"""Data models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
class ModelInfo:
    """Metadata describing the loaded DSW knowledge model.

    Args:
        id: Root model identifier.
        km_id: Knowledge model identifier.
        name: Human-readable model name.
    """

    id: str | None
    km_id: str | None
    name: str


@dataclass
class TreeNode:
    """Node in the exported translation tree.

    Args:
        entity_uuid: UUID of the node.
        parent_uuid: UUID of the parent node, if any.
        event_type: DSW event type.
        content: Latest merged node content from the KM.
        po_refs: Flattened PO entries attached to this node.
        children: Child nodes in tree order.
    """

    entity_uuid: str
    parent_uuid: str | None
    event_type: str | None
    content: dict[str, Any]
    po_refs: list[PoEntry] = field(default_factory=list)
    children: list["TreeNode"] = field(default_factory=list)


@dataclass
class TranslationFieldState:
    """Source and target text for one translatable field.

    Args:
        source_text: Source-language text.
        target_text: Target-language text.
    """

    source_text: str
    target_text: str


@dataclass
class TreeFolderSnapshot:
    """Current on-disk state of one exported tree folder.

    Args:
        entity_uuid: UUID stored in the folder.
        path: Relative path from tree root.
        event_type: DSW event type, if known.
        translation_path: Path to the `translation.md` file.
        modified_at: Last-modified timestamp used for sync precedence.
        fields: Parsed translation fields found in the folder.
        field_modified_at: Per-field edit timestamps used for sync precedence.
    """

    entity_uuid: str
    path: str
    event_type: str | None
    translation_path: Path | None
    modified_at: float
    fields: dict[str, TranslationFieldState] = field(default_factory=dict)
    field_modified_at: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslationStatusFolder:
    """Translation progress for one exported node folder.

    Args:
        uuid: Node UUID.
        path: Relative folder path.
        event_type: DSW event type, if known.
        untranslated_fields: Fields with missing target text.
        translated_fields: Fields with non-empty target text.
    """

    uuid: str
    path: str
    event_type: str | None
    untranslated_fields: tuple[str, ...]
    translated_fields: tuple[str, ...]


@dataclass(frozen=True)
class TranslationStatusSummary:
    """Aggregated translation progress counters.

    Args:
        total_nodes: Total node count recorded in the manifest.
        translatable_nodes: Node count that contains translatable fields.
        complete_folders: Folder count with no untranslated fields.
        pending_folders: Folder count with at least one untranslated field.
        total_fields: Total number of translatable fields.
        translated_fields: Number of translated fields.
        untranslated_fields: Number of untranslated fields.
    """

    total_nodes: int
    translatable_nodes: int
    complete_folders: int
    pending_folders: int
    total_fields: int
    translated_fields: int
    untranslated_fields: int

    def to_dict(self) -> dict[str, int]:
        """Convert the summary to a JSON-friendly dictionary.

        Returns:
            A dictionary using the legacy camelCase keys expected by CLI
            wrappers and compatibility helpers.
        """

        return {
            "totalNodes": self.total_nodes,
            "translatableNodes": self.translatable_nodes,
            "completeFolders": self.complete_folders,
            "pendingFolders": self.pending_folders,
            "totalFields": self.total_fields,
            "translatedFields": self.translated_fields,
            "untranslatedFields": self.untranslated_fields,
        }


@dataclass(frozen=True)
class TranslationStatusReport:
    """Full translation progress report for a tree scan.

    Args:
        summary: Aggregate counters for the tree.
        folders: Folder-level progress records in tree order.
    """

    summary: TranslationStatusSummary
    folders: tuple[TranslationStatusFolder, ...]

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert the report to the previous dictionary format.

        Returns:
            A dictionary compatible with the existing CLI and compatibility
            facade code paths.
        """

        return {
            "summary": self.summary.to_dict(),
            "folders": list(self.folders),
        }


@dataclass(frozen=True)
class TreeScanResult:
    """Parsed contents of an exported translation tree.

    Args:
        manifest: Manifest read from `_translation_tree.json`, if present.
        node_dirs: Mapping from UUID to absolute folder path.
        translations: Mapping from `(uuid, field)` to target text.
        duplicate_uuids: Duplicate UUID folder collisions discovered on disk.
        folders_by_uuid: Folder snapshots keyed by UUID.
    """

    manifest: dict[str, Any] | None
    node_dirs: dict[str, str]
    translations: dict[tuple[str, str], str]
    duplicate_uuids: tuple[tuple[str, str, str], ...]
    folders_by_uuid: dict[str, TreeFolderSnapshot]

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert the scan result to the previous dictionary format."""

        return {
            "manifest": self.manifest,
            "nodeDirs": self.node_dirs,
            "translations": self.translations,
            "duplicateUuids": list(self.duplicate_uuids),
            "foldersByUuid": self.folders_by_uuid,
        }


@dataclass(frozen=True)
class TreeValidationResult:
    """Validation result for an exported translation tree.

    Args:
        scan_result: Parsed scan result for the tree.
        errors: Validation errors discovered during the scan.
    """

    scan_result: TreeScanResult
    errors: tuple[str, ...]

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert the validation result to the previous dictionary format."""

        return {
            **self.scan_result.to_legacy_dict(),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class WorkflowContext:
    """In-memory context needed for export and validation workflows.

    Args:
        report: PO-versus-KM validation report.
        model_info: Metadata of the loaded model.
        roots: Translation tree roots.
        entries: Flattened PO entries.
        latest_by_uuid: Latest merged KM entities keyed by UUID.
        manifest: Exported manifest when a tree was written to disk.
    """

    report: dict[str, Any]
    model_info: ModelInfo
    roots: list[TreeNode]
    entries: list[PoEntry]
    latest_by_uuid: dict[str, dict[str, Any]]
    manifest: dict[str, Any] | None = None

    @property
    def model_metadata(self) -> dict[str, str | None]:
        """Return model metadata in a JSON-friendly dictionary form."""

        return {
            "id": self.model_info.id,
            "kmId": self.model_info.km_id,
            "name": self.model_info.name,
        }


@dataclass(frozen=True)
class PoBuildResult:
    """Result of rebuilding a PO file from the translation tree.

    Args:
        po_content: Generated PO text.
        translations: `(uuid, field)` translation mapping used for the build.
        validation: Validation result of the input tree.
        output_po: Generated PO file path.
    """

    po_content: str
    translations: dict[tuple[str, str], str]
    validation: TreeValidationResult
    output_po: Path


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
    """

    groups_scanned: int
    groups_updated: int
    fields_updated: int
    conflicts: tuple[SharedStringConflict, ...]
    output_po: str | None = None
    output_outline: str | None = None


@dataclass(frozen=True)
class OutlineBuildResult:
    """Result of building a markdown outline for the collaboration tree.

    Args:
        markdown_text: Generated outline markdown.
        output_outline: Destination markdown path.
    """

    markdown_text: str
    output_outline: Path


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
