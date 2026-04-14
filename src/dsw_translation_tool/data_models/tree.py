"""Tree- and outline-related data models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        shared_fields: Field names whose source of truth is `shared_blocks.md`.
    """

    entity_uuid: str
    path: str
    event_type: str | None
    translation_path: Path | None
    modified_at: float
    fields: dict[str, TranslationFieldState] = field(default_factory=dict)
    field_modified_at: dict[str, float] = field(default_factory=dict)
    shared_fields: tuple[str, ...] = ()


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
class OutlineBuildResult:
    """Result of building a markdown outline for the collaboration tree.

    Args:
        markdown_text: Generated outline markdown.
        output_outline: Destination markdown path.
    """

    markdown_text: str
    output_outline: Path


@dataclass(frozen=True)
class SharedBlocksBuildResult:
    """Result of building shared-block collaboration markdown.

    Args:
        markdown_text: Generated shared-block markdown.
        output_shared_blocks: Destination markdown path.
    """

    markdown_text: str
    output_shared_blocks: Path


@dataclass(frozen=True)
class SharedBlocksOutlineBuildResult:
    """Result of building shared-block outline markdown.

    Args:
        markdown_text: Generated shared-block outline markdown.
        output_shared_blocks_outline: Destination markdown path.
    """

    markdown_text: str
    output_shared_blocks_outline: Path
