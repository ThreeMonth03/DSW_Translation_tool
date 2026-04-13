"""Text resolution helpers for knowledge-model entities."""

from __future__ import annotations

from typing import Any

from ..constants import PO_FIELD_FALLBACKS, PRIMARY_NAME_FIELDS, RELATED_NAME_UUID_FIELDS, ZERO_UUID


class KnowledgeModelTextResolver:
    """Resolve translatable text and display labels from KM entities."""

    def get_event_text_value(
        self,
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
            return self.normalize_source_text(content[field])

        for fallback_field in PO_FIELD_FALLBACKS.get(field, []):
            if fallback_field in content and content[fallback_field] is not None:
                return self.normalize_source_text(content[fallback_field])

        return self.normalize_source_text(content.get(field))

    def resolve_node_display_name(
        self,
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
            value = self.clean_display_text(content.get(field))
            if value:
                return value, {
                    "sourceUuid": entity_uuid,
                    "field": field,
                    "relation": "self",
                }

        related_name = self._resolve_related_display_name(
            content=content,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
            visited=visited,
        )
        if related_name is not None:
            return related_name

        for field in ("description", "url", "advice"):
            value = self.clean_display_text(content.get(field))
            if value:
                return value, {
                    "sourceUuid": entity_uuid,
                    "field": field,
                    "relation": "self",
                }

        parent_uuid = event.get("parentUuid")
        if parent_uuid and parent_uuid != ZERO_UUID:
            parent_name, parent_source = self.resolve_node_display_name(
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

    def clean_display_text(self, value: Any) -> str | None:
        """Normalize candidate display text into a single readable line.

        Args:
            value: Raw candidate value.

        Returns:
            First readable display line or `None`.
        """

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
    def normalize_source_text(value: Any) -> Any:
        """Normalize KM source strings for validation consistency.

        Args:
            value: Raw source value.

        Returns:
            Normalized source value.
        """

        if not isinstance(value, str):
            return value
        return value.replace("\u2028", "").replace("\u2029", "")

    def _resolve_related_display_name(
        self,
        content: dict[str, Any],
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str | None,
        visited: set[str],
    ) -> tuple[str, dict[str, Any]] | None:
        """Resolve display name from a related UUID field when available.

        Args:
            content: Entity content dictionary.
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            model_name: Model-level fallback name.
            visited: Cycle-detection set.

        Returns:
            Related display name and metadata, if any.
        """

        for relation_field in RELATED_NAME_UUID_FIELDS:
            related_uuid = content.get(relation_field)
            if not related_uuid or related_uuid == ZERO_UUID:
                continue
            related_name, related_source = self.resolve_node_display_name(
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
