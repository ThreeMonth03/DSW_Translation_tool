"""Snapshot-building helpers for translation tree folders."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..constants import TRANSLATION_FILENAME, UUID_FILENAME
from ..data_models import TranslationFieldState, TreeFolderSnapshot
from .document import TranslationMarkdownDocument
from .storage import TranslationBackupStore


class TreeFolderSnapshotBuilder:
    """Build in-memory folder snapshots from on-disk tree folders.

    Args:
        document: Markdown document parser used for `translation.md`.
        backup_store: Backup store used for automatic recovery.
        source_lang: Source language code used by legacy split files.
        target_lang: Target language code used by markdown and legacy files.
    """

    def __init__(
        self,
        document: TranslationMarkdownDocument,
        backup_store: TranslationBackupStore,
        source_lang: str,
        target_lang: str,
    ):
        self.document = document
        self.backup_store = backup_store
        self.source_lang = source_lang
        self.target_lang = target_lang

    def build_snapshot(
        self,
        current_root: str,
        tree_dir: str,
        filenames: list[str],
        manifest: dict[str, Any] | None,
    ) -> TreeFolderSnapshot:
        """Build one folder snapshot from a tree directory.

        Args:
            current_root: Absolute directory path containing `_uuid.txt`.
            tree_dir: Translation tree root directory.
            filenames: Sorted filenames found in the folder.
            manifest: Parsed tree manifest, if available.

        Returns:
            Snapshot representing the current folder state.
        """

        uuid_path = Path(current_root) / UUID_FILENAME
        entity_uuid = uuid_path.read_text(encoding="utf-8").strip()
        translation_path = Path(current_root) / TRANSLATION_FILENAME
        modified_at = (
            translation_path.stat().st_mtime
            if translation_path.exists()
            else uuid_path.stat().st_mtime
        )
        fields = self.read_folder_fields(
            folder_path=Path(current_root),
            filenames=filenames,
            translation_path=translation_path,
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
        )
        return TreeFolderSnapshot(
            entity_uuid=entity_uuid,
            path=os.path.relpath(current_root, tree_dir),
            event_type=self.manifest_event_type(
                manifest=manifest,
                entity_uuid=entity_uuid,
            ),
            translation_path=translation_path if translation_path.exists() else None,
            modified_at=modified_at,
            fields=fields,
        )

    @staticmethod
    def manifest_event_type(
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

    def read_folder_fields(
        self,
        folder_path: Path,
        filenames: list[str],
        translation_path: Path,
        tree_dir: str,
        entity_uuid: str,
    ) -> dict[str, TranslationFieldState]:
        """Read either `translation.md` or the legacy split text files.

        Args:
            folder_path: Folder being scanned.
            filenames: Sorted filenames found in the folder.
            translation_path: Candidate markdown translation path.
            tree_dir: Translation tree root directory.
            entity_uuid: UUID represented by the folder.

        Returns:
            Parsed translation fields for the folder.
        """

        if translation_path.exists():
            return self.parse_translation_markdown(
                translation_path=translation_path,
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
            )
        return self.scan_legacy_split_files(folder_path, filenames)

    def parse_translation_markdown(
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
            backup_path = self.backup_store.restore_translation_backup(
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
        self.backup_store.write_backup_text(
            tree_dir=tree_dir,
            entity_uuid=entity_uuid,
            markdown_text=markdown_text,
        )
        return fields

    def scan_legacy_split_files(
        self,
        folder_path: Path,
        filenames: list[str],
    ) -> dict[str, TranslationFieldState]:
        """Read the previous split-file translation format for compatibility.

        Args:
            folder_path: Folder containing legacy split text files.
            filenames: Sorted filenames found in the folder.

        Returns:
            Parsed field mapping from the legacy format.
        """

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
