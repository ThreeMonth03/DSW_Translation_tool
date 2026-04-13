"""Rendering helpers for rewritten PO sections."""

from __future__ import annotations

from ..data_models import PoReference, PoTranslationGroup
from .codec import PoStringCodec


class PoSectionRenderer:
    """Render grouped PO references back into serialized PO text."""

    @staticmethod
    def group_tokens_by_translation(
        parsed_tokens: list[PoReference],
        translations_by_key: dict[tuple[str, str], str],
        fallback_msgstr: str,
    ) -> list[PoTranslationGroup]:
        """Group references by the translation they should receive.

        Args:
            parsed_tokens: Structured references in original section order.
            translations_by_key: Mapping from `(uuid, field)` to target text.
            fallback_msgstr: Current block translation used as fallback.

        Returns:
            Consecutive reference groups keyed by target translation.
        """

        grouped_tokens: list[PoTranslationGroup] = []
        for token in parsed_tokens:
            key = (token.uuid, token.field)
            msgstr_value = translations_by_key.get(key, fallback_msgstr)
            if grouped_tokens and grouped_tokens[-1].msgstr == msgstr_value:
                previous = grouped_tokens[-1]
                grouped_tokens[-1] = PoTranslationGroup(
                    msgstr=previous.msgstr,
                    tokens=(*previous.tokens, token),
                )
            else:
                grouped_tokens.append(
                    PoTranslationGroup(
                        msgstr=msgstr_value,
                        tokens=(token,),
                    )
                )
        return grouped_tokens

    def render_grouped_tokens(
        self,
        grouped_tokens: list[PoTranslationGroup],
        parsed_tokens: list[PoReference],
        comment_lines: tuple[str, ...],
        extra_comment_lines: list[str],
        msgid_lines: list[str],
    ) -> list[str]:
        """Render grouped PO references back into PO block text.

        Args:
            grouped_tokens: Consecutive reference groups keyed by translation.
            parsed_tokens: Original structured references for the section.
            comment_lines: Original `#:` lines.
            extra_comment_lines: Non-reference comment lines after `#:`.
            msgid_lines: Original `msgid` block lines.

        Returns:
            Rewritten PO lines for the section.
        """

        if len(grouped_tokens) == 1 and len(grouped_tokens[0].tokens) == len(parsed_tokens):
            return [
                *comment_lines,
                *extra_comment_lines,
                *msgid_lines,
                *self.format_po_string_block(
                    "msgstr",
                    grouped_tokens[0].msgstr,
                ),
            ]

        output_lines: list[str] = []
        for group_index, group in enumerate(grouped_tokens):
            for token in group.tokens:
                output_lines.append(f"#: {token.comment}\n")
            output_lines.extend(extra_comment_lines)
            output_lines.extend(msgid_lines)
            output_lines.extend(
                self.format_po_string_block(
                    "msgstr",
                    group.msgstr,
                )
            )
            if group_index < len(grouped_tokens) - 1:
                output_lines.append("\n")
        return output_lines

    @staticmethod
    def format_po_string_block(keyword: str, value: str) -> list[str]:
        """Format one single-line PO string block.

        Args:
            keyword: PO keyword such as `msgid` or `msgstr`.
            value: Plain-text value to format.

        Returns:
            Serialized PO lines for the string block.
        """

        return [f'{keyword} "{PoStringCodec.escape(value)}"\n']
