"""Knowledge model loading and tree-building facade services."""

from __future__ import annotations

from typing import Any

from .data_models import ModelInfo, PoEntry, TreeNode
from .dsw_models_adapter import DswModelsBundleAdapter
from .knowledge_model_support import (
    KnowledgeModelEntryValidator,
    KnowledgeModelEventMerger,
    KnowledgeModelTextResolver,
    KnowledgeModelTreeBuilder,
)


class KnowledgeModelService:
    """Load DSW models and derive the translation tree view."""

    _event_merger = KnowledgeModelEventMerger()
    _tree_builder = KnowledgeModelTreeBuilder()
    _text_resolver = KnowledgeModelTextResolver()
    _entry_validator = KnowledgeModelEntryValidator(
        text_resolver=_text_resolver,
    )

    @staticmethod
    def load_model(model_path: str) -> tuple[dict[str, dict[str, Any]], ModelInfo]:
        """Load a KM/JSON model and merge entity history into latest state.

        Args:
            model_path: Path to the KM or JSON model file.

        Returns:
            A tuple containing latest entities keyed by UUID and model metadata.
        """

        events, model_info = DswModelsBundleAdapter.load_bundle_events(model_path)
        entity_history = KnowledgeModelService._event_merger.group_events_by_entity(events)
        latest_by_uuid = KnowledgeModelService._event_merger.build_latest_entities(entity_history)
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

        return KnowledgeModelService._tree_builder.build_ancestor_set(
            latest_by_uuid=latest_by_uuid,
            referenced_uuids=referenced_uuids,
        )

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

        return KnowledgeModelService._tree_builder.build_tree(
            latest_by_uuid=latest_by_uuid,
            root_uuids=root_uuids,
        )

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

        KnowledgeModelService._tree_builder.annotate_tree_nodes(
            po_entries=po_entries,
            nodes_map=nodes_map,
        )

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

        return KnowledgeModelService._entry_validator.validate_po_entries(
            po_entries=po_entries,
            latest_by_uuid=latest_by_uuid,
        )

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

        return KnowledgeModelService._text_resolver.get_event_text_value(
            event=event,
            field=field,
        )

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

        return KnowledgeModelService._text_resolver.resolve_node_display_name(
            entity_uuid=entity_uuid,
            latest_by_uuid=latest_by_uuid,
            model_name=model_name,
            visited=visited,
        )


__all__ = ["KnowledgeModelService"]
