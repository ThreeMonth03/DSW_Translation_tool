"""Shared-string synchronization facade services."""

from __future__ import annotations

from pathlib import Path

from .data_models import (
    SharedStringSyncResult,
)
from .po import PoCatalogParser, PoCatalogWriter
from .sync_support import SharedStringGroupBuilder, SharedStringGroupProcessor
from .tree import TranslationTreeRepository


class SharedStringSynchronizer:
    """Keep repeated source strings aligned across the translation tree.

    Args:
        tree_repository: Repository used to read and write tree folders.
        po_writer: Optional PO writer used when generating an updated PO file.
        group_builder: Optional builder used to derive shared-string groups.
        group_processor: Optional processor used to resolve and apply group updates.
    """

    def __init__(
        self,
        tree_repository: TranslationTreeRepository,
        po_writer: PoCatalogWriter | None = None,
        group_builder: SharedStringGroupBuilder | None = None,
        group_processor: SharedStringGroupProcessor | None = None,
    ):
        self.tree_repository = tree_repository
        self.po_writer = po_writer or PoCatalogWriter()
        self.group_builder = group_builder or SharedStringGroupBuilder()
        self.group_processor = group_processor or SharedStringGroupProcessor()

    def sync(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str | None = None,
        group_by: str = "shared-block",
    ) -> SharedStringSyncResult:
        """Synchronize repeated translation groups across the tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the grouping source.
            out_po_path: Optional output PO path to refresh after sync.
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
        processing_result = self.group_processor.process_groups(
            groups=groups,
            folders_by_uuid=scan_result.folders_by_uuid,
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
