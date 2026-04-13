"""Outline view models used by collaboration-tree markdown rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OutlineNode:
    """Outline node with aggregated translation progress.

    Args:
        entity_uuid: UUID of the represented tree node.
        path: Relative node path inside the translation tree.
        label: Original folder label used for display.
        event_type: DSW event type associated with the node.
        link_target: File path linked from the outline.
        own_translated_fields: Number of translated fields on the node itself.
        own_total_fields: Total translatable field count on the node itself.
        subtree_translated_fields: Aggregated translated-field count for the subtree.
        subtree_total_fields: Aggregated field count for the subtree.
        children: Child outline nodes in render order.
    """

    entity_uuid: str
    path: str
    label: str
    event_type: str | None
    link_target: Path
    own_translated_fields: int
    own_total_fields: int
    subtree_translated_fields: int = 0
    subtree_total_fields: int = 0
    children: list["OutlineNode"] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Return whether the node subtree is fully translated."""

        return self.subtree_translated_fields == self.subtree_total_fields

    @property
    def is_self_complete(self) -> bool:
        """Return whether this node itself is complete or non-translatable."""

        if self.own_total_fields == 0:
            return True
        return self.own_translated_fields == self.own_total_fields

    @property
    def checkbox(self) -> str:
        """Return the markdown checkbox marker."""

        return "x" if self.is_self_complete else " "

    @property
    def display_label(self) -> str:
        """Return the human-friendly node label without the UUID suffix."""

        return re.sub(r" \[[0-9a-f]{8}\]$", "", self.label)
