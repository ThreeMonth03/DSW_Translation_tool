"""Knowledge model loading and tree-building services."""

from __future__ import annotations

import json
from collections import defaultdict

from .constants import PO_FIELD_FALLBACKS, PRIMARY_NAME_FIELDS, RELATED_NAME_UUID_FIELDS, ZERO_UUID
from .models import ModelInfo, PoEntry, TreeNode


class DswModelService:
    """Loads DSW models and builds the translation tree view."""

    @staticmethod
    def load_model(model_path: str) -> tuple[dict[str, dict], ModelInfo]:
        root = json.loads(open(model_path, "r", encoding="utf-8").read())

        events: list[tuple[str, int, dict]] = []
        for package in root.get("packages", []):
            for index, event in enumerate(package.get("events", [])):
                events.append((event.get("createdAt", ""), index, event))
        events.sort(key=lambda item: (item[0], item[1]))

        entity_history: dict[str, list[dict]] = defaultdict(list)
        for _, _, event in events:
            entity_history[event["entityUuid"]].append(event)

        latest_by_uuid: dict[str, dict] = {}
        for entity_uuid, history in entity_history.items():
            state: dict | None = None
            for event in history:
                content = event.get("content", {})
                state = dict(content) if state is None else DswModelService._merge_event_content(state, content)
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

        model_info = ModelInfo(
            id=root.get("id"),
            km_id=root.get("kmId"),
            name=root.get("name") or root.get("kmId") or "Knowledge Model",
        )
        return latest_by_uuid, model_info

    @staticmethod
    def build_ancestor_set(latest_by_uuid: dict[str, dict], referenced_uuids: set[str]) -> set[str]:
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

    @staticmethod
    def build_tree(latest_by_uuid: dict[str, dict], root_uuids: set[str]) -> tuple[list[TreeNode], dict[str, TreeNode]]:
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

        roots.sort(key=lambda node: (node.content.get("createdAt") or "", node.entity_uuid))
        for root in roots:
            DswModelService._sort_tree_children(root)

        return roots, nodes

    @staticmethod
    def annotate_tree_nodes(po_entries: list[PoEntry], nodes_map: dict[str, TreeNode]) -> None:
        for entry in po_entries:
            node = nodes_map.get(entry.uuid)
            if node is not None:
                node.po_refs.append(entry)

    @staticmethod
    def validate_po_entries(po_entries: list[PoEntry], latest_by_uuid: dict[str, dict]) -> dict:
        missing_entities: list[dict] = []
        missing_fields: list[dict] = []
        mismatches: list[dict] = []

        for entry in po_entries:
            if entry.uuid not in latest_by_uuid:
                missing_entities.append(entry.__dict__)
                continue

            event = latest_by_uuid[entry.uuid]
            actual = DswModelService.get_event_text_value(event, entry.field)
            if actual is None:
                missing_fields.append({**entry.__dict__, "availableFields": list(event.get("content", {}).keys())})
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
    def get_event_text_value(event: dict | None, field: str) -> str | None:
        if not event:
            return None
        content = event.get("content", {})
        if field in content and content[field] is not None:
            return DswModelService._normalize_source_text(content[field])
        for fallback_field in PO_FIELD_FALLBACKS.get(field, []):
            if fallback_field in content and content[fallback_field] is not None:
                return DswModelService._normalize_source_text(content[fallback_field])
        return DswModelService._normalize_source_text(content.get(field))

    @staticmethod
    def resolve_node_display_name(
        entity_uuid: str,
        latest_by_uuid: dict[str, dict],
        model_name: str | None = None,
        visited: set[str] | None = None,
    ) -> tuple[str, dict]:
        if visited is None:
            visited = set()
        if entity_uuid in visited:
            return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "cycle"}
        visited.add(entity_uuid)

        event = latest_by_uuid.get(entity_uuid)
        if not event:
            return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "missing"}

        content = event.get("content", {})
        for field in PRIMARY_NAME_FIELDS:
            value = DswModelService._clean_display_text(content.get(field))
            if value:
                return value, {"sourceUuid": entity_uuid, "field": field, "relation": "self"}

        for relation_field in RELATED_NAME_UUID_FIELDS:
            related_uuid = content.get(relation_field)
            if related_uuid and related_uuid != ZERO_UUID:
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

        for field in ("description", "url", "advice"):
            value = DswModelService._clean_display_text(content.get(field))
            if value:
                return value, {"sourceUuid": entity_uuid, "field": field, "relation": "self"}

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
            return model_name, {"sourceUuid": entity_uuid, "field": "modelName", "relation": "model"}
        return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "self"}

    @staticmethod
    def _merge_event_content(base: dict, delta: dict) -> dict:
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
    def _normalize_delta_value(value):
        if isinstance(value, dict) and "changed" in value:
            return value.get("value") if value.get("changed") else None
        return value

    @staticmethod
    def _build_child_order_lookup(content: dict) -> dict[str, int]:
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
    def _clean_display_text(value) -> str | None:
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
    def _normalize_source_text(value):
        if not isinstance(value, str):
            return value
        return value.replace("\u2028", "").replace("\u2029", "")
