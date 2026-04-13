"""Knowledge-model data models used by the translation tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .po import PoEntry


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
