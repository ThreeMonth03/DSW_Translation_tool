"""Translation tree repository and markdown document handling."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    FIELD_EXPORT_ORDER,
    FIELD_STATE_FILENAME,
    MANIFEST_NAME,
    MAX_SEGMENT_TEXT_LENGTH,
    TRANSLATION_BACKUP_FILENAME,
    TRANSLATION_FILENAME,
    TREE_BACKUP_DIRNAME,
    UUID_FILENAME,
)
from .model import DswModelService
from .models import (
    PoEntry,
    TranslationFieldState,
    TranslationStatusFolder,
    TranslationStatusReport,
    TranslationStatusSummary,
    TreeFolderSnapshot,
    TreeNode,
    TreeScanResult,
    TreeValidationResult,
)


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
    ) -> str:
        """Render one node folder into markdown.

        Args:
            entity_uuid: UUID of the exported node.
            event_type: DSW event type for the node.
            fields: Translation fields to render.

        Returns:
            Rendered markdown content for `translation.md`.
        """

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
            lines.extend(
                [
                    f"## {field}",
                    "",
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
            message=(
                f"Missing opening fence for `{field_name}` {role_label} block."
            ),
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
                    (
                        f"Broken fence detected inside `{field_name}` "
                        f"{role_label} block."
                    ),
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

        raise ValueError(
            f"{markdown_path}: line {line_number}: {message}"
        )


class TranslationTreeRepository:
    """Read, write, and validate the translation tree on disk.

    Args:
        source_lang: Source language code.
        target_lang: Target language code.
        document: Optional injected markdown document helper.
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
        document: TranslationMarkdownDocument | None = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.document = document or TranslationMarkdownDocument(
            source_lang=source_lang,
            target_lang=target_lang,
        )

    def read_existing_manifest(self, out_dir: str) -> dict[str, Any] | None:
        """Read the translation tree manifest if it exists.

        Args:
            out_dir: Tree root directory.

        Returns:
            Parsed manifest dictionary or `None`.
        """

        manifest_path = Path(out_dir) / MANIFEST_NAME
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def remove_previous_export(self, out_dir: str) -> None:
        """Remove folders from a previous export using the manifest.

        Args:
            out_dir: Tree root directory.
        """

        manifest = self.read_existing_manifest(out_dir)
        if not manifest:
            return

        for relative_root in manifest.get("rootPaths", []):
            absolute_root = Path(out_dir) / relative_root
            if not absolute_root.is_dir():
                continue
            for current_root, dirnames, filenames in os.walk(
                absolute_root,
                topdown=False,
            ):
                for filename in filenames:
                    (Path(current_root) / filename).unlink()
                for dirname in dirnames:
                    (Path(current_root) / dirname).rmdir()
            absolute_root.rmdir()

        manifest_path = Path(out_dir) / MANIFEST_NAME
        if manifest_path.exists():
            manifest_path.unlink()

    def export_tree(
        self,
        out_dir: str,
        tree_roots: list[TreeNode],
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str,
        preserve_existing_translations: bool = True,
    ) -> dict[str, Any]:
        """Export the in-memory tree structure to folders on disk.

        Args:
            out_dir: Output tree root directory.
            tree_roots: Root nodes to export.
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            model_name: Human-readable model name.
            preserve_existing_translations: Whether to keep existing target
                text already present in the output tree.

        Returns:
            Manifest dictionary describing the exported tree.
        """

        output_dir = Path(out_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        existing_snapshots = self._load_existing_snapshots(
            out_dir=out_dir,
            preserve_existing_translations=preserve_existing_translations,
        )
        self.remove_previous_export(out_dir)

        manifest = self._create_manifest(model_name)
        for root_index, root in enumerate(tree_roots, start=1):
            directory_name, _ = self._build_directory_name(
                order_index=root_index,
                entity_uuid=root.entity_uuid,
                latest_by_uuid=latest_by_uuid,
                model_name=model_name,
            )
            manifest["rootPaths"].append(directory_name)
            self._write_node(
                node=root,
                parent_dir="",
                order_index=root_index,
                out_dir=out_dir,
                latest_by_uuid=latest_by_uuid,
                model_name=model_name,
                manifest=manifest,
                existing_snapshots=existing_snapshots,
            )

        manifest_path = output_dir / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def scan(self, tree_dir: str) -> TreeScanResult:
        """Scan a translation tree from disk.

        Args:
            tree_dir: Tree root directory.

        Returns:
            Parsed scan result for the tree.
        """

        self._heal_tree_from_manifest(tree_dir)
        manifest = self.read_existing_manifest(tree_dir)
        node_dirs: dict[str, str] = {}
        translations: dict[tuple[str, str], str] = {}
        duplicate_uuids: list[tuple[str, str, str]] = []
        folders_by_uuid: dict[str, TreeFolderSnapshot] = {}

        for current_root, filenames in self._iter_uuid_directories(tree_dir):
            snapshot = self._build_folder_snapshot(
                current_root=current_root,
                tree_dir=tree_dir,
                filenames=filenames,
                manifest=manifest,
            )
            if snapshot.entity_uuid in node_dirs:
                duplicate_uuids.append(
                    (
                        snapshot.entity_uuid,
                        node_dirs[snapshot.entity_uuid],
                        current_root,
                    )
                )
                continue

            node_dirs[snapshot.entity_uuid] = current_root
            for field, state in snapshot.fields.items():
                translations[(snapshot.entity_uuid, field)] = state.target_text
            folders_by_uuid[snapshot.entity_uuid] = snapshot

        self._refresh_field_state(tree_dir, folders_by_uuid)

        return TreeScanResult(
            manifest=manifest,
            node_dirs=node_dirs,
            translations=translations,
            duplicate_uuids=tuple(duplicate_uuids),
            folders_by_uuid=folders_by_uuid,
        )

    def validate(
        self,
        tree_dir: str,
        po_entries: list[PoEntry],
    ) -> TreeValidationResult:
        """Validate that the tree still matches the expected PO structure.

        Args:
            tree_dir: Tree root directory.
            po_entries: Flattened PO entries expected to exist in the tree.

        Returns:
            Tree validation result including scan data and errors.
        """

        scan_result = self.scan(tree_dir)
        errors = self._build_validation_errors(scan_result, po_entries)
        return TreeValidationResult(
            scan_result=scan_result,
            errors=tuple(errors),
        )

    def collect_status(self, tree_dir: str) -> TranslationStatusReport:
        """Collect translation progress information from the tree.

        Args:
            tree_dir: Tree root directory.

        Returns:
            Folder-by-folder translation status report.

        Raises:
            ValueError: If the tree manifest is missing.
        """

        manifest = self.read_existing_manifest(tree_dir)
        if not manifest:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}")

        scan_result = self.scan(tree_dir)
        folders: list[TranslationStatusFolder] = []
        summary = TranslationStatusSummary(
            total_nodes=len(manifest.get("nodes", {})),
            translatable_nodes=0,
            complete_folders=0,
            pending_folders=0,
            total_fields=0,
            translated_fields=0,
            untranslated_fields=0,
        )

        mutable_summary = summary.to_dict()
        for entity_uuid, node in manifest.get("nodes", {}).items():
            folder_status = self._build_folder_status(
                entity_uuid=entity_uuid,
                node=node,
                translations=scan_result.translations,
                summary=mutable_summary,
            )
            if folder_status is not None:
                folders.append(folder_status)

        return TranslationStatusReport(
            summary=TranslationStatusSummary(
                total_nodes=mutable_summary["totalNodes"],
                translatable_nodes=mutable_summary["translatableNodes"],
                complete_folders=mutable_summary["completeFolders"],
                pending_folders=mutable_summary["pendingFolders"],
                total_fields=mutable_summary["totalFields"],
                translated_fields=mutable_summary["translatedFields"],
                untranslated_fields=mutable_summary["untranslatedFields"],
            ),
            folders=tuple(folders),
        )

    def write_snapshot(self, snapshot: TreeFolderSnapshot) -> None:
        """Write one folder snapshot back to `translation.md`.

        Args:
            snapshot: Snapshot to persist.
        """

        if snapshot.translation_path is None:
            return
        tree_root = self._resolve_tree_root_for_snapshot(snapshot)
        self._write_translation_markdown(
            tree_dir=str(tree_root),
            translation_path=snapshot.translation_path,
            entity_uuid=snapshot.entity_uuid,
            event_type=snapshot.event_type,
            fields=snapshot.fields,
        )

    def _load_existing_snapshots(
        self,
        out_dir: str,
        preserve_existing_translations: bool,
    ) -> dict[str, TreeFolderSnapshot]:
        """Load existing folder snapshots when export should preserve text."""

        if not preserve_existing_translations or not Path(out_dir).is_dir():
            return {}
        return self.scan(out_dir).folders_by_uuid

    def _create_manifest(self, model_name: str) -> dict[str, Any]:
        """Create the base manifest structure for a new export."""

        return {
            "modelName": model_name,
            "sourceLang": self.source_lang,
            "targetLang": self.target_lang,
            "translationFile": TRANSLATION_FILENAME,
            "rootPaths": [],
            "nodes": {},
        }

    def _iter_uuid_directories(
        self,
        tree_dir: str,
    ) -> Iterable[tuple[str, list[str]]]:
        """Yield directories inside the tree that contain `_uuid.txt`."""

        for current_root, dirnames, filenames in os.walk(tree_dir):
            dirnames.sort()
            filenames.sort()
            if UUID_FILENAME in filenames:
                yield current_root, filenames

    def _build_folder_snapshot(
        self,
        current_root: str,
        tree_dir: str,
        filenames: list[str],
        manifest: dict[str, Any] | None,
    ) -> TreeFolderSnapshot:
        """Build one folder snapshot from a tree directory."""

        uuid_path = Path(current_root) / UUID_FILENAME
        entity_uuid = uuid_path.read_text(encoding="utf-8").strip()
        translation_path = Path(current_root) / TRANSLATION_FILENAME
        modified_at = (
            translation_path.stat().st_mtime
            if translation_path.exists()
            else uuid_path.stat().st_mtime
        )
        fields = self._read_folder_fields(
            folder_path=Path(current_root),
            filenames=filenames,
            translation_path=translation_path,
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
        )
        return TreeFolderSnapshot(
            entity_uuid=entity_uuid,
            path=os.path.relpath(current_root, tree_dir),
            event_type=self._manifest_event_type(
                manifest=manifest,
                entity_uuid=entity_uuid,
            ),
            translation_path=translation_path if translation_path.exists() else None,
            modified_at=modified_at,
            fields=fields,
        )

    @staticmethod
    def _manifest_event_type(
        manifest: dict[str, Any] | None,
        entity_uuid: str,
    ) -> str | None:
        """Return the manifest event type for one tree UUID.

        Args:
            manifest: Parsed tree manifest, if available.
            entity_uuid: UUID stored in the current node folder.

        Returns:
            Event type from the manifest when present, otherwise `None`.
        """

        if manifest is None:
            return None
        nodes = manifest.get("nodes", {})
        if not isinstance(nodes, dict):
            return None
        node = nodes.get(entity_uuid)
        if not isinstance(node, dict):
            return None
        event_type = node.get("eventType")
        return event_type if isinstance(event_type, str) else None

    def _read_folder_fields(
        self,
        folder_path: Path,
        filenames: list[str],
        translation_path: Path,
        tree_dir: str,
        entity_uuid: str,
    ) -> dict[str, TranslationFieldState]:
        """Read either `translation.md` or the legacy split text files."""

        if translation_path.exists():
            return self._parse_translation_markdown(
                translation_path=translation_path,
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
            )
        return self._scan_legacy_split_files(folder_path, filenames)

    def _parse_translation_markdown(
        self,
        translation_path: Path,
        tree_dir: str,
        entity_uuid: str,
    ) -> dict[str, TranslationFieldState]:
        """Parse one translation markdown file with backup recovery.

        Args:
            translation_path: Markdown file path to parse.
            tree_dir: Translation tree root directory.
            entity_uuid: UUID represented by the markdown file.

        Returns:
            Parsed field states from the markdown file.

        Raises:
            ValueError: If the markdown file is invalid.
        """

        markdown_text = translation_path.read_text(encoding="utf-8")
        try:
            fields = self.document.parse_text(markdown_text, str(translation_path))
        except ValueError as error:
            backup_path = self._restore_translation_backup(
                translation_path=translation_path,
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
            )
            if backup_path is not None:
                raise ValueError(
                    "Invalid translation file was restored from the last "
                    f"known-good backup.\nFile: {translation_path}\n"
                    f"Backup: {backup_path}\nReason: {error}"
                ) from error
            raise ValueError(
                "Invalid translation file and no valid backup was available.\n"
                f"File: {translation_path}\nReason: {error}"
            ) from error
        self._write_backup_text(
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
            markdown_text=markdown_text,
        )
        return fields

    def _restore_translation_backup(
        self,
        translation_path: Path,
        tree_dir: str,
        entity_uuid: str,
    ) -> Path | None:
        """Restore one invalid translation file from its last good backup.

        Args:
            translation_path: Invalid translation markdown path.
            tree_dir: Translation tree root directory.
            entity_uuid: UUID represented by the markdown file.

        Returns:
            Backup path when restoration succeeded, otherwise `None`.
        """

        for backup_path in self._candidate_backup_paths(
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
            translation_path=translation_path,
        ):
            if not backup_path.exists():
                continue
            backup_text = backup_path.read_text(encoding="utf-8")
            self.document.parse_text(backup_text, str(backup_path))
            translation_path.parent.mkdir(parents=True, exist_ok=True)
            translation_path.write_text(backup_text, encoding="utf-8")
            self._write_backup_text(
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
                markdown_text=backup_text,
            )
            return backup_path
        return None

    def _heal_tree_from_manifest(self, tree_dir: str) -> None:
        """Restore missing node folders and files from manifest and backups.

        Args:
            tree_dir: Translation tree root directory.

        Raises:
            ValueError: If a missing translation file cannot be restored.
        """

        manifest = self.read_existing_manifest(tree_dir)
        if not manifest:
            return

        for entity_uuid, node in manifest.get("nodes", {}).items():
            folder_path = Path(tree_dir) / node["path"]
            folder_path.mkdir(parents=True, exist_ok=True)
            self._ensure_uuid_file(folder_path=folder_path, entity_uuid=entity_uuid)
            if not node.get("fields"):
                continue
            translation_path = folder_path / TRANSLATION_FILENAME
            if translation_path.exists():
                continue
            restored_path = self._restore_translation_backup(
                translation_path=translation_path,
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
            )
            if restored_path is None:
                raise ValueError(
                    "Missing translation file and no valid backup was available.\n"
                    f"File: {translation_path}"
                )

    @staticmethod
    def _ensure_uuid_file(folder_path: Path, entity_uuid: str) -> None:
        """Ensure that `_uuid.txt` exists and matches the manifest UUID."""

        uuid_path = folder_path / UUID_FILENAME
        current_value = uuid_path.read_text(encoding="utf-8").strip() if uuid_path.exists() else None
        if current_value == entity_uuid:
            return
        uuid_path.write_text(entity_uuid, encoding="utf-8")

    def _build_validation_errors(
        self,
        scan_result: TreeScanResult,
        po_entries: list[PoEntry],
    ) -> list[str]:
        """Build a list of validation errors for the scanned tree."""

        errors: list[str] = []
        errors.extend(self._build_duplicate_uuid_errors(scan_result.duplicate_uuids))
        errors.extend(
            self._build_manifest_node_errors(
                manifest=scan_result.manifest,
                node_dirs=scan_result.node_dirs,
            )
        )
        errors.extend(
            self._build_missing_field_errors(
                po_entries=po_entries,
                node_dirs=scan_result.node_dirs,
                translations=scan_result.translations,
            )
        )
        return errors

    @staticmethod
    def _build_duplicate_uuid_errors(
        duplicate_uuids: tuple[tuple[str, str, str], ...],
    ) -> list[str]:
        """Create error messages for duplicate UUID folders."""

        return [
            (
                "Duplicate UUID folder detected for "
                f"{entity_uuid}: {first_path} and {second_path}"
            )
            for entity_uuid, first_path, second_path in duplicate_uuids
        ]

    @staticmethod
    def _build_manifest_node_errors(
        manifest: dict[str, Any] | None,
        node_dirs: dict[str, str],
    ) -> list[str]:
        """Create error messages for manifest-to-disk UUID mismatches."""

        if not manifest:
            return []

        expected_nodes = set(manifest.get("nodes", {}).keys())
        actual_nodes = set(node_dirs.keys())
        missing_nodes = sorted(expected_nodes - actual_nodes)[:50]
        unexpected_nodes = sorted(actual_nodes - expected_nodes)[:50]
        return [
            *(f"Missing UUID folder: {uuid}" for uuid in missing_nodes),
            *(f"Unexpected UUID folder: {uuid}" for uuid in unexpected_nodes),
        ]

    def _build_missing_field_errors(
        self,
        po_entries: list[PoEntry],
        node_dirs: dict[str, str],
        translations: dict[tuple[str, str], str],
    ) -> list[str]:
        """Create error messages for missing translation fields."""

        expected_fields_by_uuid: dict[str, set[str]] = {}
        for entry in po_entries:
            expected_fields_by_uuid.setdefault(entry.uuid, set()).add(entry.field)

        errors: list[str] = []
        for entity_uuid, fields in sorted(expected_fields_by_uuid.items()):
            folder_path = node_dirs.get(entity_uuid)
            if folder_path is None:
                continue
            for field in sorted(fields):
                if (entity_uuid, field) in translations:
                    continue
                translation_markdown_path = Path(folder_path) / TRANSLATION_FILENAME
                if translation_markdown_path.exists():
                    errors.append(
                        f"Missing translation block: {translation_markdown_path} -> {field}"
                    )
                    continue
                expected_path = Path(folder_path) / f"{field}.{self.target_lang}.txt"
                errors.append(f"Missing translation file: {expected_path}")
        return errors

    def _build_folder_status(
        self,
        entity_uuid: str,
        node: dict[str, Any],
        translations: dict[tuple[str, str], str],
        summary: dict[str, int],
    ) -> TranslationStatusFolder | None:
        """Build one folder status entry and update summary counters."""

        fields = tuple(node["fields"])
        if not fields:
            return None

        summary["translatableNodes"] += 1
        untranslated_fields: list[str] = []
        translated_fields: list[str] = []

        for field in fields:
            summary["totalFields"] += 1
            target_text = translations.get((entity_uuid, field))
            if target_text is None or not target_text.strip():
                untranslated_fields.append(field)
                summary["untranslatedFields"] += 1
            else:
                translated_fields.append(field)
                summary["translatedFields"] += 1

        if untranslated_fields:
            summary["pendingFolders"] += 1
        else:
            summary["completeFolders"] += 1

        return TranslationStatusFolder(
            uuid=entity_uuid,
            path=node["path"],
            event_type=node["eventType"],
            untranslated_fields=tuple(untranslated_fields),
            translated_fields=tuple(translated_fields),
        )

    def _write_node(
        self,
        node: TreeNode,
        parent_dir: str,
        order_index: int,
        out_dir: str,
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str,
        manifest: dict[str, Any],
        existing_snapshots: dict[str, TreeFolderSnapshot],
    ) -> None:
        """Write one tree node and recursively write its children."""

        directory_name, name_source = self._build_directory_name(
            order_index=order_index,
            entity_uuid=node.entity_uuid,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
        )
        relative_path = (
            directory_name
            if not parent_dir
            else os.path.join(parent_dir, directory_name)
        )
        absolute_path = Path(out_dir) / relative_path
        absolute_path.mkdir(parents=True, exist_ok=True)
        (absolute_path / UUID_FILENAME).write_text(node.entity_uuid, encoding="utf-8")

        translation_fields = self._build_translation_fields(
            node=node,
            existing_snapshots=existing_snapshots,
        )
        if translation_fields:
            translation_path = absolute_path / TRANSLATION_FILENAME
            self._write_translation_markdown(
                tree_dir=out_dir,
                translation_path=translation_path,
                entity_uuid=node.entity_uuid,
                event_type=node.event_type,
                fields=translation_fields,
            )

        manifest["nodes"][node.entity_uuid] = {
            "path": relative_path,
            "fields": self.document.sort_fields(translation_fields.keys()),
            "eventType": node.event_type,
            "nameSource": name_source,
        }

        for child_index, child in enumerate(node.children, start=1):
            self._write_node(
                node=child,
                parent_dir=relative_path,
                order_index=child_index,
                out_dir=out_dir,
                latest_by_uuid=latest_by_uuid,
                model_name=model_name,
                manifest=manifest,
                existing_snapshots=existing_snapshots,
            )

    def _build_translation_fields(
        self,
        node: TreeNode,
        existing_snapshots: dict[str, TreeFolderSnapshot],
    ) -> dict[str, TranslationFieldState]:
        """Merge exported field values with preserved target translations."""

        fields = self._map_field_values(node)
        translation_fields: dict[str, TranslationFieldState] = {}
        existing_snapshot = existing_snapshots.get(node.entity_uuid)

        for field in self.document.sort_fields(fields.keys()):
            state = fields[field]
            preserved_target = ""
            if existing_snapshot and field in existing_snapshot.fields:
                preserved_target = existing_snapshot.fields[field].target_text
            translation_fields[field] = TranslationFieldState(
                source_text=state.source_text,
                target_text=preserved_target or state.target_text,
            )
        return translation_fields

    @staticmethod
    def _map_field_values(node: TreeNode) -> dict[str, TranslationFieldState]:
        """Collapse duplicate PO references to one field entry per node."""

        fields: dict[str, TranslationFieldState] = {}
        for ref in node.po_refs:
            if ref.field not in fields:
                fields[ref.field] = TranslationFieldState(
                    source_text=ref.msgid,
                    target_text=ref.msgstr,
                )
        return fields

    @staticmethod
    def _sanitize_path_text(value: str) -> str:
        """Remove path-unsafe characters from a directory name."""

        sanitized = value
        for source, replacement in (
            ("/", " "),
            ("\\", " "),
            (":", " - "),
            ("*", " "),
            ("?", ""),
            ('"', ""),
            ("<", ""),
            (">", ""),
            ("|", " "),
        ):
            sanitized = sanitized.replace(source, replacement)
        sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
        return sanitized or "Untitled"

    def _resolve_tree_root_for_snapshot(self, snapshot: TreeFolderSnapshot) -> Path:
        """Resolve the translation tree root for one persisted snapshot.

        Args:
            snapshot: Snapshot being written back to disk.

        Returns:
            Resolved tree root path for the snapshot.
        """

        if snapshot.translation_path is None:
            raise ValueError(
                f"Snapshot {snapshot.entity_uuid} does not have a translation file."
            )
        manifest_root = self._find_tree_root(snapshot.translation_path.parent)
        if manifest_root is not None:
            return manifest_root

        tree_root = snapshot.translation_path.parent
        for _ in Path(snapshot.path).parts:
            tree_root = tree_root.parent
        return tree_root

    @staticmethod
    def _find_tree_root(start_path: Path) -> Path | None:
        """Find the nearest ancestor that contains the tree manifest."""

        for candidate in (start_path, *start_path.parents):
            if (candidate / MANIFEST_NAME).exists():
                return candidate
        return None

    def _backup_root(self, tree_dir: str | Path) -> Path:
        """Return the central backup root for one translation tree."""

        tree_path = Path(tree_dir)
        return tree_path.parent / TREE_BACKUP_DIRNAME / tree_path.name

    def _field_state_path(self, tree_dir: str | Path) -> Path:
        """Return the per-field local state file for one translation tree."""

        return self._backup_root(tree_dir) / FIELD_STATE_FILENAME

    def _load_field_state(
        self,
        tree_dir: str | Path,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Load per-field edit timestamps from the local state file.

        Args:
            tree_dir: Translation tree root directory.

        Returns:
            Nested state keyed by UUID and field name.
        """

        state_path = self._field_state_path(tree_dir)
        if not state_path.exists():
            return {}
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        normalized_state: dict[str, dict[str, dict[str, Any]]] = {}
        for entity_uuid, fields in data.items():
            if not isinstance(entity_uuid, str) or not isinstance(fields, dict):
                continue
            normalized_fields: dict[str, dict[str, Any]] = {}
            for field_name, field_state in fields.items():
                if not isinstance(field_name, str) or not isinstance(field_state, dict):
                    continue
                normalized_fields[field_name] = field_state
            normalized_state[entity_uuid] = normalized_fields
        return normalized_state

    def _save_field_state(
        self,
        tree_dir: str | Path,
        state: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        """Persist per-field edit timestamps to the local state file.

        Args:
            tree_dir: Translation tree root directory.
            state: Nested state keyed by UUID and field name.
        """

        state_path = self._field_state_path(tree_dir)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _refresh_field_state(
        self,
        tree_dir: str,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> None:
        """Refresh local per-field edit metadata from the current tree state.

        Args:
            tree_dir: Translation tree root directory.
            folders_by_uuid: Parsed folder snapshots keyed by UUID.
        """

        state = self._load_field_state(tree_dir)
        changed = False
        active_uuids = set(folders_by_uuid)

        for entity_uuid, snapshot in folders_by_uuid.items():
            snapshot.field_modified_at = {}
            if not snapshot.fields:
                if entity_uuid in state:
                    del state[entity_uuid]
                    changed = True
                continue

            field_state = state.get(entity_uuid)
            if not isinstance(field_state, dict):
                field_state = {}
                state[entity_uuid] = field_state
                changed = True

            current_fields = set(snapshot.fields)
            stale_fields = set(field_state) - current_fields
            if stale_fields:
                for field_name in stale_fields:
                    del field_state[field_name]
                changed = True

            for field_name, translation_state in snapshot.fields.items():
                recorded_state = field_state.get(field_name)
                recorded_target = None
                recorded_edited_at = snapshot.modified_at

                if isinstance(recorded_state, dict):
                    recorded_target = recorded_state.get("targetText")
                    try:
                        recorded_edited_at = float(recorded_state.get("editedAt"))
                    except (TypeError, ValueError):
                        recorded_edited_at = snapshot.modified_at

                if recorded_target != translation_state.target_text:
                    recorded_edited_at = snapshot.modified_at
                    field_state[field_name] = {
                        "targetText": translation_state.target_text,
                        "editedAt": recorded_edited_at,
                    }
                    changed = True
                elif not isinstance(recorded_state, dict):
                    field_state[field_name] = {
                        "targetText": translation_state.target_text,
                        "editedAt": recorded_edited_at,
                    }
                    changed = True

                snapshot.field_modified_at[field_name] = recorded_edited_at

        stale_uuids = set(state) - active_uuids
        if stale_uuids:
            for entity_uuid in stale_uuids:
                del state[entity_uuid]
            changed = True

        if changed:
            self._save_field_state(tree_dir, state)

    def _central_backup_path(self, tree_dir: str | Path, entity_uuid: str) -> Path:
        """Return the central backup path for one node translation file."""

        return self._backup_root(tree_dir) / f"{entity_uuid}.{TRANSLATION_FILENAME}.bak"

    @staticmethod
    def _legacy_backup_path(translation_path: Path) -> Path:
        """Return the legacy in-folder backup path for one translation file."""

        return translation_path.parent / TRANSLATION_BACKUP_FILENAME

    def _candidate_backup_paths(
        self,
        tree_dir: str,
        entity_uuid: str,
        translation_path: Path,
    ) -> tuple[Path, ...]:
        """Return backup locations to try when restoring a translation file."""

        return (
            self._central_backup_path(tree_dir, entity_uuid),
            self._legacy_backup_path(translation_path),
        )

    def _write_backup_text(
        self,
        tree_dir: str,
        entity_uuid: str,
        markdown_text: str,
    ) -> None:
        """Write one central translation backup file.

        Args:
            tree_dir: Translation tree root directory.
            entity_uuid: UUID represented by the markdown file.
            markdown_text: Valid markdown content to persist as backup.
        """

        backup_path = self._central_backup_path(tree_dir, entity_uuid)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(markdown_text, encoding="utf-8")

    def _write_translation_markdown(
        self,
        tree_dir: str,
        translation_path: Path,
        entity_uuid: str,
        event_type: str | None,
        fields: dict[str, TranslationFieldState],
    ) -> None:
        """Write one translation markdown file and refresh its backup.

        Args:
            tree_dir: Translation tree root directory.
            translation_path: Destination translation markdown path.
            entity_uuid: UUID stored in the document header.
            event_type: Event type stored in the document header.
            fields: Translation fields to render and persist.
        """

        markdown_text = self.document.render(
            entity_uuid=entity_uuid,
            event_type=event_type,
            fields=fields,
        )
        translation_path.write_text(markdown_text, encoding="utf-8")
        self._write_backup_text(
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
            markdown_text=markdown_text,
        )

    @staticmethod
    def _truncate_path_text(
        value: str,
        max_length: int = MAX_SEGMENT_TEXT_LENGTH,
    ) -> str:
        """Truncate long directory names while keeping them readable."""

        if len(value) <= max_length:
            return value
        shortened = value[: max_length - 3].rstrip()
        if " " in shortened:
            shortened = shortened.rsplit(" ", 1)[0]
        shortened = shortened.rstrip(" .-_")
        fallback = shortened or value[: max_length - 3]
        return fallback.rstrip() + "..."

    def _build_directory_name(
        self,
        order_index: int,
        entity_uuid: str,
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build the final folder name for one node."""

        raw_name, name_source = DswModelService.resolve_node_display_name(
            entity_uuid,
            latest_by_uuid,
            model_name=model_name,
        )
        safe_name = self._truncate_path_text(self._sanitize_path_text(raw_name))
        return f"{order_index:04d} {safe_name} [{entity_uuid[:8]}]", name_source

    def _scan_legacy_split_files(
        self,
        folder_path: Path,
        filenames: list[str],
    ) -> dict[str, TranslationFieldState]:
        """Read the previous split-file translation format for compatibility."""

        fields: dict[str, TranslationFieldState] = {}
        target_suffix = f".{self.target_lang}.txt"
        source_suffix = f".{self.source_lang}.txt"

        for filename in filenames:
            if not filename.endswith(target_suffix):
                continue
            field = filename[: -len(target_suffix)]
            source_text = ""
            source_path = folder_path / f"{field}{source_suffix}"
            target_path = folder_path / filename
            if source_path.exists():
                source_text = source_path.read_text(encoding="utf-8")
            fields[field] = TranslationFieldState(
                source_text=source_text,
                target_text=target_path.read_text(encoding="utf-8"),
            )
        return fields
