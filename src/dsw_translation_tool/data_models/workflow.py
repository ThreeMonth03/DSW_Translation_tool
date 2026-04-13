"""Workflow result models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .knowledge_model import ModelInfo, TreeNode
from .po import PoEntry
from .tree import TreeValidationResult


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
