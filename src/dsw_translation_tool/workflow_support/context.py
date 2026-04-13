"""Context-building helpers for translation workflow services."""

from __future__ import annotations

from ..data_models import PoEntry, WorkflowContext
from ..knowledge_model_service import KnowledgeModelService
from ..po import PoCatalogParser


class TranslationWorkflowContextBuilder:
    """Build reusable workflow context from PO and KM inputs.

    Args:
        model_service: Knowledge-model service used to load and validate KM
            content against PO entries.
    """

    def __init__(self, model_service: KnowledgeModelService):
        self.model_service = model_service

    def build(
        self,
        po_path: str,
        model_path: str,
    ) -> WorkflowContext:
        """Build the in-memory workflow context for a PO/KM pair.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.

        Returns:
            Workflow context used by export and validation steps.
        """

        po_entries = self.parse_po_entries(po_path)
        latest_by_uuid, model_info = self.model_service.load_model(model_path)
        relevant_uuids = self.model_service.build_ancestor_set(
            latest_by_uuid,
            {entry.uuid for entry in po_entries},
        )
        tree_roots, nodes_map = self.model_service.build_tree(
            latest_by_uuid,
            relevant_uuids,
        )
        self.model_service.annotate_tree_nodes(po_entries, nodes_map)
        report = self.model_service.validate_po_entries(po_entries, latest_by_uuid)
        return WorkflowContext(
            report=report,
            model_info=model_info,
            roots=tree_roots,
            entries=po_entries,
            latest_by_uuid=latest_by_uuid,
        )

    def validate_po_against_model(
        self,
        po_path: str,
        model_path: str,
    ) -> dict[str, object]:
        """Validate one PO file against the latest KM model.

        Args:
            po_path: PO file to validate.
            model_path: KM or JSON model path.

        Returns:
            Validation report dictionary.
        """

        po_entries = self.parse_po_entries(po_path)
        latest_by_uuid, _ = self.model_service.load_model(model_path)
        return self.model_service.validate_po_entries(po_entries, latest_by_uuid)

    @staticmethod
    def parse_po_entries(po_path: str) -> list[PoEntry]:
        """Parse one PO file into flattened `(uuid, field)` entries.

        Args:
            po_path: PO file to parse.

        Returns:
            Flattened PO entries.
        """

        return PoCatalogParser(po_path).parse_entries()
