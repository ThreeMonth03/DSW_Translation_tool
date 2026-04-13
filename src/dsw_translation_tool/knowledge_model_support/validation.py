"""Validation helpers for PO entries against merged KM entities."""

from __future__ import annotations

from typing import Any

from ..data_models import PoEntry
from .display import KnowledgeModelTextResolver


class KnowledgeModelEntryValidator:
    """Validate flattened PO entries against merged KM entities."""

    def __init__(
        self,
        text_resolver: KnowledgeModelTextResolver | None = None,
    ):
        self.text_resolver = text_resolver or KnowledgeModelTextResolver()

    def validate_po_entries(
        self,
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
            actual = self.text_resolver.get_event_text_value(event, entry.field)
            if actual is None:
                missing_fields.append(
                    {
                        **entry.__dict__,
                        "availableFields": list(event.get("content", {}).keys()),
                    }
                )
                continue

            if actual != self.text_resolver.normalize_source_text(entry.msgid):
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
