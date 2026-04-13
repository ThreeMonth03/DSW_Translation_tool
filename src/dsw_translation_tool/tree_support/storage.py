"""Storage helpers for translation tree backups, paths, and field state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..constants import (
    FIELD_STATE_FILENAME,
    MANIFEST_NAME,
    TRANSLATION_BACKUP_FILENAME,
    TRANSLATION_FILENAME,
    TREE_BACKUP_DIRNAME,
    UUID_FILENAME,
)
from ..data_models import TreeFolderSnapshot
from .document import TranslationMarkdownDocument


class TranslationTreePathService:
    """Resolve canonical paths associated with one translation tree."""

    @staticmethod
    def find_tree_root(start_path: Path) -> Path | None:
        """Find the nearest ancestor that contains the tree manifest.

        Args:
            start_path: Starting directory or file parent to inspect.

        Returns:
            Tree root path when found, otherwise `None`.
        """

        for candidate in (start_path, *start_path.parents):
            if (candidate / MANIFEST_NAME).exists():
                return candidate
        return None

    def resolve_tree_root_for_snapshot(self, snapshot: TreeFolderSnapshot) -> Path:
        """Resolve the translation tree root for one persisted snapshot.

        Args:
            snapshot: Snapshot being written back to disk.

        Returns:
            Resolved tree root path for the snapshot.
        """

        if snapshot.translation_path is None:
            raise ValueError(f"Snapshot {snapshot.entity_uuid} does not have a translation file.")
        manifest_root = self.find_tree_root(snapshot.translation_path.parent)
        if manifest_root is not None:
            return manifest_root

        tree_root = snapshot.translation_path.parent
        for _ in Path(snapshot.path).parts:
            tree_root = tree_root.parent
        return tree_root

    @staticmethod
    def ensure_uuid_file(folder_path: Path, entity_uuid: str) -> None:
        """Ensure that `_uuid.txt` exists and matches the manifest UUID.

        Args:
            folder_path: Node folder path.
            entity_uuid: UUID expected from the manifest.
        """

        uuid_path = folder_path / UUID_FILENAME
        current_value = (
            uuid_path.read_text(encoding="utf-8").strip() if uuid_path.exists() else None
        )
        if current_value == entity_uuid:
            return
        uuid_path.write_text(entity_uuid, encoding="utf-8")

    @staticmethod
    def backup_root(tree_dir: str | Path) -> Path:
        """Return the central backup root for one translation tree.

        Args:
            tree_dir: Translation tree root directory.

        Returns:
            Central backup root path.
        """

        tree_path = Path(tree_dir)
        return tree_path.parent / TREE_BACKUP_DIRNAME / tree_path.name

    def field_state_path(self, tree_dir: str | Path) -> Path:
        """Return the per-field local state file for one translation tree.

        Args:
            tree_dir: Translation tree root directory.

        Returns:
            Path to the persisted field-state file.
        """

        return self.backup_root(tree_dir) / FIELD_STATE_FILENAME

    def central_backup_path(self, tree_dir: str | Path, entity_uuid: str) -> Path:
        """Return the central backup path for one node translation file.

        Args:
            tree_dir: Translation tree root directory.
            entity_uuid: Node UUID represented by the markdown file.

        Returns:
            Central backup file path.
        """

        return self.backup_root(tree_dir) / f"{entity_uuid}.{TRANSLATION_FILENAME}.bak"

    @staticmethod
    def legacy_backup_path(translation_path: Path) -> Path:
        """Return the legacy in-folder backup path for one translation file.

        Args:
            translation_path: Translation markdown path.

        Returns:
            Legacy backup file path.
        """

        return translation_path.parent / TRANSLATION_BACKUP_FILENAME

    def candidate_backup_paths(
        self,
        tree_dir: str | Path,
        entity_uuid: str,
        translation_path: Path,
    ) -> tuple[Path, ...]:
        """Return backup locations to try when restoring a translation file.

        Args:
            tree_dir: Translation tree root directory.
            entity_uuid: Node UUID represented by the markdown file.
            translation_path: Translation markdown file path.

        Returns:
            Ordered candidate backup paths.
        """

        return (
            self.central_backup_path(tree_dir, entity_uuid),
            self.legacy_backup_path(translation_path),
        )


class TranslationBackupStore:
    """Persist and restore last-known-good translation markdown backups.

    Args:
        path_service: Shared tree path helper.
        document: Markdown document parser used to verify backup validity.
    """

    def __init__(
        self,
        path_service: TranslationTreePathService,
        document: TranslationMarkdownDocument,
    ):
        self.path_service = path_service
        self.document = document

    def write_backup_text(
        self,
        tree_dir: str | Path,
        entity_uuid: str,
        markdown_text: str,
    ) -> None:
        """Write one central translation backup file.

        Args:
            tree_dir: Translation tree root directory.
            entity_uuid: UUID represented by the markdown file.
            markdown_text: Valid markdown content to persist as backup.
        """

        backup_path = self.path_service.central_backup_path(tree_dir, entity_uuid)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(markdown_text, encoding="utf-8")

    def restore_translation_backup(
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

        for backup_path in self.path_service.candidate_backup_paths(
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
            self.write_backup_text(
                tree_dir=tree_dir,
                entity_uuid=entity_uuid,
                markdown_text=backup_text,
            )
            return backup_path
        return None


class TranslationFieldStateStore:
    """Manage per-field edit timestamps used by shared-string synchronization.

    Args:
        path_service: Shared tree path helper.
    """

    def __init__(self, path_service: TranslationTreePathService):
        self.path_service = path_service

    def load(self, tree_dir: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
        """Load per-field edit timestamps from the local state file.

        Args:
            tree_dir: Translation tree root directory.

        Returns:
            Nested state keyed by UUID and field name.
        """

        state_path = self.path_service.field_state_path(tree_dir)
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

    def save(
        self,
        tree_dir: str | Path,
        state: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        """Persist per-field edit timestamps to the local state file.

        Args:
            tree_dir: Translation tree root directory.
            state: Nested state keyed by UUID and field name.
        """

        state_path = self.path_service.field_state_path(tree_dir)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def refresh(
        self,
        tree_dir: str,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> None:
        """Refresh local per-field edit metadata from the current tree state.

        Args:
            tree_dir: Translation tree root directory.
            folders_by_uuid: Parsed folder snapshots keyed by UUID.
        """

        state = self.load(tree_dir)
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
            self.save(tree_dir, state)
