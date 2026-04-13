"""Execution helpers for shared-string synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..data_models import (
    SharedStringCandidate,
    SharedStringConflict,
    TranslationFieldState,
    TreeFolderSnapshot,
)


@dataclass
class SharedStringGroupProcessingResult:
    """Mutable result of processing shared-string groups.

    Args:
        pending_writes: Snapshots that need to be persisted back to disk.
        conflicts: Conflicts collected while processing candidate groups.
        groups_updated: Number of groups that caused at least one update.
        fields_updated: Total number of rewritten `(uuid, field)` values.
    """

    pending_writes: dict[str, TreeFolderSnapshot] = field(default_factory=dict)
    conflicts: list[SharedStringConflict] = field(default_factory=list)
    groups_updated: int = 0
    fields_updated: int = 0


class SharedStringGroupProcessor:
    """Resolve candidate translations and apply group-wide updates."""

    def process_groups(
        self,
        groups: dict[tuple[object, ...], list],
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> SharedStringGroupProcessingResult:
        """Process all shared-string groups against the scanned tree state.

        Args:
            groups: Shared-string groups keyed by grouping strategy output.
            folders_by_uuid: Parsed folder snapshots keyed by UUID.

        Returns:
            Aggregated processing result containing writes and counters.
        """

        result = SharedStringGroupProcessingResult()

        for references in groups.values():
            if len(references) < 2:
                continue

            candidates = self.collect_candidates(
                references=references,
                folders_by_uuid=folders_by_uuid,
            )
            if not candidates:
                continue

            canonical_text = candidates[0].translation
            result.conflicts.extend(self.collect_conflicts(references, candidates))
            group_updates = self.apply_group_updates(
                references=references,
                canonical_text=canonical_text,
                folders_by_uuid=folders_by_uuid,
                pending_writes=result.pending_writes,
            )
            if group_updates:
                result.groups_updated += 1
                result.fields_updated += group_updates

        return result

    @staticmethod
    def collect_candidates(
        references: list,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> list[SharedStringCandidate]:
        """Collect candidate translations for one group.

        Candidates are ordered by per-field edit time so that synchronization
        follows the most recently edited field rather than the newest file.
        Blank translations are included intentionally so a deliberately-cleared
        field can also win when it is the latest edit.

        Args:
            references: Group references to resolve.
            folders_by_uuid: Parsed folder snapshots keyed by UUID.

        Returns:
            Ordered shared-string candidates for the group.
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
    def collect_conflicts(
        references: list,
        candidates: list[SharedStringCandidate],
    ) -> list[SharedStringConflict]:
        """Build conflict records when a group has multiple non-empty values.

        Args:
            references: All references in the current group.
            candidates: Candidate translations collected from the tree.

        Returns:
            Conflict records for the group, if any.
        """

        unique_translations = {
            candidate.translation for candidate in candidates if candidate.translation.strip()
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
    def apply_group_updates(
        references: list,
        canonical_text: str,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
        pending_writes: dict[str, TreeFolderSnapshot],
    ) -> int:
        """Apply one canonical translation to the entire group.

        Args:
            references: All references in the current group.
            canonical_text: Translation selected as the canonical value.
            folders_by_uuid: Parsed folder snapshots keyed by UUID.
            pending_writes: Mutable snapshot map to populate with writes.

        Returns:
            Number of field updates applied to the group.
        """

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
