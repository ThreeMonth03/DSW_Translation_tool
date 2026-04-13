"""PO-related data models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PoReference:
    """Represents one `#:` reference inside a PO block.

    Args:
        prefix: Prefix segment from the PO reference token.
        uuid: Entity UUID referenced by the PO block.
        field: Translatable field name for the entity.
        comment: Full original PO reference token.
    """

    prefix: str
    uuid: str
    field: str
    comment: str


@dataclass(frozen=True)
class PoEntry(PoReference):
    """Represents one flattened `(uuid, field)` translation entry.

    Args:
        msgid: Source-language string.
        msgstr: Target-language string.
    """

    msgid: str
    msgstr: str


@dataclass(frozen=True)
class PoBlock:
    """Represents one PO message block and its grouped references.

    Args:
        references: All references that share the same PO block.
        msgid: Source-language string.
        msgstr: Target-language string.
        is_fuzzy: Whether the block was marked as fuzzy.
    """

    references: tuple[PoReference, ...]
    msgid: str
    msgstr: str
    is_fuzzy: bool = False


@dataclass(frozen=True)
class PoReferenceSection:
    """Represents one contiguous PO reference-comment section.

    Args:
        comment_lines: Original serialized `#:` lines.
        comment_tokens: Flattened reference tokens extracted from the section.
    """

    comment_lines: tuple[str, ...]
    comment_tokens: tuple[str, ...]


@dataclass(frozen=True)
class PoTranslationGroup:
    """Represents consecutive references sharing one rewritten translation.

    Args:
        msgstr: Target translation for the grouped references.
        tokens: Structured PO references in their original section order.
    """

    msgstr: str
    tokens: tuple[PoReference, ...]


@dataclass(frozen=True)
class PoDiffReviewResult:
    """Summary of differences between an original and generated PO file.

    Args:
        total_blocks: Total message-block count in the original PO file.
        changed_blocks: Number of blocks with any semantic change.
        changed_msgstr_blocks: Number of blocks whose `msgstr` changed.
        changed_msgid_blocks: Number of blocks whose `msgid` changed.
        changed_reference_blocks: Number of blocks whose `#:` references changed.
        changed_fuzzy_blocks: Number of blocks whose fuzzy flag changed.
        inserted_blocks: Number of extra blocks in the generated PO file.
        deleted_blocks: Number of missing blocks in the generated PO file.
        msgstr_only: Whether all semantic changes were limited to `msgstr`.
        diff_text: Unified diff text for the whole file.
    """

    total_blocks: int
    changed_blocks: int
    changed_msgstr_blocks: int
    changed_msgid_blocks: int
    changed_reference_blocks: int
    changed_fuzzy_blocks: int
    inserted_blocks: int
    deleted_blocks: int
    msgstr_only: bool
    diff_text: str
