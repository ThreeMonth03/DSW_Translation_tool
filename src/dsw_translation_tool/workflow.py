"""High-level translation workflow services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import DswModelService
from .models import ModelInfo, PoBuildResult, PoEntry, TranslationStatusReport, WorkflowContext
from .po import PoCatalogParser, PoCatalogWriter
from .tree import TranslationTreeRepository


class TranslationWorkflowService:
    """Coordinate PO parsing, KM loading, tree export, and PO rebuild steps.

    Args:
        source_lang: Source language code used by the workflow.
        target_lang: Target language code used by the workflow.
        tree_repository: Optional injected translation tree repository.
        model_service: Optional injected model service class or instance.
        po_writer: Optional injected PO writer.
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
        tree_repository: TranslationTreeRepository | None = None,
        model_service: DswModelService | None = None,
        po_writer: PoCatalogWriter | None = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.tree_repository = tree_repository or TranslationTreeRepository(
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self.model_service = model_service or DswModelService()
        self.po_writer = po_writer or PoCatalogWriter()

    def build_tree_context(self, po_path: str, model_path: str) -> WorkflowContext:
        """Build the in-memory workflow context for a PO/KM pair.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.

        Returns:
            Workflow context used by export and validation steps.
        """

        po_entries = self._parse_po_entries(po_path)
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
            model_info=self._normalize_model_info(model_info),
            roots=tree_roots,
            entries=po_entries,
            latest_by_uuid=latest_by_uuid,
        )

    def export_tree(
        self,
        po_path: str,
        model_path: str,
        out_dir: str,
        preserve_existing_translations: bool = True,
    ) -> WorkflowContext:
        """Export a PO/KM pair into the translation tree folder structure.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.
            out_dir: Output tree directory.
            preserve_existing_translations: Whether to preserve already edited
                target strings in the existing tree.

        Returns:
            Workflow context including the exported manifest.
        """

        context = self.build_tree_context(po_path=po_path, model_path=model_path)
        manifest = self.tree_repository.export_tree(
            out_dir=out_dir,
            tree_roots=context.roots,
            latest_by_uuid=context.latest_by_uuid,
            model_name=context.model_info.name,
            preserve_existing_translations=preserve_existing_translations,
        )
        return WorkflowContext(
            report=context.report,
            model_info=context.model_info,
            roots=context.roots,
            entries=context.entries,
            latest_by_uuid=context.latest_by_uuid,
            manifest=manifest,
        )

    def validate_po_against_model(self, po_path: str, model_path: str) -> dict[str, Any]:
        """Validate one PO file against the latest KM model.

        Args:
            po_path: PO file to validate.
            model_path: KM or JSON model path.

        Returns:
            Validation report dictionary.
        """

        po_entries = self._parse_po_entries(po_path)
        latest_by_uuid, _ = self.model_service.load_model(model_path)
        return self.model_service.validate_po_entries(po_entries, latest_by_uuid)

    def write_report(self, report: dict[str, Any], report_path: str) -> None:
        """Write a validation report to disk as JSON.

        Args:
            report: Report dictionary to serialize.
            report_path: Output JSON file path.
        """

        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def build_po_from_tree(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str,
    ) -> PoBuildResult:
        """Generate a PO file from the exported tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the structural template.
            out_po_path: Destination path for the generated PO.

        Returns:
            Result containing generated PO content and validation data.

        Raises:
            ValueError: If tree validation fails.
        """

        po_entries = self._parse_po_entries(original_po_path)
        tree_validation = self.tree_repository.validate(tree_dir, po_entries)
        if tree_validation.errors:
            preview = "\n".join(tree_validation.errors[:50])
            raise ValueError(f"Translation tree validation failed:\n{preview}")

        po_content = self.po_writer.rewrite_translations(
            original_po_path,
            tree_validation.scan_result.translations,
        )
        out_po_file = Path(out_po_path)
        out_po_file.parent.mkdir(parents=True, exist_ok=True)
        out_po_file.write_text(po_content, encoding="utf-8")

        return PoBuildResult(
            po_content=po_content,
            translations=tree_validation.scan_result.translations,
            validation=tree_validation,
            output_po=out_po_file,
        )

    def collect_status(self, tree_dir: str) -> TranslationStatusReport:
        """Collect translation status from the exported tree.

        Args:
            tree_dir: Translation tree directory.

        Returns:
            Translation status report.
        """

        return self.tree_repository.collect_status(tree_dir)

    @staticmethod
    def _parse_po_entries(po_path: str) -> list[PoEntry]:
        """Parse one PO file into flattened `(uuid, field)` entries."""

        return PoCatalogParser(po_path).parse_entries()

    @staticmethod
    def _normalize_model_info(model_info: ModelInfo) -> ModelInfo:
        """Normalize model metadata into the shared dataclass."""

        return ModelInfo(
            id=model_info.id,
            km_id=model_info.km_id,
            name=model_info.name,
        )
