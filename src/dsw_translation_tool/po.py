"""PO parsing and writing services."""

from __future__ import annotations

from pathlib import Path

from .constants import UUID_RE
from .models import PoBlock, PoEntry, PoReference


class PoStringCodec:
    """Handles PO string escaping and decoding."""

    @staticmethod
    def decode(value: str) -> str:
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
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )


class PoCatalogParser:
    """Parses PO files into block and field-level structures."""

    def __init__(self, po_path: str):
        self.po_path = po_path

    def parse_blocks(self) -> list[PoBlock]:
        lines = Path(self.po_path).read_text(encoding="utf-8").splitlines(keepends=True)
        index = 0
        pending_tokens: list[str] = []
        pending_is_fuzzy = False
        blocks: list[PoBlock] = []

        while index < len(lines):
            line = lines[index].rstrip("\n")

            if line.startswith("#"):
                if line.startswith("#:"):
                    pending_tokens.extend(line[2:].strip().split())
                elif line.startswith("#,") and "fuzzy" in line:
                    pending_is_fuzzy = True
                index += 1
                continue

            if line.startswith("msgid "):
                msgid, index = self._parse_string_block(lines, index)
                if index < len(lines) and lines[index].startswith("msgstr "):
                    msgstr, index = self._parse_string_block(lines, index)
                else:
                    msgstr = ""

                references = tuple(
                    ref
                    for token in pending_tokens
                    if (ref := self.parse_comment_token(token)) is not None
                )
                if references:
                    blocks.append(
                        PoBlock(
                            references=references,
                            msgid=msgid,
                            msgstr=msgstr,
                            is_fuzzy=pending_is_fuzzy,
                        )
                    )

                pending_tokens = []
                pending_is_fuzzy = False
                continue

            if not line:
                pending_tokens = []
                pending_is_fuzzy = False
            index += 1

        return blocks

    def parse_entries(self) -> list[PoEntry]:
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
    def _parse_string_block(lines: list[str], start_index: int) -> tuple[str, int]:
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


class PoCatalogWriter:
    """Rewrites translations back into an original PO template."""

    @staticmethod
    def rewrite_translations(original_po_path: str, translations_by_key: dict[tuple[str, str], str]) -> str:
        lines = Path(original_po_path).read_text(encoding="utf-8").splitlines(keepends=True)
        output_lines: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            if not line.startswith("#:"):
                output_lines.append(line)
                index += 1
                continue

            comment_lines: list[str] = []
            comment_tokens: list[str] = []
            while index < len(lines) and lines[index].startswith("#:"):
                comment_tokens.extend(lines[index][2:].strip().split())
                comment_lines.append(lines[index])
                index += 1

            parsed_tokens = [
                token
                for token in (PoCatalogParser.parse_comment_token(comment) for comment in comment_tokens)
                if token is not None
            ]

            extra_comment_lines: list[str] = []
            while index < len(lines) and lines[index].startswith("#") and not lines[index].startswith("#:"):
                extra_comment_lines.append(lines[index])
                index += 1

            msgid_lines: list[str] = []
            if index < len(lines) and lines[index].startswith("msgid "):
                _, next_index = PoCatalogParser._parse_string_block(lines, index)
                msgid_lines = lines[index:next_index]
                index = next_index

            if index >= len(lines) or not lines[index].startswith("msgstr "):
                continue

            current_msgstr, next_index = PoCatalogParser._parse_string_block(lines, index)
            if not parsed_tokens:
                output_lines.extend(comment_lines)
                output_lines.extend(extra_comment_lines)
                output_lines.extend(msgid_lines)
                output_lines.extend(lines[index:next_index])
                index = next_index
                continue

            grouped_tokens: list[dict[str, list | str]] = []
            for token in parsed_tokens:
                key = (token.uuid, token.field)
                msgstr_value = translations_by_key.get(key, current_msgstr)
                if grouped_tokens and grouped_tokens[-1]["msgstr"] == msgstr_value:
                    grouped_tokens[-1]["tokens"].append(token)
                else:
                    grouped_tokens.append({"msgstr": msgstr_value, "tokens": [token]})

            if len(grouped_tokens) == 1 and len(grouped_tokens[0]["tokens"]) == len(parsed_tokens):
                output_lines.extend(comment_lines)
                output_lines.extend(extra_comment_lines)
                output_lines.extend(msgid_lines)
                output_lines.extend(PoCatalogWriter._format_po_string_block("msgstr", grouped_tokens[0]["msgstr"]))
            else:
                for group_index, group in enumerate(grouped_tokens):
                    for token in group["tokens"]:
                        output_lines.append(f"#: {token.comment}\n")
                    output_lines.extend(extra_comment_lines)
                    output_lines.extend(msgid_lines)
                    output_lines.extend(PoCatalogWriter._format_po_string_block("msgstr", group["msgstr"]))
                    if group_index < len(grouped_tokens) - 1:
                        output_lines.append("\n")
            index = next_index

        return "".join(output_lines)

    @staticmethod
    def _format_po_string_block(keyword: str, value: str) -> list[str]:
        return [f'{keyword} "{PoStringCodec.escape(value)}"\n']
