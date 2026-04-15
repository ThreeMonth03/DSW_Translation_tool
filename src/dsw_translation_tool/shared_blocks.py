"""Shared-block markdown generation and parsing services."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    MANIFEST_NAME,
    SHARED_BLOCK_CONTEXT_FILENAME,
    SHARED_BLOCKS_DIRNAME,
    SHARED_BLOCKS_FILENAME,
    UUID_FILENAME,
)
from .data_models import (
    PoBlock,
    PoReference,
    SharedBlocksBuildResult,
    SharedBlocksDirectoryBuildResult,
    SharedBlocksOutlineBuildResult,
    TreeFolderSnapshot,
)
from .outline_support import TranslationOutlineRenderer
from .po import PoCatalogParser
from .tree import TranslationTreeRepository

GROUP_HEADING_RE = re.compile(r"^## Group (?P<index>\d{4})$")
STATUS_LINE_RE = re.compile(r"^- Status: \[(?P<checkbox>[ x])\]$")
REFERENCE_COUNT_RE = re.compile(r"^- References: `(?P<count>\d+)`$")
SHARED_KEY_RE = re.compile(r"^- Shared Key: `(?P<key>[^`]*)`$")
GROUP_BLOCK_ANCHOR_RE = re.compile(r'^<a id="group-(?P<index>\d{4})-blocks"></a>$')
GROUP_TRANSLATION_ANCHOR_RE = re.compile(r'^<a id="group-(?P<index>\d{4})-translation"></a>$')
TRANSLATION_SECTION_HEADING_RE = re.compile(r"^### Translation zh-Hant Group (?P<index>\d{4})$")
SEGMENT_ORDER_RE = re.compile(r"^\d{4}\s+")
SEGMENT_UUID_SUFFIX_RE = re.compile(r" \[[0-9a-f]{8}\]$")


@dataclass(frozen=True)
class SharedBlockContext:
    """One linked tree context rendered inside `shared_blocks.md`.

    Args:
        reference: Structured `(uuid, field)` reference represented by the
            context.
        badge: Short event-type badge shown before the link.
        label: Human-readable linked node label.
        relative_link: Relative markdown destination.
        context_label: Short parent/self/child summary for translators.
    """

    reference: PoReference
    badge: str
    label: str
    relative_link: str
    context_label: str


@dataclass(frozen=True)
class SharedBlockRecord:
    """One shared PO block rendered into `shared_blocks.md`.

    Args:
        group_key: Stable key derived from the block references.
        source_text: Shared source-language text.
        translation_text: Canonical target-language translation.
        contexts: All linked tree contexts that share this block.
        stable_id: Stable filesystem identifier used for the group directory.
    """

    group_key: tuple[tuple[str, str], ...]
    source_text: str
    translation_text: str
    contexts: tuple[SharedBlockContext, ...]
    stable_id: str

    @property
    def is_translated(self) -> bool:
        """Return whether the shared block currently has a translation."""

        return bool(self.translation_text.strip())

    @property
    def field_names(self) -> tuple[str, ...]:
        """Return sorted field names represented by the shared block."""

        return tuple(
            sorted({context.reference.field for context in self.contexts}, key=str.casefold)
        )


class SharedBlocksCatalogParser:
    """Parse shared-block collaboration artifacts into canonical translations.

    Args:
        source_lang: Source language code used by the markdown template.
        target_lang: Target language code used by the markdown template.
    """

    def __init__(self, source_lang: str = "en", target_lang: str = "zh_Hant"):
        self.source_lang = source_lang
        self.target_lang = target_lang

    def parse(
        self,
        shared_blocks_path: str,
        expected_group_keys: set[tuple[tuple[str, str], ...]] | None = None,
    ) -> dict[tuple[tuple[str, str], ...], str]:
        """Parse shared-block canonical content from disk.

        Args:
            shared_blocks_path: Shared-block markdown path or canonical root
                directory.
            expected_group_keys: Optional expected shared-group set used for
                stable directory parsing.

        Returns:
            Mapping from stable group keys to translated text.
        """

        shared_blocks_location = Path(shared_blocks_path)
        if shared_blocks_location.is_dir():
            return self.parse_directory(
                shared_blocks_root=shared_blocks_location,
                expected_group_keys=expected_group_keys,
            )

        markdown_text = shared_blocks_location.read_text(encoding="utf-8")
        return self.parse_text(markdown_text, str(shared_blocks_location))

    def parse_text(
        self,
        markdown_text: str,
        markdown_path: str,
    ) -> dict[tuple[tuple[str, str], ...], str]:
        """Parse shared-block markdown text.

        Args:
            markdown_text: Markdown content to parse.
            markdown_path: Source path used in error messages.

        Returns:
            Mapping from stable group keys to translated text.

        Raises:
            ValueError: If the markdown structure is invalid.
        """

        lines = markdown_text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        index = self._expect_exact_line(
            lines=lines,
            index=0,
            expected="# Shared Blocks",
            markdown_path=markdown_path,
            message="Missing shared-block document title.",
        )
        translations: dict[tuple[tuple[str, str], ...], str] = {}

        while index < len(lines):
            if not lines[index].strip():
                index += 1
                continue
            match = GROUP_HEADING_RE.fullmatch(lines[index].strip())
            if match is None:
                index += 1
                continue
            group_index = match.group("index")
            index += 1
            index = self._consume_blank_lines(lines, index)
            index = self._expect_pattern_line(
                lines=lines,
                index=index,
                pattern=STATUS_LINE_RE,
                markdown_path=markdown_path,
                message="Malformed shared-block status line.",
            )
            index = self._consume_blank_lines(lines, index)
            index = self._expect_pattern_line(
                lines=lines,
                index=index,
                pattern=REFERENCE_COUNT_RE,
                markdown_path=markdown_path,
                message="Malformed shared-block reference-count line.",
            )
            index = self._consume_blank_lines(lines, index)
            key_line, index = self._expect_pattern_line(
                lines=lines,
                index=index,
                pattern=SHARED_KEY_RE,
                markdown_path=markdown_path,
                message="Malformed shared-block key line.",
                return_line=True,
            )
            key_match = SHARED_KEY_RE.fullmatch(key_line.strip())
            assert key_match is not None
            group_key = self.deserialize_group_key(key_match.group("key"))

            index = self._consume_blank_lines(lines, index)
            if index < len(lines) and GROUP_BLOCK_ANCHOR_RE.fullmatch(lines[index].strip()):
                index += 1
                index = self._consume_blank_lines(lines, index)
            index = self._expect_exact_line(
                lines=lines,
                index=index,
                expected=f"### Source ({self.source_lang})",
                markdown_path=markdown_path,
                message="Missing shared-block source heading.",
            )
            index = self._consume_blank_lines(lines, index)
            _, index = self._consume_fenced_block(
                lines=lines,
                index=index,
                markdown_path=markdown_path,
                role_label="source",
            )

            index = self._consume_blank_lines(lines, index)
            if index < len(lines) and GROUP_TRANSLATION_ANCHOR_RE.fullmatch(lines[index].strip()):
                index += 1
                index = self._consume_blank_lines(lines, index)
            if index < len(lines):
                translation_section_heading = f"### Translation zh-Hant Group {group_index}"
                if lines[index].strip() == translation_section_heading:
                    index += 1
                    index = self._consume_blank_lines(lines, index)
            index = self._expect_exact_line(
                lines=lines,
                index=index,
                expected=f"### Translation ({self.target_lang})",
                markdown_path=markdown_path,
                message="Missing shared-block translation heading.",
            )
            index = self._consume_blank_lines(lines, index)
            translation_text, index = self._consume_fenced_block(
                lines=lines,
                index=index,
                markdown_path=markdown_path,
                role_label="translation",
            )
            translations[group_key] = translation_text

            while index < len(lines):
                if GROUP_HEADING_RE.fullmatch(lines[index].strip()):
                    break
                index += 1

        return translations

    def parse_directory(
        self,
        shared_blocks_root: str | Path,
        expected_group_keys: set[tuple[tuple[str, str], ...]] | None = None,
    ) -> dict[tuple[tuple[str, str], ...], str]:
        """Parse split shared-block canonical files from one directory root.

        Args:
            shared_blocks_root: Canonical shared-block directory root.
            expected_group_keys: Optional expected shared-group set. When
                provided, the parser reads the deterministic `context.md`
                file for each expected group directly.

        Returns:
            Mapping from stable group keys to translated text.
        """

        root_path = Path(shared_blocks_root)
        if expected_group_keys is not None:
            return self._parse_expected_group_directory(root_path, expected_group_keys)

        translations: dict[tuple[tuple[str, str], ...], str] = {}
        for context_path in sorted(root_path.glob(f"*/{SHARED_BLOCK_CONTEXT_FILENAME}")):
            group_key = self._parse_group_key_from_context(context_path)
            translations[group_key] = self._parse_translation_from_context(context_path)
        return translations

    def _parse_expected_group_directory(
        self,
        shared_blocks_root: Path,
        expected_group_keys: set[tuple[tuple[str, str], ...]],
    ) -> dict[tuple[tuple[str, str], ...], str]:
        """Parse deterministic split shared-block files for the expected groups.

        Args:
            shared_blocks_root: Canonical shared-block directory root.
            expected_group_keys: Structured shared-group set expected by sync.

        Returns:
            Mapping from stable group keys to translated text.
        """

        translations: dict[tuple[tuple[str, str], ...], str] = {}
        for group_key in sorted(expected_group_keys):
            context_path = self.group_context_path(shared_blocks_root, group_key)
            if not context_path.exists():
                raise ValueError(
                    "Missing shared-block context file.\n"
                    f"File: {context_path}"
                )
            translations[group_key] = self._parse_translation_from_context(context_path)
        return translations

    def _parse_group_key_from_context(
        self,
        context_path: Path,
    ) -> tuple[tuple[str, str], ...]:
        """Parse one shared-group key from a generated `context.md` file.

        Args:
            context_path: Generated shared-block context markdown path.

        Returns:
            Structured group key.
        """

        for line in context_path.read_text(encoding="utf-8").splitlines():
            match = SHARED_KEY_RE.fullmatch(line.strip())
            if match is None:
                continue
            return self.deserialize_group_key(match.group("key"))
        raise ValueError(
            "Missing shared-block key metadata in generated context markdown.\n"
            f"File: {context_path}"
        )

    def _parse_translation_from_context(self, context_path: Path) -> str:
        """Parse the editable translation block from one canonical context file.

        Args:
            context_path: Canonical `context.md` path.

        Returns:
            Shared translation text without editor-added trailing blank lines.
        """

        lines = context_path.read_text(encoding="utf-8").splitlines()
        if lines and lines[-1] == "":
            lines = lines[:-1]
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped not in {
                f"### Translation ({self.target_lang})",
                f"### Current Translation ({self.target_lang})",
            }:
                continue
            block_start = self._consume_blank_lines(lines, index + 1)
            translation_text, _ = self._consume_fenced_block(
                lines=lines,
                index=block_start,
                markdown_path=str(context_path),
                role_label="translation",
            )
            return translation_text
        raise ValueError(
            "Missing editable translation block in shared-block context markdown.\n"
            f"File: {context_path}"
        )

    @staticmethod
    def serialize_group_key(group_key: tuple[tuple[str, str], ...]) -> str:
        """Serialize one group key into markdown metadata.

        Args:
            group_key: Structured `(uuid, field)` tuples.

        Returns:
            Stable serialized key string.
        """

        return " | ".join(f"{entity_uuid}:{field}" for entity_uuid, field in group_key)

    @staticmethod
    def stable_group_id(group_key: tuple[tuple[str, str], ...]) -> str:
        """Return a deterministic filesystem-safe identifier for one group.

        Args:
            group_key: Structured `(uuid, field)` tuples.

        Returns:
            Stable hexadecimal identifier suitable for folder names.
        """

        serialized_key = SharedBlocksCatalogParser.serialize_group_key(group_key)
        return hashlib.sha1(serialized_key.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def group_dir_path(
        cls,
        shared_blocks_root: Path,
        group_key: tuple[tuple[str, str], ...],
    ) -> Path:
        """Return the canonical directory for one shared-block group.

        Args:
            shared_blocks_root: Canonical shared-block directory root.
            group_key: Structured group key.

        Returns:
            Canonical group directory path.
        """

        return shared_blocks_root / cls.stable_group_id(group_key)

    @classmethod
    def group_context_path(
        cls,
        shared_blocks_root: Path,
        group_key: tuple[tuple[str, str], ...],
    ) -> Path:
        """Return the generated context markdown path for one group."""

        return cls.group_dir_path(shared_blocks_root, group_key) / SHARED_BLOCK_CONTEXT_FILENAME

    @staticmethod
    def deserialize_group_key(serialized_key: str) -> tuple[tuple[str, str], ...]:
        """Parse one serialized group key from markdown metadata.

        Args:
            serialized_key: Serialized key produced by `serialize_group_key`.

        Returns:
            Structured group key.

        Raises:
            ValueError: If the key is malformed.
        """

        if not serialized_key.strip():
            raise ValueError("Shared-block key is empty.")
        group_key: list[tuple[str, str]] = []
        for token in serialized_key.split(" | "):
            try:
                entity_uuid, field = token.split(":", 1)
            except ValueError as error:
                raise ValueError(f"Malformed shared-block key token: {token!r}") from error
            if not entity_uuid or not field:
                raise ValueError(f"Malformed shared-block key token: {token!r}")
            group_key.append((entity_uuid, field))
        return tuple(group_key)

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
        """Consume one exact line and return the next index."""

        if index >= len(lines) or lines[index].strip() != expected:
            self._raise_parse_error(markdown_path, index + 1, message)
        return index + 1

    def _expect_pattern_line(
        self,
        lines: list[str],
        index: int,
        pattern: re.Pattern[str],
        markdown_path: str,
        message: str,
        return_line: bool = False,
    ) -> int | tuple[str, int]:
        """Consume one regex-matched line.

        Args:
            lines: Markdown lines under parse.
            index: Current line index.
            pattern: Compiled regex that must match the stripped line.
            markdown_path: Source path used in error messages.
            message: Error message when the pattern does not match.
            return_line: Whether to return the matched line with the index.

        Returns:
            Next index, or `(line, next_index)` when `return_line` is `True`.
        """

        if index >= len(lines) or pattern.fullmatch(lines[index].strip()) is None:
            self._raise_parse_error(markdown_path, index + 1, message)
        if return_line:
            return lines[index], index + 1
        return index + 1

    def _consume_fenced_block(
        self,
        lines: list[str],
        index: int,
        markdown_path: str,
        role_label: str,
    ) -> tuple[str, int]:
        """Consume one fenced text block from shared-block markdown."""

        if index >= len(lines) or lines[index].strip() != "~~~text":
            self._raise_parse_error(
                markdown_path,
                index + 1,
                f"Missing opening fence for shared-block {role_label} block.",
            )
        index += 1
        block_lines: list[str] = []
        while index < len(lines):
            current_line = lines[index]
            if current_line.strip() == "~~~":
                return "\n".join(block_lines), index + 1
            block_lines.append(current_line)
            index += 1
        self._raise_parse_error(
            markdown_path,
            len(lines),
            f"Missing closing fence for shared-block {role_label} block.",
        )

    @staticmethod
    def _raise_parse_error(markdown_path: str, line_number: int, message: str) -> None:
        """Raise a consistently formatted shared-block parse error."""

        raise ValueError(f"{markdown_path}: line {line_number}: {message}")


def resolve_shared_blocks_backup_path(
    tree_repository: TranslationTreeRepository,
    tree_dir: str | Path,
) -> Path:
    """Return the local backup path for generated `shared_blocks.md`.

    Args:
        tree_repository: Translation tree repository that owns the path service.
        tree_dir: Translation tree root directory.

    Returns:
        Central backup path for the shared-block markdown file.
    """

    return tree_repository.path_service.backup_root(tree_dir) / f"{SHARED_BLOCKS_FILENAME}.bak"


def resolve_shared_blocks_root_path(shared_blocks_path: str | Path) -> Path:
    """Return the canonical shared-block directory for one output path.

    Args:
        shared_blocks_path: Generated top-level shared-block markdown path or
            canonical shared-block directory path.

    Returns:
        Canonical shared-block directory root.
    """

    markdown_path = Path(shared_blocks_path)
    if markdown_path.suffix == ".md":
        return markdown_path.with_suffix("")
    if markdown_path.name == SHARED_BLOCKS_DIRNAME:
        return markdown_path
    return markdown_path / SHARED_BLOCKS_DIRNAME


def resolve_shared_blocks_backup_root(
    tree_repository: TranslationTreeRepository,
    tree_dir: str | Path,
) -> Path:
    """Return the local backup directory for split shared-block files."""

    return tree_repository.path_service.backup_root(tree_dir) / SHARED_BLOCKS_DIRNAME


class SharedBlocksCatalogBuilder:
    """Build shared-block collaboration artifacts from the current tree and PO.

    Args:
        tree_repository: Translation tree repository used to scan the tree.
        source_lang: Source language code shown in the markdown.
        target_lang: Target language code shown in the markdown.
    """

    def __init__(
        self,
        tree_repository: TranslationTreeRepository,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
    ):
        self.tree_repository = tree_repository
        self.source_lang = source_lang
        self.target_lang = target_lang

    def build(
        self,
        tree_dir: str,
        original_po_path: str,
        output_shared_blocks_path: str,
    ) -> SharedBlocksBuildResult:
        """Build and persist the shared-block markdown file.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the shared-block source.
            output_shared_blocks_path: Destination markdown path.

        Returns:
            Shared-block build result.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        output_path = Path(output_shared_blocks_path)
        shared_blocks_root = resolve_shared_blocks_root_path(output_path)
        records = self._build_records(
            blocks=blocks,
            manifest=manifest,
            tree_dir=Path(tree_dir),
            output_path=output_path,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        written_paths = self._write_group_files(
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        markdown_text = self._render(records)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown_text, encoding="utf-8")
        written_paths.add(output_path)
        self._write_shared_blocks_backup(
            tree_dir=tree_dir,
            markdown_text=markdown_text,
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        return SharedBlocksBuildResult(
            markdown_text=markdown_text,
            output_shared_blocks=output_path,
            output_shared_blocks_root=shared_blocks_root,
            written_paths=tuple(sorted(written_paths, key=str)),
        )

    def build_directory(
        self,
        tree_dir: str,
        original_po_path: str,
        output_shared_blocks_root: str,
    ) -> SharedBlocksDirectoryBuildResult:
        """Build and persist only the canonical shared-block directory.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the shared-block source.
            output_shared_blocks_root: Destination shared-block directory path.

        Returns:
            Shared-block directory build result.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        shared_blocks_root = Path(output_shared_blocks_root)
        pseudo_index_path = shared_blocks_root.parent / SHARED_BLOCKS_FILENAME
        records = self._build_records(
            blocks=blocks,
            manifest=manifest,
            tree_dir=Path(tree_dir),
            output_path=pseudo_index_path,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        written_paths = self._write_group_files(
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        self._write_shared_blocks_backup(
            tree_dir=tree_dir,
            markdown_text=None,
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        return SharedBlocksDirectoryBuildResult(
            output_shared_blocks_root=shared_blocks_root,
            written_paths=tuple(sorted(written_paths, key=str)),
        )

    def build_outline(
        self,
        tree_dir: str,
        original_po_path: str,
        output_shared_blocks_outline_path: str,
    ) -> SharedBlocksOutlineBuildResult:
        """Build and persist the shared-block outline markdown file.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the shared-block source.
            output_shared_blocks_outline_path: Destination markdown path.

        Returns:
            Shared-block outline build result.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        output_path = Path(output_shared_blocks_outline_path)
        records = self._build_records(
            blocks=blocks,
            manifest=manifest,
            tree_dir=Path(tree_dir),
            output_path=output_path,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        markdown_text = self._render_outline(records, output_path=output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown_text, encoding="utf-8")
        return SharedBlocksOutlineBuildResult(
            markdown_text=markdown_text,
            output_shared_blocks_outline=output_path,
        )

    def _build_records(
        self,
        blocks: list[PoBlock],
        manifest: dict[str, Any],
        tree_dir: Path,
        output_path: Path,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> list[SharedBlockRecord]:
        """Build shared-block records from parsed PO blocks."""

        manifest_nodes = manifest.get("nodes", {})
        if not isinstance(manifest_nodes, dict):
            raise ValueError("Tree manifest nodes must be a dictionary")
        path_to_uuid, children_by_uuid = self._build_relation_indexes(manifest_nodes)

        records: list[SharedBlockRecord] = []
        for block in blocks:
            if len(block.references) < 2:
                continue
            contexts = tuple(
                self._build_context(
                    reference=reference,
                    tree_dir=tree_dir,
                    output_path=output_path,
                    manifest_nodes=manifest_nodes,
                    children_by_uuid=children_by_uuid,
                    folders_by_uuid=folders_by_uuid,
                )
                for reference in block.references
            )
            records.append(
                SharedBlockRecord(
                    group_key=tuple(
                        (reference.uuid, reference.field) for reference in block.references
                    ),
                    source_text=block.msgid,
                    translation_text=self._resolve_translation_text(
                        block=block,
                        folders_by_uuid=folders_by_uuid,
                    ),
                    contexts=contexts,
                    stable_id=SharedBlocksCatalogParser.stable_group_id(
                        tuple((reference.uuid, reference.field) for reference in block.references)
                    ),
                )
            )

        return records

    def _resolve_translation_text(
        self,
        block: PoBlock,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> str:
        """Select the current canonical translation for one shared block."""

        candidates: list[tuple[float, str, str]] = []
        for reference in block.references:
            snapshot = folders_by_uuid.get(reference.uuid)
            if snapshot is None:
                continue
            state = snapshot.fields.get(reference.field)
            if state is None:
                continue
            candidates.append(
                (
                    snapshot.field_modified_at.get(reference.field, snapshot.modified_at),
                    snapshot.path,
                    state.target_text,
                )
            )
        if not candidates:
            return block.msgstr
        candidates.sort(reverse=True)
        return candidates[0][2]

    def _build_context(
        self,
        reference: PoReference,
        tree_dir: Path,
        output_path: Path,
        manifest_nodes: dict[str, Any],
        children_by_uuid: dict[str, tuple[str, ...]],
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> SharedBlockContext:
        """Build one linked context for a shared block."""

        node = manifest_nodes.get(reference.uuid, {})
        relative_node_path = str(node.get("path", ""))
        snapshot = folders_by_uuid.get(reference.uuid)
        link_target = (
            snapshot.translation_path
            if snapshot is not None and snapshot.translation_path is not None
            else tree_dir / relative_node_path / UUID_FILENAME
        )
        relative_link = os.path.relpath(link_target, output_path.parent)
        label = self._display_label(relative_node_path or reference.uuid)
        badge = TranslationOutlineRenderer.event_type_badge(node.get("eventType"))
        context_label = self._build_context_label(
            entity_uuid=reference.uuid,
            relative_node_path=relative_node_path,
            children_by_uuid=children_by_uuid,
            manifest_nodes=manifest_nodes,
        )
        return SharedBlockContext(
            reference=reference,
            badge=badge,
            label=label,
            relative_link=relative_link,
            context_label=context_label,
        )

    def _render(self, records: list[SharedBlockRecord]) -> str:
        """Render the generated shared-block index markdown."""

        lines = [
            "# Shared Blocks",
            "",
            (
                "This file is generated. Edit shared translations in "
                f"`{SHARED_BLOCKS_DIRNAME}/<group-id>/{SHARED_BLOCK_CONTEXT_FILENAME}`."
            ),
            "",
        ]

        for index, record in enumerate(records, start=1):
            checkbox = "x" if record.is_translated else " "
            context_link = TranslationOutlineRenderer.format_link_destination(
                f"{SHARED_BLOCKS_DIRNAME}/{record.stable_id}/{SHARED_BLOCK_CONTEXT_FILENAME}"
            )
            source_preview = self._escape_markdown_link_text(self._preview_text(record.source_text))
            lines.extend(
                [
                    f"## Group {index:04d}",
                    "",
                    f"- Status: [{checkbox}]",
                    f"- [Open context]({context_link})",
                    f"- {source_preview}",
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    def _render_outline(
        self,
        records: list[SharedBlockRecord],
        output_path: Path,
    ) -> str:
        """Render shared-block records into compact overview markdown."""

        indexed_records = list(enumerate(records, start=1))
        translated_count = sum(1 for _, record in indexed_records if record.is_translated)
        untranslated_count = len(indexed_records) - translated_count
        lines = [
            "# Shared Blocks Outline",
            "",
            (
                "Review shared translation progress here. Edit the actual shared"
                f" translations in `{SHARED_BLOCKS_DIRNAME}/`."
            ),
            "",
            f"- Total groups: `{len(records)}`",
            f"- Untranslated: `{untranslated_count}`",
            f"- Translated: `{translated_count}`",
            "",
        ]
        self._render_outline_section(lines, indexed_records, output_path=output_path)
        return "\n".join(lines).rstrip() + "\n"

    def _render_outline_section(
        self,
        lines: list[str],
        indexed_records: list[tuple[int, SharedBlockRecord]],
        output_path: Path,
    ) -> None:
        """Render the shared-block outline in stable group order."""

        for group_index, record in indexed_records:
            checkbox = "x" if record.is_translated else " "
            context_relative_path = os.path.relpath(
                output_path.parent / SHARED_BLOCKS_DIRNAME / record.stable_id / SHARED_BLOCK_CONTEXT_FILENAME,
                output_path.parent,
            )
            translation_destination = TranslationOutlineRenderer.format_link_destination(
                context_relative_path
            )
            source_preview = self._escape_markdown_link_text(self._preview_text(record.source_text))
            lines.append(f"- [{checkbox}] Group {group_index:04d}")
            lines.append("")
            lines.append(f"  [{source_preview}]({translation_destination})")
            lines.append("")

    def _write_group_files(
        self,
        shared_blocks_root: Path,
        records: list[SharedBlockRecord],
    ) -> set[Path]:
        """Write canonical per-group shared-block files.

        Args:
            shared_blocks_root: Canonical shared-block directory root.
            records: Shared-block records to persist.

        Returns:
            Set of generated file paths.
        """

        shared_blocks_root.mkdir(parents=True, exist_ok=True)
        expected_group_ids = {record.stable_id for record in records}
        self._prune_stale_group_paths(shared_blocks_root, expected_group_ids)

        written_paths: set[Path] = set()
        for group_index, record in enumerate(records, start=1):
            group_dir = shared_blocks_root / record.stable_id
            group_dir.mkdir(parents=True, exist_ok=True)
            self._prune_stale_group_member_paths(group_dir)

            context_path = group_dir / SHARED_BLOCK_CONTEXT_FILENAME
            context_path.write_text(
                self._render_group_context(
                    group_index=group_index,
                    record=record,
                    shared_blocks_root=shared_blocks_root,
                ),
                encoding="utf-8",
            )
            written_paths.add(context_path)
        return written_paths

    def _render_group_context(
        self,
        group_index: int,
        record: SharedBlockRecord,
        shared_blocks_root: Path,
    ) -> str:
        """Render one generated shared-block context markdown file."""

        lines = [
            f"# Group {group_index:04d}",
            "",
            (
                f"> Edit only the `Translation ({self.target_lang})` block below. "
                "Other sections are generated."
            ),
            "",
            f"- Status: [{'x' if record.is_translated else ' '}]",
            f"- Stable ID: `{record.stable_id}`",
            (
                "- Shared Key: "
                f"`{SharedBlocksCatalogParser.serialize_group_key(record.group_key)}`"
            ),
            "",
            f"### Source ({self.source_lang})",
            "",
            "~~~text",
            record.source_text,
            "~~~",
            "",
            f"### Translation ({self.target_lang})",
            "",
            "~~~text",
            record.translation_text,
            "~~~",
            "",
            "### Contexts",
            "",
        ]
        group_dir = shared_blocks_root / record.stable_id
        for context in record.contexts:
            link_label = self._escape_markdown_link_text(context.label)
            tree_root_relative_link = shared_blocks_root.parent / context.relative_link
            context_relative_link = os.path.relpath(tree_root_relative_link, group_dir)
            formatted_link = TranslationOutlineRenderer.format_link_destination(
                context_relative_link
            )
            lines.extend(
                [
                    f"- {context.badge} [{link_label}]({formatted_link})",
                    f"  Context: {context.context_label} [{context.reference.field}]",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _prune_stale_group_paths(shared_blocks_root: Path, expected_group_ids: set[str]) -> None:
        """Remove stale generated group directories from the canonical root."""

        for child in shared_blocks_root.iterdir():
            if child.name in expected_group_ids:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    @staticmethod
    def _prune_stale_group_member_paths(group_dir: Path) -> None:
        """Remove unexpected generated files from one group directory."""

        expected_names = {
            SHARED_BLOCK_CONTEXT_FILENAME,
        }
        for child in group_dir.iterdir():
            if child.name in expected_names:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    @staticmethod
    def _preview_text(value: str, limit: int = 100) -> str:
        """Return a single-line preview for one shared source string."""

        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    @staticmethod
    def _build_relation_indexes(
        manifest_nodes: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
        """Build path and child indexes for manifest nodes.

        Args:
            manifest_nodes: Manifest node mapping keyed by UUID.

        Returns:
            Tuple of `(path_to_uuid, children_by_uuid)`.
        """

        path_to_uuid: dict[str, str] = {}
        children_by_uuid: dict[str, list[str]] = {}
        for entity_uuid, node in manifest_nodes.items():
            relative_path = str(node.get("path", ""))
            path_to_uuid[relative_path] = entity_uuid
            children_by_uuid.setdefault(entity_uuid, [])

        for entity_uuid, node in manifest_nodes.items():
            relative_path = str(node.get("path", ""))
            parent_path = str(Path(relative_path).parent)
            if parent_path == ".":
                continue
            parent_uuid = path_to_uuid.get(parent_path)
            if parent_uuid is None:
                continue
            children_by_uuid.setdefault(parent_uuid, []).append(entity_uuid)

        ordered_children: dict[str, tuple[str, ...]] = {}
        for entity_uuid, child_uuids in children_by_uuid.items():
            ordered_children[entity_uuid] = tuple(
                sorted(child_uuids, key=lambda child_uuid: str(manifest_nodes[child_uuid]["path"]))
            )
        return path_to_uuid, ordered_children

    @classmethod
    def _build_context_label(
        cls,
        entity_uuid: str,
        relative_node_path: str,
        children_by_uuid: dict[str, tuple[str, ...]],
        manifest_nodes: dict[str, Any],
    ) -> str:
        """Build a compact parent/self/child summary for one context.

        Args:
            entity_uuid: Node UUID represented by the context.
            relative_node_path: Relative tree path for the node.
            path_to_uuid: Mapping from manifest paths to UUIDs.
            children_by_uuid: Mapping from UUIDs to ordered child UUIDs.
            manifest_nodes: Manifest node mapping keyed by UUID.

        Returns:
            Compact context label that highlights the surrounding node chain.
        """

        current_path = Path(relative_node_path)
        labels: list[str] = []
        parent_path = str(current_path.parent)
        if parent_path != ".":
            labels.append(cls._display_label(parent_path))
        labels.append(cls._display_label(relative_node_path or entity_uuid))

        child_uuids = children_by_uuid.get(entity_uuid, ())
        if child_uuids:
            first_child_uuid = child_uuids[0]
            child_path = str(manifest_nodes[first_child_uuid]["path"])
            labels.append(cls._display_label(child_path))
        return " -> ".join(labels)

    @staticmethod
    def _display_label(relative_path: str) -> str:
        """Return a short display label for one tree path."""

        path_name = Path(relative_path).name
        without_order = SEGMENT_ORDER_RE.sub("", path_name)
        return SEGMENT_UUID_SUFFIX_RE.sub("", without_order)

    @classmethod
    def _humanize_path(cls, relative_path: str) -> str:
        """Return a human-readable path label without order/UUID noise."""

        parts = []
        for segment in Path(relative_path).parts:
            segment = SEGMENT_ORDER_RE.sub("", segment)
            segment = SEGMENT_UUID_SUFFIX_RE.sub("", segment)
            parts.append(segment)
        return " > ".join(parts)

    @staticmethod
    def _escape_markdown_link_text(value: str) -> str:
        """Escape markdown-sensitive link text characters."""

        return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")

    def _write_shared_blocks_backup(
        self,
        tree_dir: str | Path,
        markdown_text: str | None,
        shared_blocks_root: Path,
        records: list[SharedBlockRecord],
    ) -> None:
        """Persist last-known-good backups of shared-block artifacts.

        Args:
            tree_dir: Translation tree root directory.
            markdown_text: Optional generated shared-block index markdown.
            shared_blocks_root: Canonical shared-block directory root.
            records: Shared-block records used to populate the backup tree.
        """

        backup_path = resolve_shared_blocks_backup_path(
            tree_repository=self.tree_repository,
            tree_dir=tree_dir,
        )
        if markdown_text is not None:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(markdown_text, encoding="utf-8")
        backup_root = resolve_shared_blocks_backup_root(
            tree_repository=self.tree_repository,
            tree_dir=tree_dir,
        )
        backup_root.mkdir(parents=True, exist_ok=True)
        expected_group_ids = {record.stable_id for record in records}
        self._prune_stale_group_paths(backup_root, expected_group_ids)
        for group_index, record in enumerate(records, start=1):
            group_dir = backup_root / record.stable_id
            group_dir.mkdir(parents=True, exist_ok=True)
            self._prune_stale_group_member_paths(group_dir)
            (group_dir / SHARED_BLOCK_CONTEXT_FILENAME).write_text(
                self._render_group_context(
                    group_index=group_index,
                    record=record,
                    shared_blocks_root=shared_blocks_root,
                ),
                encoding="utf-8",
            )
