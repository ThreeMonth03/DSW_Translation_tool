"""Shared-string synchronization services."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import (
    PoBlock,
    PoReference,
    SharedStringConflict,
    SharedStringSyncResult,
    TranslationFieldState,
)
from .po import PoCatalogParser, PoCatalogWriter
from .tree import TranslationTreeRepository


class SharedStringSynchronizer:
    """Keeps repeated source strings aligned across the translation tree."""

    def __init__(self, tree_repository: TranslationTreeRepository):
        self.tree_repository = tree_repository

    def sync(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str | None = None,
        group_by: str = "shared-block",
    ) -> SharedStringSyncResult:
        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        folders_by_uuid = scan_result["foldersByUuid"]
        groups = self._build_groups(blocks, group_by=group_by)

        pending_writes = {}
        conflicts: list[SharedStringConflict] = []
        groups_updated = 0
        fields_updated = 0

        for references in groups.values():
            if len(references) < 2:
                continue

            candidates = self._collect_candidates(references, folders_by_uuid)
            if not candidates:
                continue

            canonical_text = candidates[0]["translation"]
            unique_translations = {candidate["translation"] for candidate in candidates}
            if len(unique_translations) > 1:
                conflicts.append(
                    SharedStringConflict(
                        msgid=candidates[0]["source"],
                        references=tuple(references),
                        translations=tuple(sorted(unique_translations)),
                    )
                )

            group_updates = 0
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
                group_updates += 1

            if group_updates:
                groups_updated += 1
                fields_updated += group_updates

        for snapshot in pending_writes.values():
            self.tree_repository.write_snapshot(snapshot)

        output_po = None
        if out_po_path:
            refreshed_translations = self.tree_repository.scan(tree_dir)["translations"]
            output_po = self._write_output_po(
                original_po_path=original_po_path,
                out_po_path=out_po_path,
                translations=refreshed_translations,
            )

        return SharedStringSyncResult(
            groups_scanned=sum(1 for references in groups.values() if len(references) > 1),
            groups_updated=groups_updated,
            fields_updated=fields_updated,
            conflicts=tuple(conflicts),
            output_po=output_po,
        )

    def _build_groups(self, blocks: list[PoBlock], group_by: str) -> dict[tuple, list[PoReference]]:
        groups: dict[tuple, list[PoReference]] = defaultdict(list)
        for block in blocks:
            if not block.msgid:
                continue
            key = self._build_group_key(block, group_by=group_by)
            groups[key].extend(block.references)
        return groups

    @staticmethod
    def _build_group_key(block: PoBlock, group_by: str) -> tuple:
        if group_by == "shared-block":
            return ("shared-block", tuple((reference.uuid, reference.field) for reference in block.references))
        if group_by == "msgid":
            return ("msgid", block.msgid)
        if group_by == "msgid-field":
            fields = tuple(sorted({reference.field for reference in block.references}))
            return ("msgid-field", block.msgid, fields)
        raise ValueError(f"Unsupported grouping mode: {group_by}")

    @staticmethod
    def _collect_candidates(references, folders_by_uuid) -> list[dict]:
        candidates = []
        for reference in references:
            snapshot = folders_by_uuid.get(reference.uuid)
            if snapshot is None:
                continue
            state = snapshot.fields.get(reference.field)
            if state is None or not state.target_text.strip():
                continue
            candidates.append(
                {
                    "reference": reference,
                    "translation": state.target_text,
                    "source": state.source_text,
                    "modifiedAt": snapshot.modified_at,
                    "path": snapshot.path,
                }
            )

        candidates.sort(
            key=lambda candidate: (
                candidate["modifiedAt"],
                candidate["path"],
                candidate["reference"].uuid,
                candidate["reference"].field,
            ),
            reverse=True,
        )
        return candidates

    @staticmethod
    def _write_output_po(
        original_po_path: str,
        out_po_path: str,
        translations: dict[tuple[str, str], str],
    ) -> str:
        po_content = PoCatalogWriter.rewrite_translations(original_po_path, translations)
        output_file = Path(out_po_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(po_content, encoding="utf-8")
        return str(output_file)
