"""Tree-building helpers for the translation view of a knowledge model."""

from __future__ import annotations

from typing import Any

from ..constants import ZERO_UUID
from ..data_models import PoEntry, TreeNode


class KnowledgeModelTreeBuilder:
    """Build translation-tree structures from merged KM entities."""

    def build_ancestor_set(
        self,
        latest_by_uuid: dict[str, dict[str, Any]],
        referenced_uuids: set[str],
    ) -> set[str]:
        """Build the referenced UUID set including all ancestors.

        Args:
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            referenced_uuids: UUIDs directly referenced by PO entries.

        Returns:
            UUIDs required to keep the exported tree connected.
        """

        collected: set[str] = set()
        to_scan = list(referenced_uuids)

        while to_scan:
            current_uuid = to_scan.pop()
            if current_uuid in collected:
                continue
            collected.add(current_uuid)
            event = latest_by_uuid.get(current_uuid)
            if not event:
                continue
            parent_uuid = event.get("parentUuid")
            if parent_uuid and parent_uuid != ZERO_UUID and parent_uuid not in collected:
                to_scan.append(parent_uuid)

        return collected

    def build_tree(
        self,
        latest_by_uuid: dict[str, dict[str, Any]],
        root_uuids: set[str],
    ) -> tuple[list[TreeNode], dict[str, TreeNode]]:
        """Build the in-memory translation tree.

        Args:
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            root_uuids: UUIDs that should appear in the exported tree.

        Returns:
            Root nodes and a node lookup keyed by UUID.
        """

        nodes: dict[str, TreeNode] = {}
        for entity_uuid, event in latest_by_uuid.items():
            if entity_uuid not in root_uuids:
                continue
            nodes[entity_uuid] = TreeNode(
                entity_uuid=entity_uuid,
                parent_uuid=event.get("parentUuid"),
                event_type=event.get("content", {}).get("eventType"),
                content=event.get("content", {}),
            )

        roots: list[TreeNode] = []
        for entity_uuid, node in nodes.items():
            parent_uuid = node.parent_uuid
            if parent_uuid and parent_uuid in nodes:
                nodes[parent_uuid].children.append(node)
            else:
                roots.append(node)

        roots.sort(
            key=lambda node: (
                node.content.get("createdAt") or "",
                node.entity_uuid,
            )
        )
        for root in roots:
            self._sort_tree_children(root)

        return roots, nodes

    @staticmethod
    def annotate_tree_nodes(
        po_entries: list[PoEntry],
        nodes_map: dict[str, TreeNode],
    ) -> None:
        """Attach flattened PO entries to their corresponding tree nodes.

        Args:
            po_entries: Flattened PO entries.
            nodes_map: Tree node lookup keyed by UUID.
        """

        for entry in po_entries:
            node = nodes_map.get(entry.uuid)
            if node is not None:
                node.po_refs.append(entry)

    @staticmethod
    def _build_child_order_lookup(content: dict[str, Any]) -> dict[str, int]:
        """Build child ordering metadata from `*Uuids` fields.

        Args:
            content: Entity content dictionary.

        Returns:
            Child ordering lookup.
        """

        ordered_child_uuids: list[str] = []
        for key, value in content.items():
            if key.endswith("Uuids") and isinstance(value, list):
                ordered_child_uuids.extend(value)

        order_lookup: dict[str, int] = {}
        for index, child_uuid in enumerate(ordered_child_uuids):
            order_lookup.setdefault(child_uuid, index)
        return order_lookup

    def _sort_tree_children(self, node: TreeNode) -> None:
        """Sort node children using KM order and creation fallback.

        Args:
            node: Root node whose subtree should be sorted.
        """

        order_lookup = self._build_child_order_lookup(node.content)
        fallback_index = len(order_lookup) + 1
        node.children.sort(
            key=lambda child: (
                order_lookup.get(child.entity_uuid, fallback_index),
                child.content.get("createdAt") or "",
                child.entity_uuid,
            )
        )
        for child in node.children:
            self._sort_tree_children(child)
