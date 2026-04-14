"""Shared-string synchronization facade services."""

from __future__ import annotations

from pathlib import Path

from .data_models import (
    SharedStringSyncResult,
)
from .po import PoCatalogParser, PoCatalogWriter
from .shared_blocks import SharedBlocksCatalogParser, resolve_shared_blocks_backup_path
from .sync_support import SharedStringGroupBuilder, SharedStringGroupProcessor
from .tree import TranslationTreeRepository


class SharedStringSynchronizer:
    """Keep repeated source strings aligned across the translation tree.

    Args:
        tree_repository: Repository used to read and write tree folders.
        po_writer: Optional PO writer used when generating an updated PO file.
        group_builder: Optional builder used to derive shared-string groups.
        group_processor: Optional processor used to resolve and apply group updates.
        shared_blocks_parser: Optional parser used to read `shared_blocks.md`.
    """

    def __init__(
        self,
        tree_repository: TranslationTreeRepository,
        po_writer: PoCatalogWriter | None = None,
        group_builder: SharedStringGroupBuilder | None = None,
        group_processor: SharedStringGroupProcessor | None = None,
        shared_blocks_parser: SharedBlocksCatalogParser | None = None,
    ):
        self.tree_repository = tree_repository
        self.po_writer = po_writer or PoCatalogWriter()
        self.group_builder = group_builder or SharedStringGroupBuilder()
        self.group_processor = group_processor or SharedStringGroupProcessor()
        self.shared_blocks_parser = shared_blocks_parser or SharedBlocksCatalogParser(
            source_lang=tree_repository.source_lang,
            target_lang=tree_repository.target_lang,
        )

    def sync(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str | None = None,
        shared_blocks_path: str | None = None,
        group_by: str = "shared-block",
    ) -> SharedStringSyncResult:
        """Synchronize repeated translation groups across the tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the grouping source.
            out_po_path: Optional output PO path to refresh after sync.
            shared_blocks_path: Optional shared-block markdown path used as
                the canonical source for shared-block synchronization.
            group_by: Grouping strategy for shared strings.

        Returns:
            Summary of the synchronization run.
        """

        parser = PoCatalogParser(original_po_path)
        blocks = parser.parse_blocks()
        entries = parser.parse_entries()
        tree_validation = self.tree_repository.validate(tree_dir, entries)
        if tree_validation.errors:
            preview = "\n".join(tree_validation.errors[:50])
            raise ValueError(f"Translation tree validation failed:\n{preview}")

        scan_result = tree_validation.scan_result
        groups = self.group_builder.build_groups(blocks, group_by=group_by)
        if group_by == "shared-block":
            expected_group_keys = self.expected_shared_block_group_keys(groups)
            canonical_translations = self.load_shared_block_translations(
                tree_dir=tree_dir,
                shared_blocks_path=shared_blocks_path,
                expected_group_keys=expected_group_keys,
            )
        else:
            canonical_translations = {}
        processing_result = self.group_processor.process_groups(
            groups=groups,
            folders_by_uuid=scan_result.folders_by_uuid,
            canonical_translations=canonical_translations,
        )

        for snapshot in processing_result.pending_writes.values():
            self.tree_repository.write_snapshot(snapshot)

        output_po = None
        if out_po_path:
            refreshed_translations = self.tree_repository.scan(tree_dir).translations
            output_po = self._write_output_po(
                original_po_path=original_po_path,
                out_po_path=out_po_path,
                translations=refreshed_translations,
            )

        scanned_group_count = self.group_builder.count_multi_reference_groups(groups)
        return SharedStringSyncResult(
            groups_scanned=scanned_group_count,
            groups_updated=processing_result.groups_updated,
            fields_updated=processing_result.fields_updated,
            conflicts=tuple(processing_result.conflicts),
            output_po=output_po,
        )

    def load_shared_block_translations(
        self,
        tree_dir: str,
        shared_blocks_path: str | None,
        expected_group_keys: set[tuple[tuple[str, str], ...]],
    ) -> dict[tuple[tuple[str, str], ...], str]:
        """Load shared-block translations from markdown when the file exists.

        Args:
            tree_dir: Translation tree root directory.
            shared_blocks_path: Candidate shared-block markdown path.
            expected_group_keys: Structured shared-block group set expected from
                the source PO.

        Returns:
            Mapping from shared-block keys to canonical translated text.
        """

        if not shared_blocks_path:
            return {}
        shared_blocks_file = Path(shared_blocks_path)
        if not shared_blocks_file.exists():
            restored_backup = self.restore_shared_blocks_backup(
                shared_blocks_path=shared_blocks_file,
                tree_dir=tree_dir,
                expected_group_keys=expected_group_keys,
            )
            if restored_backup is not None:
                raise ValueError(
                    "Missing shared-block markdown was restored from the last "
                    f"known-good backup.\nFile: {shared_blocks_file}\n"
                    f"Backup: {restored_backup}"
                )
            return {}
        try:
            translations = self.shared_blocks_parser.parse(str(shared_blocks_file))
            self.validate_shared_block_translations(
                translations=translations,
                expected_group_keys=expected_group_keys,
                shared_blocks_path=str(shared_blocks_file),
            )
            return translations
        except ValueError as error:
            restored_backup = self.restore_shared_blocks_backup(
                shared_blocks_path=shared_blocks_file,
                tree_dir=tree_dir,
                expected_group_keys=expected_group_keys,
            )
            if restored_backup is not None:
                raise ValueError(
                    "Invalid shared-block markdown was restored from the last "
                    f"known-good backup.\nFile: {shared_blocks_file}\n"
                    f"Backup: {restored_backup}\nReason: {error}"
                ) from error
            raise ValueError(
                "Invalid shared-block markdown and no valid backup was available.\n"
                f"File: {shared_blocks_file}\nReason: {error}"
            ) from error

    def validate_shared_block_translations(
        self,
        translations: dict[tuple[tuple[str, str], ...], str],
        expected_group_keys: set[tuple[tuple[str, str], ...]],
        shared_blocks_path: str,
    ) -> None:
        """Validate that `shared_blocks.md` covers the full shared-block set.

        Args:
            translations: Parsed shared-block translation mapping.
            expected_group_keys: Structured shared-block group set expected
                from the source PO.
            shared_blocks_path: Source path used in error messages.

        Raises:
            ValueError: If the shared-block file is incomplete or contains
                unexpected groups.
        """

        actual_group_keys = set(translations)
        missing_groups = expected_group_keys - actual_group_keys
        unexpected_groups = actual_group_keys - expected_group_keys
        if not missing_groups and not unexpected_groups:
            return

        preview_lines = []
        if missing_groups:
            missing_preview = ", ".join(
                SharedBlocksCatalogParser.serialize_group_key(group_key)
                for group_key in sorted(missing_groups)[:3]
            )
            preview_lines.append(f"Missing groups: {missing_preview}")
        if unexpected_groups:
            unexpected_preview = ", ".join(
                SharedBlocksCatalogParser.serialize_group_key(group_key)
                for group_key in sorted(unexpected_groups)[:3]
            )
            preview_lines.append(f"Unexpected groups: {unexpected_preview}")
        preview = "\n".join(preview_lines)
        raise ValueError(
            "Shared-block markdown does not match the expected shared-group set.\n"
            f"File: {shared_blocks_path}\n{preview}"
        )

    def restore_shared_blocks_backup(
        self,
        shared_blocks_path: Path,
        tree_dir: str,
        expected_group_keys: set[tuple[tuple[str, str], ...]],
    ) -> Path | None:
        """Restore `shared_blocks.md` from the last known-good backup.

        Args:
            shared_blocks_path: Shared-block markdown path to restore.
            tree_dir: Translation tree root directory.
            expected_group_keys: Structured shared-block group set expected
                from the source PO.

        Returns:
            Backup path when restoration succeeded, otherwise `None`.
        """

        backup_path = resolve_shared_blocks_backup_path(
            tree_repository=self.tree_repository,
            tree_dir=tree_dir,
        )
        if not backup_path.exists():
            return None

        backup_text = backup_path.read_text(encoding="utf-8")
        translations = self.shared_blocks_parser.parse_text(
            backup_text,
            str(backup_path),
        )
        self.validate_shared_block_translations(
            translations=translations,
            expected_group_keys=expected_group_keys,
            shared_blocks_path=str(backup_path),
        )
        shared_blocks_path.parent.mkdir(parents=True, exist_ok=True)
        shared_blocks_path.write_text(backup_text, encoding="utf-8")
        backup_path.write_text(backup_text, encoding="utf-8")
        return backup_path

    def expected_shared_block_group_keys(
        self,
        groups: dict[tuple[object, ...], list],
    ) -> set[tuple[tuple[str, str], ...]]:
        """Return the structured shared-block key set for the current sync run.

        Args:
            groups: Shared-string groups built from the source PO.

        Returns:
            Structured shared-block key set for multi-reference shared groups.
        """

        return {
            normalized_key
            for group_key, references in groups.items()
            if len(references) >= 2
            for normalized_key in (self.group_processor.normalize_shared_block_key(group_key),)
            if normalized_key
        }

    def _write_output_po(
        self,
        original_po_path: str,
        out_po_path: str,
        translations: dict[tuple[str, str], str],
    ) -> str:
        """Write the refreshed PO file after synchronization."""

        po_content = self.po_writer.rewrite_translations(
            original_po_path,
            translations,
        )
        output_file = Path(out_po_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(po_content, encoding="utf-8")
        return str(output_file)
