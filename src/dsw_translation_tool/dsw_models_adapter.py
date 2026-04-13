"""Adapters for the official `dsw-models` knowledge model schemas.

This module keeps the translation workflow loosely coupled to the upstream
`dsw-models` package. We validate incoming KM bundles with the official
Pydantic schema and expose a small normalized event record that the local
parser can merge deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data_models import ModelInfo


@dataclass(frozen=True)
class TypedKnowledgeModelEvent:
    """Normalized KM event record produced from `dsw-models`.

    Args:
        uuid: Event UUID.
        entity_uuid: UUID of the entity the event applies to.
        parent_uuid: Raw `parentUuid` from the event payload.
        effective_parent_uuid: Effective current parent used for tree building.
        created_at: Event timestamp in ISO string form.
        package_index: Source package order within the KM bundle.
        event_index: Event order within the source package.
        content: JSON-friendly event content dumped with camelCase aliases.
    """

    uuid: str
    entity_uuid: str
    parent_uuid: str
    effective_parent_uuid: str
    created_at: str
    package_index: int
    event_index: int
    content: dict[str, Any]

    @property
    def event_type(self) -> str:
        """Return the normalized event type."""

        return str(self.content["eventType"])


class DswModelsBundleAdapter:
    """Load KM bundles via the official `dsw-models` schema package."""

    @classmethod
    def load_bundle_events(
        cls,
        model_path: str,
    ) -> tuple[list[TypedKnowledgeModelEvent], ModelInfo]:
        """Validate a KM bundle and normalize its events.

        Args:
            model_path: Path to a DSW KM/JSON bundle file.

        Returns:
            Normalized typed events and bundle metadata.

        Raises:
            RuntimeError: If `dsw-models` is not installed.
        """

        bundle_class = cls._bundle_class()
        root = json.loads(Path(model_path).read_text(encoding="utf-8"))
        normalized_root = cls._normalize_edit_event_fields(root)
        bundle = bundle_class.model_validate(normalized_root)

        events: list[TypedKnowledgeModelEvent] = []
        for package_index, package in enumerate(bundle.packages):
            for event_index, event in enumerate(package.events):
                dumped_event = event.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude_none=False,
                )
                content = dumped_event["content"]
                effective_parent_uuid = cls._resolve_effective_parent_uuid(dumped_event)
                events.append(
                    TypedKnowledgeModelEvent(
                        uuid=str(dumped_event["uuid"]),
                        entity_uuid=str(dumped_event["entityUuid"]),
                        parent_uuid=str(dumped_event["parentUuid"]),
                        effective_parent_uuid=str(effective_parent_uuid),
                        created_at=str(dumped_event["createdAt"]),
                        package_index=package_index,
                        event_index=event_index,
                        content=content,
                    )
                )

        events.sort(
            key=lambda item: (
                item.created_at,
                item.package_index,
                item.event_index,
            )
        )
        model_info = ModelInfo(
            id=str(bundle.id),
            km_id=str(bundle.km_id),
            name=bundle.name or bundle.km_id or "Knowledge Model",
        )
        return events, model_info

    @classmethod
    def _normalize_edit_event_fields(cls, value: Any) -> Any:
        """Normalize raw KM JSON before `dsw-models` validation.

        The upstream schema models edit fields as `{changed, value}`, but real
        DSW package bundles frequently serialize unchanged fields as just
        `{"changed": false}`. We add `value: null` in that case so the typed
        schema can still validate the bundle.

        Args:
            value: Raw JSON-like value read from the KM bundle.

        Returns:
            Normalized JSON-like value ready for schema validation.
        """

        if isinstance(value, list):
            return [cls._normalize_edit_event_fields(item) for item in value]

        if not isinstance(value, dict):
            return value

        normalized = {key: cls._normalize_edit_event_fields(item) for key, item in value.items()}
        if "changed" in normalized and "value" not in normalized:
            normalized["value"] = None
        return normalized

    @staticmethod
    def _resolve_effective_parent_uuid(dumped_event: dict[str, Any]) -> str:
        """Resolve the effective parent UUID for one normalized event.

        Move events use `targetUuid` as the current parent in the resulting
        graph. Other events continue to use `parentUuid`.

        Args:
            dumped_event: Event dumped via `model_dump(by_alias=True)`.

        Returns:
            Effective parent UUID string.
        """

        content = dumped_event["content"]
        event_type = content["eventType"]
        if event_type.startswith("Move") and content.get("targetUuid"):
            return str(content["targetUuid"])
        return str(dumped_event["parentUuid"])

    @staticmethod
    def _bundle_class() -> Any:
        """Import and return `KnowledgeModelPackageBundle`.

        Returns:
            The upstream bundle schema class.

        Raises:
            RuntimeError: If the dependency is unavailable.
        """

        try:
            from dsw.models.knowledge_model.package import (
                KnowledgeModelPackageBundle,
            )
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised in CI env
            raise RuntimeError(
                "The `dsw-models` dependency is required to parse knowledge "
                "models. Run `make install-dev` to install it."
            ) from exc
        return KnowledgeModelPackageBundle
