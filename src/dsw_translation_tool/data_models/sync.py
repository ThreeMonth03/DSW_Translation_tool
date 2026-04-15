"""Shared-string synchronization data models."""

from __future__ import annotations

from dataclasses import dataclass

from .po import PoReference


@dataclass(frozen=True)
class SharedStringCandidate:
    """Candidate translation used during shared-string synchronization.

    Args:
        reference: Source PO reference represented by the candidate.
        translation: Current translated text.
        source: Current source-language text.
        modified_at: Last modification time of the containing folder.
        path: Relative folder path for deterministic ordering.
    """

    reference: PoReference
    translation: str
    source: str
    modified_at: float
    path: str


@dataclass(frozen=True)
class SharedStringConflict:
    """Conflicting translation candidates inside one shared-string group.

    Args:
        msgid: Source text shared by the group.
        references: All PO references in the group.
        translations: Distinct non-empty translations observed in the group.
    """

    msgid: str
    references: tuple[PoReference, ...]
    translations: tuple[str, ...]


@dataclass(frozen=True)
class SharedStringSyncResult:
    """Outcome of a shared-string synchronization run.

    Args:
        groups_scanned: Number of multi-reference groups examined.
        groups_updated: Number of groups that caused file updates.
        fields_updated: Number of `(uuid, field)` values rewritten.
        conflicts: Conflicting groups encountered during synchronization.
        output_po: Generated PO path when requested.
        output_outline: Generated outline-markdown path when requested.
        output_shared_blocks: Generated shared-block markdown path when requested.
        output_shared_blocks_outline: Generated shared-block outline markdown path
            when requested.
        written_tree_paths: Translation-tree markdown files rewritten during the
            synchronization cycle.
    """

    groups_scanned: int
    groups_updated: int
    fields_updated: int
    conflicts: tuple[SharedStringConflict, ...]
    output_po: str | None = None
    output_outline: str | None = None
    output_shared_blocks: str | None = None
    output_shared_blocks_outline: str | None = None
    written_tree_paths: tuple[str, ...] = ()
