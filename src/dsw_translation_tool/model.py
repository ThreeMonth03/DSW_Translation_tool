"""Knowledge model loading and tree-building services."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .constants import (
    PO_FIELD_FALLBACKS,
    PRIMARY_NAME_FIELDS,
    RELATED_NAME_UUID_FIELDS,
    ZERO_UUID,
)
from .models import ModelInfo, PoEntry, TreeNode


class DswModelService:
    """Load DSW models and derive the translation tree view."""

    @staticmethod
    def load_model(model_path: str) -> tuple[dict[str, dict[str, Any]], ModelInfo]:
        """Load a KM/JSON model and merge entity history into latest state.

        Args:
            model_path: Path to the KM or JSON model file.

        Returns:
            A tuple containing latest entities keyed by UUID and model metadata.
        """

        root = json.loads(Path(model_path).read_text(encoding="utf-8"))
        events = DswModelService._collect_sorted_events(root)
        entity_history = DswModelService._group_events_by_entity(events)
        latest_by_uuid = DswModelService._build_latest_entities(entity_history)
        model_info = ModelInfo(
            id=root.get("id"),
            km_id=root.get("kmId"),
            name=root.get("name") or root.get("kmId") or "Knowledge Model",
        )
        return latest_by_uuid, model_info

    @staticmethod
    def build_ancestor_set(
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
            if (
                parent_uuid
                and parent_uuid != ZERO_UUID
                and parent_uuid not in collected
            ):
                to_scan.append(parent_uuid)

        return collected

    @staticmethod
    def build_tree(
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
            DswModelService._sort_tree_children(root)

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
    def validate_po_entries(
        po_entries: list[PoEntry],
        latest_by_uuid: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate PO entries against the latest KM entities.

        Args:
            po_entries: Flattened PO entries.
            latest_by_uuid: Latest merged KM entities keyed by UUID.

        Returns:
            Validation report in the existing JSON-friendly structure.
        """

        missing_entities: list[dict[str, Any]] = []
        missing_fields: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []

        for entry in po_entries:
            if entry.uuid not in latest_by_uuid:
                missing_entities.append(entry.__dict__)
                continue

            event = latest_by_uuid[entry.uuid]
            actual = DswModelService.get_event_text_value(event, entry.field)
            if actual is None:
                missing_fields.append(
                    {
                        **entry.__dict__,
                        "availableFields": list(event.get("content", {}).keys()),
                    }
                )
                continue

            if actual != DswModelService._normalize_source_text(entry.msgid):
                mismatches.append({**entry.__dict__, "actual": actual})

        return {
            "totalComments": len(po_entries),
            "missingEntities": len(missing_entities),
            "missingFields": len(missing_fields),
            "mismatches": len(mismatches),
            "missingEntitiesDetails": missing_entities,
            "missingFieldsDetails": missing_fields,
            "mismatchesDetails": mismatches,
        }

    @staticmethod
    def get_event_text_value(
        event: dict[str, Any] | None,
        field: str,
    ) -> str | None:
        """Read one translatable field from a merged KM entity.

        Args:
            event: Latest merged KM entity.
            field: Requested translatable field name.

        Returns:
            Resolved source text or `None` when unavailable.
        """

        if not event:
            return None

        content = event.get("content", {})
        if field in content and content[field] is not None:
            return DswModelService._normalize_source_text(content[field])

        for fallback_field in PO_FIELD_FALLBACKS.get(field, []):
            if fallback_field in content and content[fallback_field] is not None:
                return DswModelService._normalize_source_text(
                    content[fallback_field]
                )

        return DswModelService._normalize_source_text(content.get(field))

    @staticmethod
    def resolve_node_display_name(
        entity_uuid: str,
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str | None = None,
        visited: set[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve the best display name for one exported node.

        Args:
            entity_uuid: UUID being named.
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            model_name: Model-level fallback name.
            visited: Cycle-detection set for recursive lookups.

        Returns:
            A display label and metadata describing how it was resolved.
        """

        visited = visited or set()
        if entity_uuid in visited:
            return entity_uuid, {
                "sourceUuid": entity_uuid,
                "field": "uuid",
                "relation": "cycle",
            }
        visited.add(entity_uuid)

        event = latest_by_uuid.get(entity_uuid)
        if not event:
            return entity_uuid, {
                "sourceUuid": entity_uuid,
                "field": "uuid",
                "relation": "missing",
            }

        content = event.get("content", {})
        for field in PRIMARY_NAME_FIELDS:
            value = DswModelService._clean_display_text(content.get(field))
            if value:
                return value, {
                    "sourceUuid": entity_uuid,
                    "field": field,
                    "relation": "self",
                }

        related_name = DswModelService._resolve_related_display_name(
            content=content,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
            visited=visited,
        )
        if related_name is not None:
            return related_name

        for field in ("description", "url", "advice"):
            value = DswModelService._clean_display_text(content.get(field))
            if value:
                return value, {
                    "sourceUuid": entity_uuid,
                    "field": field,
                    "relation": "self",
                }

        parent_uuid = event.get("parentUuid")
        if parent_uuid and parent_uuid != ZERO_UUID:
            parent_name, parent_source = DswModelService.resolve_node_display_name(
                parent_uuid,
                latest_by_uuid,
                model_name=model_name,
                visited=set(visited),
            )
            if parent_name:
                return parent_name, {
                    "sourceUuid": parent_source.get("sourceUuid", parent_uuid),
                    "field": parent_source.get("field"),
                    "relation": "parentUuid",
                }

        if model_name:
            return model_name, {
                "sourceUuid": entity_uuid,
                "field": "modelName",
                "relation": "model",
            }
        return entity_uuid, {
            "sourceUuid": entity_uuid,
            "field": "uuid",
            "relation": "self",
        }

    @staticmethod
    def _collect_sorted_events(root: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
        """Collect all package events in deterministic order."""

        events: list[tuple[str, int, dict[str, Any]]] = []
        for package in root.get("packages", []):
            for index, event in enumerate(package.get("events", [])):
                events.append((event.get("createdAt", ""), index, event))
        events.sort(key=lambda item: (item[0], item[1]))
        return events

    @staticmethod
    def _group_events_by_entity(
        events: list[tuple[str, int, dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group sorted events by entity UUID."""

        entity_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for _, _, event in events:
            entity_history[event["entityUuid"]].append(event)
        return entity_history

    @staticmethod
    def _build_latest_entities(
        entity_history: dict[str, list[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        """Merge entity event history into one latest state per UUID."""

        latest_by_uuid: dict[str, dict[str, Any]] = {}
        for entity_uuid, history in entity_history.items():
            state: dict[str, Any] | None = None
            for event in history:
                content = event.get("content", {})
                state = (
                    dict(content)
                    if state is None
                    else DswModelService._merge_event_content(state, content)
                )
                state["eventType"] = content.get("eventType")
                state["annotations"] = content.get("annotations", [])
                state["parentUuid"] = event.get("parentUuid")
                state["entityUuid"] = entity_uuid
                state["uuid"] = event.get("uuid")
                state["createdAt"] = event.get("createdAt")

            latest_by_uuid[entity_uuid] = {
                "content": state,
                "parentUuid": state.get("parentUuid"),
                "entityUuid": entity_uuid,
            }
        return latest_by_uuid

    @staticmethod
    def _resolve_related_display_name(
        content: dict[str, Any],
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str | None,
        visited: set[str],
    ) -> tuple[str, dict[str, Any]] | None:
        """Resolve display name from a related UUID field when available."""

        for relation_field in RELATED_NAME_UUID_FIELDS:
            related_uuid = content.get(relation_field)
            if not related_uuid or related_uuid == ZERO_UUID:
                continue
            related_name, related_source = DswModelService.resolve_node_display_name(
                related_uuid,
                latest_by_uuid,
                model_name=model_name,
                visited=set(visited),
            )
            if related_name:
                return related_name, {
                    "sourceUuid": related_source.get("sourceUuid", related_uuid),
                    "field": related_source.get("field"),
                    "relation": relation_field,
                }
        return None

    @staticmethod
    def _merge_event_content(
        base: dict[str, Any],
        delta: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge one event delta into the accumulated entity state."""

        result = dict(base)
        for key, value in delta.items():
            if key in {"eventType", "annotations"}:
                continue
            normalized = DswModelService._normalize_delta_value(value)
            if normalized is None:
                if key not in result:
                    result[key] = None
                continue
            result[key] = normalized
        return result

    @staticmethod
    def _normalize_delta_value(value: Any) -> Any:
        """Normalize the DSW `changed/value` delta structure."""

        if isinstance(value, dict) and "changed" in value:
            return value.get("value") if value.get("changed") else None
        return value

    @staticmethod
    def _build_child_order_lookup(content: dict[str, Any]) -> dict[str, int]:
        """Build child ordering metadata from `*Uuids` fields."""

        ordered_child_uuids: list[str] = []
        for key, value in content.items():
            if key.endswith("Uuids") and isinstance(value, list):
                ordered_child_uuids.extend(value)

        order_lookup: dict[str, int] = {}
        for index, child_uuid in enumerate(ordered_child_uuids):
            order_lookup.setdefault(child_uuid, index)
        return order_lookup

    @staticmethod
    def _sort_tree_children(node: TreeNode) -> None:
        """Sort node children using KM order and creation fallback."""

        order_lookup = DswModelService._build_child_order_lookup(node.content)
        fallback_index = len(order_lookup) + 1
        node.children.sort(
            key=lambda child: (
                order_lookup.get(child.entity_uuid, fallback_index),
                child.content.get("createdAt") or "",
                child.entity_uuid,
            )
        )
        for child in node.children:
            DswModelService._sort_tree_children(child)

    @staticmethod
    def _clean_display_text(value: Any) -> str | None:
        """Normalize candidate display text into a single readable line."""

        if value is None:
            return None
        text = (
            str(value)
            .replace("\u2028", "\n")
            .replace("\u2029", "\n")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        if not text:
            return None
        return next((line.strip() for line in text.split("\n") if line.strip()), "") or text

    @staticmethod
    def _normalize_source_text(value: Any) -> Any:
        """Normalize KM source strings for validation consistency."""

        if not isinstance(value, str):
            return value
        return value.replace("\u2028", "").replace("\u2029", "")
