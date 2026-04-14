"""Translation tree repository and markdown document handling."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    MANIFEST_NAME,
    TRANSLATION_FILENAME,
    UUID_FILENAME,
)
from .data_models import (
    PoEntry,
    TranslationFieldState,
    TranslationStatusReport,
    TreeFolderSnapshot,
    TreeNode,
    TreeScanResult,
    TreeValidationResult,
)
from .tree_support import (
    TranslationBackupStore,
    TranslationFieldStateStore,
    TranslationMarkdownDocument,
    TranslationStatusCollector,
    TranslationTreePathService,
    TranslationTreeValidator,
    TreeDirectoryNamer,
    TreeFolderSnapshotBuilder,
)


class TranslationTreeRepository:
    """Read, write, and validate the translation tree on disk.

    Args:
        source_lang: Source language code.
        target_lang: Target language code.
        document: Optional injected markdown document helper.
        path_service: Optional injected tree path resolver.
        backup_store: Optional injected backup persistence service.
        field_state_store: Optional injected field metadata persistence service.
        directory_namer: Optional injected folder naming service.
        snapshot_builder: Optional injected folder snapshot builder.
        validator: Optional injected tree validation helper.
        status_collector: Optional injected tree status-report helper.
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
        document: TranslationMarkdownDocument | None = None,
        path_service: TranslationTreePathService | None = None,
        backup_store: TranslationBackupStore | None = None,
        field_state_store: TranslationFieldStateStore | None = None,
        directory_namer: TreeDirectoryNamer | None = None,
        snapshot_builder: TreeFolderSnapshotBuilder | None = None,
        validator: TranslationTreeValidator | None = None,
        status_collector: TranslationStatusCollector | None = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.document = document or TranslationMarkdownDocument(
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self.path_service = path_service or TranslationTreePathService()
        self.backup_store = backup_store or TranslationBackupStore(
            path_service=self.path_service,
            document=self.document,
        )
        self.field_state_store = field_state_store or TranslationFieldStateStore(
            path_service=self.path_service,
        )
        self.directory_namer = directory_namer or TreeDirectoryNamer()
        self.snapshot_builder = snapshot_builder or TreeFolderSnapshotBuilder(
            document=self.document,
            backup_store=self.backup_store,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )
        self.validator = validator or TranslationTreeValidator(
            target_lang=self.target_lang,
        )
        self.status_collector = status_collector or TranslationStatusCollector()

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
        shared_reference_keys: frozenset[tuple[str, str]] = frozenset(),
        preserve_existing_translations: bool = True,
    ) -> dict[str, Any]:
        """Export the in-memory tree structure to folders on disk.

        Args:
            out_dir: Output tree root directory.
            tree_roots: Root nodes to export.
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            model_name: Human-readable model name.
            shared_reference_keys: Shared `(uuid, field)` keys that should be
                edited in `shared_blocks.md`.
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
                shared_reference_keys=shared_reference_keys,
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
            snapshot = self.snapshot_builder.build_snapshot(
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

        self.field_state_store.refresh(tree_dir, folders_by_uuid)

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
        return self.validator.build_result(
            scan_result=scan_result,
            po_entries=po_entries,
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
        return self.status_collector.collect(
            manifest=manifest,
            scan_result=scan_result,
        )

    def write_snapshot(self, snapshot: TreeFolderSnapshot) -> None:
        """Write one folder snapshot back to `translation.md`.

        Args:
            snapshot: Snapshot to persist.
        """

        if snapshot.translation_path is None:
            return
        tree_root = self.path_service.resolve_tree_root_for_snapshot(snapshot)
        self._write_translation_markdown(
            tree_dir=str(tree_root),
            translation_path=snapshot.translation_path,
            entity_uuid=snapshot.entity_uuid,
            event_type=snapshot.event_type,
            fields=snapshot.fields,
            shared_fields=snapshot.shared_fields,
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
            self.path_service.ensure_uuid_file(
                folder_path=folder_path,
                entity_uuid=entity_uuid,
            )
            if not node.get("fields"):
                continue
            translation_path = folder_path / TRANSLATION_FILENAME
            if translation_path.exists():
                continue
            restored_path = self.backup_store.restore_translation_backup(
                translation_path=translation_path,
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
            )
            if restored_path is None:
                raise ValueError(
                    "Missing translation file and no valid backup was available.\n"
                    f"File: {translation_path}"
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
        shared_reference_keys: frozenset[tuple[str, str]],
    ) -> None:
        """Write one tree node and recursively write its children."""

        directory_name, name_source = self._build_directory_name(
            order_index=order_index,
            entity_uuid=node.entity_uuid,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
        )
        relative_path = (
            directory_name if not parent_dir else os.path.join(parent_dir, directory_name)
        )
        absolute_path = Path(out_dir) / relative_path
        absolute_path.mkdir(parents=True, exist_ok=True)
        (absolute_path / UUID_FILENAME).write_text(node.entity_uuid, encoding="utf-8")

        translation_fields = self._build_translation_fields(
            node=node,
            existing_snapshots=existing_snapshots,
        )
        shared_fields = tuple(
            self.document.sort_fields(
                field
                for field in translation_fields
                if (node.entity_uuid, field) in shared_reference_keys
            )
        )
        if translation_fields:
            translation_path = absolute_path / TRANSLATION_FILENAME
            self._write_translation_markdown(
                tree_dir=out_dir,
                translation_path=translation_path,
                entity_uuid=node.entity_uuid,
                event_type=node.event_type,
                fields=translation_fields,
                shared_fields=shared_fields,
            )

        manifest["nodes"][node.entity_uuid] = {
            "path": relative_path,
            "fields": self.document.sort_fields(translation_fields.keys()),
            "sharedFields": list(shared_fields),
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
                shared_reference_keys=shared_reference_keys,
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

    def _write_translation_markdown(
        self,
        tree_dir: str,
        translation_path: Path,
        entity_uuid: str,
        event_type: str | None,
        fields: dict[str, TranslationFieldState],
        shared_fields: Iterable[str] = (),
    ) -> None:
        """Write one translation markdown file and refresh its backup.

        Args:
            tree_dir: Translation tree root directory.
            translation_path: Destination translation markdown path.
            entity_uuid: UUID stored in the document header.
            event_type: Event type stored in the document header.
            fields: Translation fields to render and persist.
            shared_fields: Field names whose source of truth is
                `shared_blocks.md`.
        """

        markdown_text = self.document.render(
            entity_uuid=entity_uuid,
            event_type=event_type,
            fields=fields,
            shared_fields=shared_fields,
        )
        translation_path.write_text(markdown_text, encoding="utf-8")
        self.backup_store.write_backup_text(
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
            markdown_text=markdown_text,
        )

    def _build_directory_name(
        self,
        order_index: int,
        entity_uuid: str,
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build the final folder name for one node."""

        return self.directory_namer.build_directory_name(
            order_index=order_index,
            entity_uuid=entity_uuid,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
        )

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
