"""PO parsing and writing services."""

from __future__ import annotations

from typing import Iterable

from .constants import UUID_RE
from .models import PoBlock, PoEntry, PoReference


class PoStringCodec:
    """Handle PO string escaping and decoding."""

    @staticmethod
    def decode(value: str) -> str:
        """Decode PO escape sequences.

        Args:
            value: Encoded PO string payload without surrounding quotes.

        Returns:
            Decoded text.
        """

        if "\\" not in value:
            return value
        replacements = [
            ("\\\\", "\\"),
            ("\\n", "\n"),
            ("\\t", "\t"),
            ("\\r", "\r"),
            ('\\"', '"'),
            ("\\'", "'"),
            ("\\u2028", "\u2028"),
            ("\\u2029", "\u2029"),
        ]
        for old, new in replacements:
            value = value.replace(old, new)
        return value

    @staticmethod
    def escape(value: str) -> str:
        """Escape a string for PO serialization.

        Args:
            value: Plain text value.

        Returns:
            Escaped PO string payload without surrounding quotes.
        """

        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )


class PoCatalogParser:
    """Parse PO files into block and field-level structures.

    Args:
        po_path: Path to the PO file being parsed.
    """

    def __init__(self, po_path: str):
        self.po_path = po_path

    def parse_blocks(self) -> list[PoBlock]:
        """Parse the PO file into message blocks.

        Returns:
            Parsed PO blocks with grouped references.
        """

        with open(self.po_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        index = 0
        pending_tokens: list[str] = []
        pending_is_fuzzy = False
        blocks: list[PoBlock] = []

        while index < len(lines):
            line = lines[index].rstrip("\n")
            if line.startswith("#"):
                pending_tokens, pending_is_fuzzy = self._consume_comment_line(
                    line=line,
                    pending_tokens=pending_tokens,
                    pending_is_fuzzy=pending_is_fuzzy,
                )
                index += 1
                continue

            if line.startswith("msgid "):
                block, index = self._parse_block(
                    lines=lines,
                    start_index=index,
                    pending_tokens=pending_tokens,
                    pending_is_fuzzy=pending_is_fuzzy,
                )
                if block is not None:
                    blocks.append(block)
                pending_tokens = []
                pending_is_fuzzy = False
                continue

            if not line:
                pending_tokens = []
                pending_is_fuzzy = False
            index += 1

        return blocks

    def parse_entries(self) -> list[PoEntry]:
        """Flatten parsed PO blocks into `(uuid, field)` entries.

        Returns:
            Flattened PO entries.
        """

        entries: list[PoEntry] = []
        for block in self.parse_blocks():
            for reference in block.references:
                entries.append(
                    PoEntry(
                        prefix=reference.prefix,
                        uuid=reference.uuid,
                        field=reference.field,
                        comment=reference.comment,
                        msgid=block.msgid,
                        msgstr=block.msgstr,
                    )
                )
        return entries

    @staticmethod
    def parse_comment_token(token: str) -> PoReference | None:
        """Parse one PO `#:` token into a structured reference.

        Args:
            token: Raw PO reference token.

        Returns:
            Structured PO reference or `None` if the token is unrelated.
        """

        parts = token.split(":")
        if len(parts) < 3 or not UUID_RE.fullmatch(parts[1]):
            return None
        return PoReference(
            prefix=parts[0],
            uuid=parts[1],
            field=parts[2],
            comment=token,
        )

    @staticmethod
    def _parse_string_block(
        lines: list[str],
        start_index: int,
    ) -> tuple[str, int]:
        """Parse one `msgid` or `msgstr` block from the PO file."""

        line = lines[start_index].rstrip("\n")
        current = line.split(" ", 1)[1]
        parts: list[str] = []
        if current != '""':
            parts.append(PoStringCodec.decode(current[1:-1]))

        index = start_index + 1
        while index < len(lines):
            current_line = lines[index].rstrip("\n")
            if not current_line.startswith('"'):
                break
            parts.append(PoStringCodec.decode(current_line[1:-1]))
            index += 1
        return "".join(parts), index

    @staticmethod
    def _consume_comment_line(
        line: str,
        pending_tokens: list[str],
        pending_is_fuzzy: bool,
    ) -> tuple[list[str], bool]:
        """Update parser state from one PO comment line."""

        if line.startswith("#:"):
            pending_tokens.extend(line[2:].strip().split())
        elif line.startswith("#,") and "fuzzy" in line:
            pending_is_fuzzy = True
        return pending_tokens, pending_is_fuzzy

    def _parse_block(
        self,
        lines: list[str],
        start_index: int,
        pending_tokens: list[str],
        pending_is_fuzzy: bool,
    ) -> tuple[PoBlock | None, int]:
        """Parse one PO message block starting at `msgid`."""

        msgid, index = self._parse_string_block(lines, start_index)
        if index < len(lines) and lines[index].startswith("msgstr "):
            msgstr, index = self._parse_string_block(lines, index)
        else:
            msgstr = ""

        references = tuple(self._parse_references(pending_tokens))
        if not references:
            return None, index

        return (
            PoBlock(
                references=references,
                msgid=msgid,
                msgstr=msgstr,
                is_fuzzy=pending_is_fuzzy,
            ),
            index,
        )

    @staticmethod
    def _parse_references(tokens: list[str]) -> Iterable[PoReference]:
        """Parse PO reference tokens, skipping unrelated tokens."""

        for token in tokens:
            reference = PoCatalogParser.parse_comment_token(token)
            if reference is not None:
                yield reference


class PoCatalogWriter:
    """Rewrite translations back into an original PO template."""

    def rewrite_translations(
        self,
        original_po_path: str,
        translations_by_key: dict[tuple[str, str], str],
    ) -> str:
        """Rewrite PO `msgstr` values using the provided translation map.

        Args:
            original_po_path: Original PO file used as the structural template.
            translations_by_key: Mapping from `(uuid, field)` to target text.

        Returns:
            Rewritten PO content.
        """

        with open(original_po_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        output_lines: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            if not line.startswith("#:"):
                output_lines.append(line)
                index += 1
                continue

            section, index = self._parse_reference_section(lines, index)
            rewritten_lines, index = self._rewrite_section(
                lines=lines,
                start_index=index,
                section=section,
                translations_by_key=translations_by_key,
            )
            output_lines.extend(rewritten_lines)

        return "".join(output_lines)

    @staticmethod
    def _parse_reference_section(
        lines: list[str],
        start_index: int,
    ) -> tuple[dict[str, list[str]], int]:
        """Parse contiguous `#:` lines and collect raw tokens."""

        comment_lines: list[str] = []
        comment_tokens: list[str] = []
        index = start_index
        while index < len(lines) and lines[index].startswith("#:"):
            comment_tokens.extend(lines[index][2:].strip().split())
            comment_lines.append(lines[index])
            index += 1
        return {
            "comment_lines": comment_lines,
            "comment_tokens": comment_tokens,
        }, index

    def _rewrite_section(
        self,
        lines: list[str],
        start_index: int,
        section: dict[str, list[str]],
        translations_by_key: dict[tuple[str, str], str],
    ) -> tuple[list[str], int]:
        """Rewrite one PO section following its reference comments."""

        index = start_index
        output_lines: list[str] = []
        parsed_tokens = list(self._parse_section_tokens(section["comment_tokens"]))
        extra_comment_lines, index = self._collect_extra_comment_lines(lines, index)
        msgid_lines, index = self._collect_msgid_lines(lines, index)

        if index >= len(lines) or not lines[index].startswith("msgstr "):
            output_lines.extend(section["comment_lines"])
            output_lines.extend(extra_comment_lines)
            output_lines.extend(msgid_lines)
            return output_lines, index

        current_msgstr, next_index = PoCatalogParser._parse_string_block(lines, index)
        if not parsed_tokens:
            output_lines.extend(section["comment_lines"])
            output_lines.extend(extra_comment_lines)
            output_lines.extend(msgid_lines)
            output_lines.extend(lines[index:next_index])
            return output_lines, next_index

        grouped_tokens = self._group_tokens_by_translation(
            parsed_tokens=parsed_tokens,
            translations_by_key=translations_by_key,
            fallback_msgstr=current_msgstr,
        )
        output_lines.extend(
            self._render_grouped_tokens(
                grouped_tokens=grouped_tokens,
                parsed_tokens=parsed_tokens,
                comment_lines=section["comment_lines"],
                extra_comment_lines=extra_comment_lines,
                msgid_lines=msgid_lines,
            )
        )
        return output_lines, next_index

    @staticmethod
    def _parse_section_tokens(tokens: list[str]) -> Iterable[PoReference]:
        """Parse structured PO references from a raw token list."""

        for token in tokens:
            reference = PoCatalogParser.parse_comment_token(token)
            if reference is not None:
                yield reference

    @staticmethod
    def _collect_extra_comment_lines(
        lines: list[str],
        start_index: int,
    ) -> tuple[list[str], int]:
        """Collect non-reference comment lines after a PO section header."""

        extra_comment_lines: list[str] = []
        index = start_index
        while (
            index < len(lines)
            and lines[index].startswith("#")
            and not lines[index].startswith("#:")
        ):
            extra_comment_lines.append(lines[index])
            index += 1
        return extra_comment_lines, index

    @staticmethod
    def _collect_msgid_lines(
        lines: list[str],
        start_index: int,
    ) -> tuple[list[str], int]:
        """Collect the `msgid` block lines for one PO section."""

        index = start_index
        msgid_lines: list[str] = []
        if index < len(lines) and lines[index].startswith("msgid "):
            _, next_index = PoCatalogParser._parse_string_block(lines, index)
            msgid_lines = lines[index:next_index]
            index = next_index
        return msgid_lines, index

    @staticmethod
    def _group_tokens_by_translation(
        parsed_tokens: list[PoReference],
        translations_by_key: dict[tuple[str, str], str],
        fallback_msgstr: str,
    ) -> list[dict[str, object]]:
        """Group references by the translation they should receive."""

        grouped_tokens: list[dict[str, object]] = []
        for token in parsed_tokens:
            key = (token.uuid, token.field)
            msgstr_value = translations_by_key.get(key, fallback_msgstr)
            if grouped_tokens and grouped_tokens[-1]["msgstr"] == msgstr_value:
                grouped_tokens[-1]["tokens"].append(token)
            else:
                grouped_tokens.append(
                    {
                        "msgstr": msgstr_value,
                        "tokens": [token],
                    }
                )
        return grouped_tokens

    def _render_grouped_tokens(
        self,
        grouped_tokens: list[dict[str, object]],
        parsed_tokens: list[PoReference],
        comment_lines: list[str],
        extra_comment_lines: list[str],
        msgid_lines: list[str],
    ) -> list[str]:
        """Render grouped PO references back into PO block text."""

        if (
            len(grouped_tokens) == 1
            and len(grouped_tokens[0]["tokens"]) == len(parsed_tokens)
        ):
            return [
                *comment_lines,
                *extra_comment_lines,
                *msgid_lines,
                *self._format_po_string_block(
                    "msgstr",
                    grouped_tokens[0]["msgstr"],
                ),
            ]

        output_lines: list[str] = []
        for group_index, group in enumerate(grouped_tokens):
            for token in group["tokens"]:
                output_lines.append(f"#: {token.comment}\n")
            output_lines.extend(extra_comment_lines)
            output_lines.extend(msgid_lines)
            output_lines.extend(
                self._format_po_string_block(
                    "msgstr",
                    group["msgstr"],
                )
            )
            if group_index < len(grouped_tokens) - 1:
                output_lines.append("\n")
        return output_lines

    @staticmethod
    def _format_po_string_block(keyword: str, value: str) -> list[str]:
        """Format one single-line PO string block."""

        return [f'{keyword} "{PoStringCodec.escape(value)}"\n']
