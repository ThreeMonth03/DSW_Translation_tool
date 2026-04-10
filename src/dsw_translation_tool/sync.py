"""Shared-string synchronization services."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import (
    PoBlock,
    PoReference,
    SharedStringCandidate,
    SharedStringConflict,
    SharedStringSyncResult,
    TranslationFieldState,
)
from .po import PoCatalogParser, PoCatalogWriter
from .tree import TranslationTreeRepository


class SharedStringSynchronizer:
    """Keep repeated source strings aligned across the translation tree.

    Args:
        tree_repository: Repository used to read and write tree folders.
        po_writer: Optional PO writer used when generating an updated PO file.
    """

    def __init__(
        self,
        tree_repository: TranslationTreeRepository,
        po_writer: PoCatalogWriter | None = None,
    ):
        self.tree_repository = tree_repository
        self.po_writer = po_writer or PoCatalogWriter()

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
        groups = self._build_groups(blocks, group_by=group_by)

        pending_writes = {}
        conflicts: list[SharedStringConflict] = []
        groups_updated = 0
        fields_updated = 0

        for references in groups.values():
            if len(references) < 2:
                continue

            candidates = self._collect_candidates(
                references=references,
                folders_by_uuid=scan_result.folders_by_uuid,
            )
            if not candidates:
                continue

            canonical_text = candidates[0].translation
            conflicts.extend(self._collect_conflicts(references, candidates))
            group_updates = self._apply_group_updates(
                references=references,
                canonical_text=canonical_text,
                folders_by_uuid=scan_result.folders_by_uuid,
                pending_writes=pending_writes,
            )
            if group_updates:
                groups_updated += 1
                fields_updated += group_updates

        for snapshot in pending_writes.values():
            self.tree_repository.write_snapshot(snapshot)

        output_po = None
        if out_po_path:
            refreshed_translations = self.tree_repository.scan(tree_dir).translations
            output_po = self._write_output_po(
                original_po_path=original_po_path,
                out_po_path=out_po_path,
                translations=refreshed_translations,
            )

        scanned_group_count = sum(1 for references in groups.values() if len(references) > 1)
        return SharedStringSyncResult(
            groups_scanned=scanned_group_count,
            groups_updated=groups_updated,
            fields_updated=fields_updated,
            conflicts=tuple(conflicts),
            output_po=output_po,
        )

    def _build_groups(
        self,
        blocks: list[PoBlock],
        group_by: str,
    ) -> dict[tuple[object, ...], list[PoReference]]:
        """Build shared-string groups according to the selected strategy."""

        groups: dict[tuple[object, ...], list[PoReference]] = defaultdict(list)
        for block in blocks:
            if not block.msgid:
                continue
            key = self._build_group_key(block, group_by=group_by)
            groups[key].extend(block.references)
        return groups

    @staticmethod
    def _build_group_key(block: PoBlock, group_by: str) -> tuple[object, ...]:
        """Build the grouping key for one PO block.

        Args:
            block: PO block being grouped.
            group_by: Selected grouping strategy.

        Returns:
            Tuple key used for group aggregation.

        Raises:
            ValueError: If the grouping strategy is unsupported.
        """

        if group_by == "shared-block":
            return (
                "shared-block",
                tuple((reference.uuid, reference.field) for reference in block.references),
            )
        if group_by == "msgid":
            return ("msgid", block.msgid)
        if group_by == "msgid-field":
            fields = tuple(sorted({reference.field for reference in block.references}))
            return ("msgid-field", block.msgid, fields)
        raise ValueError(f"Unsupported grouping mode: {group_by}")

    @staticmethod
    def _collect_candidates(
        references: list[PoReference],
        folders_by_uuid,
    ) -> list[SharedStringCandidate]:
        """Collect candidate translations for one group.

        Candidates are ordered by per-field edit time so that synchronization
        follows the most recently edited field rather than the newest file.
        Blank translations are included intentionally so a deliberately-cleared
        field can also win when it is the latest edit.
        """

        candidates: list[SharedStringCandidate] = []
        for reference in references:
            snapshot = folders_by_uuid.get(reference.uuid)
            if snapshot is None:
                continue
            state = snapshot.fields.get(reference.field)
            if state is None:
                continue
            candidates.append(
                SharedStringCandidate(
                    reference=reference,
                    translation=state.target_text,
                    source=state.source_text,
                    modified_at=snapshot.field_modified_at.get(
                        reference.field,
                        snapshot.modified_at,
                    ),
                    path=snapshot.path,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.modified_at,
                candidate.path,
                candidate.reference.uuid,
                candidate.reference.field,
            ),
            reverse=True,
        )
        return candidates

    @staticmethod
    def _collect_conflicts(
        references: list[PoReference],
        candidates: list[SharedStringCandidate],
    ) -> list[SharedStringConflict]:
        """Build conflict records when a group has multiple non-empty values."""

        unique_translations = {
            candidate.translation
            for candidate in candidates
            if candidate.translation.strip()
        }
        if len(unique_translations) <= 1:
            return []
        return [
            SharedStringConflict(
                msgid=candidates[0].source,
                references=tuple(references),
                translations=tuple(sorted(unique_translations)),
            )
        ]

    @staticmethod
    def _apply_group_updates(
        references: list[PoReference],
        canonical_text: str,
        folders_by_uuid,
        pending_writes,
    ) -> int:
        """Apply one canonical translation to the entire group."""

        updates = 0
        for reference in references:
            snapshot = folders_by_uuid.get(reference.uuid)
            if snapshot is None or reference.field not in snapshot.fields:
                continue
            current_state = snapshot.fields[reference.field]
            if current_state.target_text == canonical_text:
                continue
            snapshot.fields[reference.field] = TranslationFieldState(
                source_text=current_state.source_text,
                target_text=canonical_text,
            )
            pending_writes[reference.uuid] = snapshot
            updates += 1
        return updates

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
