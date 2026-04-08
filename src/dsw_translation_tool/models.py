"""Data models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PoReference:
    prefix: str
    uuid: str
    field: str
    comment: str


@dataclass(frozen=True)
class PoEntry(PoReference):
    msgid: str
    msgstr: str


@dataclass(frozen=True)
class PoBlock:
    references: tuple[PoReference, ...]
    msgid: str
    msgstr: str
    is_fuzzy: bool = False


@dataclass(frozen=True)
class ModelInfo:
    id: str | None
    km_id: str | None
    name: str


@dataclass
class TreeNode:
    entity_uuid: str
    parent_uuid: str | None
    event_type: str | None
    content: dict
    po_refs: list[PoEntry] = field(default_factory=list)
    children: list["TreeNode"] = field(default_factory=list)


@dataclass
class TranslationFieldState:
    source_text: str
    target_text: str


@dataclass
class TreeFolderSnapshot:
    entity_uuid: str
    path: str
    event_type: str | None
    translation_path: Path | None
    modified_at: float
    fields: dict[str, TranslationFieldState] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslationStatusFolder:
    uuid: str
    path: str
    event_type: str | None
    untranslated_fields: tuple[str, ...]
    translated_fields: tuple[str, ...]


@dataclass(frozen=True)
class SharedStringConflict:
    msgid: str
    references: tuple[PoReference, ...]
    translations: tuple[str, ...]


@dataclass(frozen=True)
class SharedStringSyncResult:
    groups_scanned: int
    groups_updated: int
    fields_updated: int
    conflicts: tuple[SharedStringConflict, ...]
    output_po: str | None = None
