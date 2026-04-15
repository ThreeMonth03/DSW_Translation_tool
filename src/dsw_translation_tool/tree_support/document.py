"""Markdown document rendering and parsing for translator-facing tree files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..constants import FIELD_EXPORT_ORDER, LEGACY_SHARED_FIELD_NOTES, SHARED_FIELD_NOTE
from ..data_models import TranslationFieldState


class TranslationMarkdownDocument:
    """Render and parse translator-facing `translation.md` files.

    Args:
        source_lang: Source language code shown in the document.
        target_lang: Target language code shown in the document.
    """

    def __init__(self, source_lang: str = "en", target_lang: str = "zh_Hant"):
        self.source_lang = source_lang
        self.target_lang = target_lang

    @staticmethod
    def sort_fields(fields: Iterable[str]) -> list[str]:
        """Sort field names in a translator-friendly order.

        Args:
            fields: Field names to sort.

        Returns:
            A stable list of ordered field names.
        """

        return sorted(
            fields,
            key=lambda field: (
                FIELD_EXPORT_ORDER.index(field)
                if field in FIELD_EXPORT_ORDER
                else len(FIELD_EXPORT_ORDER),
                field,
            ),
        )

    def render(
        self,
        entity_uuid: str,
        event_type: str | None,
        fields: dict[str, TranslationFieldState],
        shared_fields: Iterable[str] = (),
    ) -> str:
        """Render one node folder into markdown.

        Args:
            entity_uuid: UUID of the exported node.
            event_type: DSW event type for the node.
            fields: Translation fields to render.
            shared_fields: Field names whose source of truth is
                `shared_blocks.md`.

        Returns:
            Rendered markdown content for `translation.md`.
        """

        shared_field_set = set(shared_fields)
        lines = [
            "# Translation",
            "",
            f"- UUID: `{entity_uuid}`",
            f"- Event Type: `{event_type}`",
            f"- Edit only the `Translation ({self.target_lang})` blocks below.",
            "",
        ]

        for field in self.sort_fields(fields.keys()):
            state = fields[field]
            field_lines = [f"## {field}", ""]
            if field in shared_field_set:
                field_lines.extend([SHARED_FIELD_NOTE, ""])
            lines.extend(
                field_lines
                + [
                    f"### Source ({self.source_lang})",
                    "",
                    "~~~text",
                    state.source_text,
                    "~~~",
                    "",
                    f"### Translation ({self.target_lang})",
                    "",
                    "~~~text",
                    state.target_text,
                    "~~~",
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    def parse(self, markdown_path: str) -> dict[str, TranslationFieldState]:
        """Parse a `translation.md` file back into field states.

        Args:
            markdown_path: Path to the markdown document.

        Returns:
            Parsed translation fields keyed by field name.
        """

        markdown_text = Path(markdown_path).read_text(encoding="utf-8")
        return self.parse_text(markdown_text, markdown_path)

    def parse_text(
        self,
        markdown_text: str,
        markdown_path: str,
    ) -> dict[str, TranslationFieldState]:
        """Parse markdown text and validate its template structure.

        Args:
            markdown_text: Markdown content to parse.
            markdown_path: Source path used in error messages.

        Returns:
            Parsed translation fields keyed by field name.

        Raises:
            ValueError: If the document structure is invalid.
        """

        lines = markdown_text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        index = self._consume_header(lines, markdown_path)
        fields: dict[str, TranslationFieldState] = {}

        while index < len(lines):
            if not lines[index].strip():
                index += 1
                continue

            field_line = lines[index]
            if not field_line.startswith("## "):
                self._raise_parse_error(
                    markdown_path,
                    index + 1,
                    "Unexpected content outside a fenced translation block.",
                )
            field_name = field_line[3:].strip()
            if not field_name:
                self._raise_parse_error(
                    markdown_path,
                    index + 1,
                    "Field heading is missing its field name.",
                )
            if field_name in fields:
                self._raise_parse_error(
                    markdown_path,
                    index + 1,
                    f"Duplicate field section detected for `{field_name}`.",
                )
            index += 1
            index = self._consume_blank_lines(lines, index)
            index = self._consume_optional_shared_field_note(lines, index)

            index = self._expect_exact_line(
                lines=lines,
                index=index,
                expected=f"### Source ({self.source_lang})",
                markdown_path=markdown_path,
                message=f"Missing source heading for `{field_name}`.",
            )
            index = self._consume_blank_lines(lines, index)
            source_text, index = self._consume_fenced_block(
                lines=lines,
                index=index,
                markdown_path=markdown_path,
                field_name=field_name,
                role_label="source",
            )
            index = self._consume_blank_lines(lines, index)

            index = self._expect_exact_line(
                lines=lines,
                index=index,
                expected=f"### Translation ({self.target_lang})",
                markdown_path=markdown_path,
                message=f"Missing translation heading for `{field_name}`.",
            )
            index = self._consume_blank_lines(lines, index)
            target_text, index = self._consume_fenced_block(
                lines=lines,
                index=index,
                markdown_path=markdown_path,
                field_name=field_name,
                role_label="translation",
            )
            index = self._consume_blank_lines(lines, index)

            fields[field_name] = TranslationFieldState(
                source_text=source_text,
                target_text=target_text,
            )

        return fields

    def _consume_header(
        self,
        lines: list[str],
        markdown_path: str,
    ) -> int:
        """Consume and validate the fixed `translation.md` header.

        Args:
            lines: Markdown lines without the trailing newline sentinel.
            markdown_path: Source path used in error messages.

        Returns:
            Index of the first line after the header.
        """

        expected_prefixes = (
            "# Translation",
            f"- Edit only the `Translation ({self.target_lang})` blocks below.",
        )
        index = 0

        index = self._expect_exact_line(
            lines=lines,
            index=index,
            expected=expected_prefixes[0],
            markdown_path=markdown_path,
            message="Missing translation document title.",
        )
        index = self._consume_blank_lines(lines, index)

        index = self._expect_pattern_line(
            lines=lines,
            index=index,
            pattern=r"- UUID: `[^`]+`",
            markdown_path=markdown_path,
            message="Malformed UUID metadata header.",
        )
        index = self._consume_blank_lines(lines, index)
        index = self._expect_pattern_line(
            lines=lines,
            index=index,
            pattern=r"- Event Type: `[^`]*`",
            markdown_path=markdown_path,
            message="Malformed Event Type metadata header.",
        )
        index = self._consume_blank_lines(lines, index)
        index = self._expect_exact_line(
            lines=lines,
            index=index,
            expected=expected_prefixes[1],
            markdown_path=markdown_path,
            message="Missing translator guidance line.",
        )
        return self._consume_blank_lines(lines, index)

    def _consume_optional_shared_field_note(
        self,
        lines: list[str],
        index: int,
    ) -> int:
        """Consume the optional shared-field guidance line.

        Args:
            lines: Markdown lines without the trailing newline sentinel.
            index: Current parser index after a field heading.

        Returns:
            Updated parser index after skipping the optional note.
        """

        if index < len(lines) and lines[index].strip() in LEGACY_SHARED_FIELD_NOTES:
            index += 1
            index = self._consume_blank_lines(lines, index)
        return index

    @staticmethod
    def _consume_blank_lines(lines: list[str], index: int) -> int:
        """Skip blank lines and return the next non-blank index."""

        while index < len(lines) and not lines[index].strip():
            index += 1
        return index

    def _expect_exact_line(
        self,
        lines: list[str],
        index: int,
        expected: str,
        markdown_path: str,
        message: str,
    ) -> int:
        """Require an exact line match and advance the parser."""

        if index >= len(lines):
            self._raise_parse_error(markdown_path, len(lines), message)
        if lines[index] != expected:
            self._raise_parse_error(markdown_path, index + 1, message)
        return index + 1

    def _expect_pattern_line(
        self,
        lines: list[str],
        index: int,
        pattern: str,
        markdown_path: str,
        message: str,
    ) -> int:
        """Require a regex full-match and advance the parser."""

        if index >= len(lines):
            self._raise_parse_error(markdown_path, len(lines), message)
        if re.fullmatch(pattern, lines[index]) is None:
            self._raise_parse_error(markdown_path, index + 1, message)
        return index + 1

    def _consume_fenced_block(
        self,
        lines: list[str],
        index: int,
        markdown_path: str,
        field_name: str,
        role_label: str,
    ) -> tuple[str, int]:
        """Consume one fenced `~~~text` block.

        Args:
            lines: Markdown lines being parsed.
            index: Current parser index.
            markdown_path: Source path used in error messages.
            field_name: Field currently being parsed.
            role_label: Human-readable role label for error messages.

        Returns:
            Parsed block text and the next index after the closing fence.
        """

        index = self._expect_exact_line(
            lines=lines,
            index=index,
            expected="~~~text",
            markdown_path=markdown_path,
            message=(f"Missing opening fence for `{field_name}` {role_label} block."),
        )
        block_lines: list[str] = []
        while index < len(lines):
            current_line = lines[index]
            stripped = current_line.strip()
            if stripped == "~~~":
                return "\n".join(block_lines), index + 1
            if stripped.startswith("~~~"):
                self._raise_parse_error(
                    markdown_path,
                    index + 1,
                    (f"Broken fence detected inside `{field_name}` {role_label} block."),
                )
            block_lines.append(current_line)
            index += 1

        self._raise_parse_error(
            markdown_path,
            len(lines),
            f"Unclosed fence for `{field_name}` {role_label} block.",
        )

    @staticmethod
    def _raise_parse_error(
        markdown_path: str,
        line_number: int,
        message: str,
    ) -> None:
        """Raise a consistent translation markdown parse error."""

        raise ValueError(f"{markdown_path}: line {line_number}: {message}")
