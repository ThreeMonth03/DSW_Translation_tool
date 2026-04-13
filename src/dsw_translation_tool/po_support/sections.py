"""Section readers for PO rewrite workflows."""

from __future__ import annotations

from typing import Iterable

from ..data_models import PoReference, PoReferenceSection
from .parser import PoCatalogParser


class PoReferenceSectionReader:
    """Read comment and `msgid` sections from an existing PO template."""

    @staticmethod
    def parse_reference_section(
        lines: list[str],
        start_index: int,
    ) -> tuple[PoReferenceSection, int]:
        """Parse contiguous `#:` lines and collect raw tokens.

        Args:
            lines: Full PO file lines.
            start_index: First `#:` line index for the section.

        Returns:
            Parsed reference section and next unread line index.
        """

        comment_lines: list[str] = []
        comment_tokens: list[str] = []
        index = start_index
        while index < len(lines) and lines[index].startswith("#:"):
            comment_tokens.extend(lines[index][2:].strip().split())
            comment_lines.append(lines[index])
            index += 1
        return (
            PoReferenceSection(
                comment_lines=tuple(comment_lines),
                comment_tokens=tuple(comment_tokens),
            ),
            index,
        )

    @staticmethod
    def parse_section_tokens(tokens: tuple[str, ...]) -> Iterable[PoReference]:
        """Parse structured PO references from a raw token list.

        Args:
            tokens: Raw reference tokens collected from `#:` comments.

        Yields:
            Structured PO references.
        """

        for token in tokens:
            reference = PoCatalogParser.parse_comment_token(token)
            if reference is not None:
                yield reference

    @staticmethod
    def collect_extra_comment_lines(
        lines: list[str],
        start_index: int,
    ) -> tuple[list[str], int]:
        """Collect non-reference comment lines after a PO section header.

        Args:
            lines: Full PO file lines.
            start_index: First unread line after the `#:` section.

        Returns:
            Extra comment lines and next unread line index.
        """

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
    def collect_msgid_lines(
        lines: list[str],
        start_index: int,
    ) -> tuple[list[str], int]:
        """Collect the `msgid` block lines for one PO section.

        Args:
            lines: Full PO file lines.
            start_index: First unread line after section comments.

        Returns:
            `msgid` lines and next unread line index.
        """

        index = start_index
        msgid_lines: list[str] = []
        if index < len(lines) and lines[index].startswith("msgid "):
            _, next_index = PoCatalogParser.parse_string_block(lines, index)
            msgid_lines = lines[index:next_index]
            index = next_index
        return msgid_lines, index
