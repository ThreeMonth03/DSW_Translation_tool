"""Entity-history merging helpers for knowledge-model events."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..constants import ZERO_UUID
from ..dsw_models_adapter import TypedKnowledgeModelEvent


class KnowledgeModelEventMerger:
    """Merge typed KM event history into latest entity state."""

    def group_events_by_entity(
        self,
        events: list[TypedKnowledgeModelEvent],
    ) -> dict[str, list[TypedKnowledgeModelEvent]]:
        """Group sorted events by entity UUID.

        Args:
            events: Sorted typed KM events.

        Returns:
            Entity history keyed by entity UUID.
        """

        entity_history: dict[str, list[TypedKnowledgeModelEvent]] = defaultdict(list)
        for event in events:
            entity_history[event.entity_uuid].append(event)
        return entity_history

    def build_latest_entities(
        self,
        entity_history: dict[str, list[TypedKnowledgeModelEvent]],
    ) -> dict[str, dict[str, Any]]:
        """Merge entity event history into one latest state per UUID.

        Args:
            entity_history: Event history keyed by entity UUID.

        Returns:
            Latest merged entities keyed by UUID.
        """

        latest_by_uuid: dict[str, dict[str, Any]] = {}
        for entity_uuid, history in entity_history.items():
            state: dict[str, Any] = {}
            latest_parent_uuid = ZERO_UUID
            for event in history:
                state = self._merge_event_content(
                    base=state,
                    event_type=event.event_type,
                    delta=event.content,
                )
                latest_parent_uuid = event.effective_parent_uuid
                state["eventType"] = event.event_type
                state.setdefault("annotations", [])
                state["parentUuid"] = latest_parent_uuid
                state["entityUuid"] = entity_uuid
                state["uuid"] = event.uuid
                state["createdAt"] = event.created_at

            latest_by_uuid[entity_uuid] = {
                "content": state,
                "parentUuid": latest_parent_uuid,
                "entityUuid": entity_uuid,
            }
        return latest_by_uuid

    def _merge_event_content(
        self,
        base: dict[str, Any],
        event_type: str,
        delta: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge one event delta into the accumulated entity state.

        Args:
            base: Current accumulated entity state.
            event_type: Current event type.
            delta: Event payload.

        Returns:
            Updated entity state.
        """

        result = dict(base)
        if event_type.startswith("Add"):
            return self._normalize_add_event_content(delta)

        if event_type.startswith("Delete") or event_type.startswith("Move"):
            return result

        for key, value in delta.items():
            if key == "eventType":
                continue
            changed, normalized = self._normalize_delta_value(value)
            if not changed:
                continue
            result[key] = normalized
        return result

    @staticmethod
    def _normalize_add_event_content(delta: dict[str, Any]) -> dict[str, Any]:
        """Normalize one add-event payload into current entity state.

        Args:
            delta: Event content dumped via the typed adapter.

        Returns:
            Normalized state dictionary containing direct add-event values.
        """

        result: dict[str, Any] = {}
        for key, value in delta.items():
            if key == "eventType":
                continue
            result[key] = value
        result.setdefault("annotations", [])
        return result

    @staticmethod
    def _normalize_delta_value(value: Any) -> tuple[bool, Any]:
        """Normalize the DSW `changed/value` delta structure.

        Args:
            value: Raw field payload from a typed edit-event dump.

        Returns:
            A tuple of `(changed, normalized_value)`.
        """

        if isinstance(value, dict) and "changed" in value:
            return bool(value.get("changed")), value.get("value")
        return True, value
