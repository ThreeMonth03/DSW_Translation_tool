"""PO parsing services."""

from __future__ import annotations

from typing import Iterable

from ..constants import UUID_RE
from ..data_models import PoBlock, PoEntry, PoReference
from .codec import PoStringCodec


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
                pending_tokens, pending_is_fuzzy = self.consume_comment_line(
                    line=line,
                    pending_tokens=pending_tokens,
                    pending_is_fuzzy=pending_is_fuzzy,
                )
                index += 1
                continue

            if line.startswith("msgid "):
                block, index = self.parse_block(
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
    def parse_string_block(
        lines: list[str],
        start_index: int,
    ) -> tuple[str, int]:
        """Parse one `msgid` or `msgstr` block from the PO file.

        Args:
            lines: Full PO file lines.
            start_index: Start index of the string block.

        Returns:
            Parsed string value and the next unread line index.
        """

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
    def consume_comment_line(
        line: str,
        pending_tokens: list[str],
        pending_is_fuzzy: bool,
    ) -> tuple[list[str], bool]:
        """Update parser state from one PO comment line.

        Args:
            line: Raw PO comment line.
            pending_tokens: Tokens accumulated so far for the current block.
            pending_is_fuzzy: Whether the current block is fuzzy so far.

        Returns:
            Updated token list and fuzzy flag.
        """

        if line.startswith("#:"):
            pending_tokens.extend(line[2:].strip().split())
        elif line.startswith("#,") and "fuzzy" in line:
            pending_is_fuzzy = True
        return pending_tokens, pending_is_fuzzy

    def parse_block(
        self,
        lines: list[str],
        start_index: int,
        pending_tokens: list[str],
        pending_is_fuzzy: bool,
    ) -> tuple[PoBlock | None, int]:
        """Parse one PO message block starting at `msgid`.

        Args:
            lines: Full PO file lines.
            start_index: Index of the `msgid` line.
            pending_tokens: Reference tokens accumulated before the block.
            pending_is_fuzzy: Fuzzy flag accumulated before the block.

        Returns:
            Parsed PO block, if any, and the next unread line index.
        """

        msgid, index = self.parse_string_block(lines, start_index)
        if index < len(lines) and lines[index].startswith("msgstr "):
            msgstr, index = self.parse_string_block(lines, index)
        else:
            msgstr = ""

        references = tuple(self.parse_references(pending_tokens))
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
    def parse_references(tokens: list[str]) -> Iterable[PoReference]:
        """Parse PO reference tokens, skipping unrelated tokens.

        Args:
            tokens: Raw reference tokens collected from `#:` comments.

        Yields:
            Structured PO references.
        """

        for token in tokens:
            reference = PoCatalogParser.parse_comment_token(token)
            if reference is not None:
                yield reference
