"""High-level translation workflow facade services."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .data_models import (
    OutlineBuildResult,
    PoBuildResult,
    PoDiffReviewResult,
    SharedStringSyncResult,
    TranslationStatusReport,
    WorkflowContext,
)
from .knowledge_model_service import KnowledgeModelService
from .outline import TranslationOutlineBuilder
from .po import PoCatalogWriter
from .review import PoDiffReviewer
from .sync import SharedStringSynchronizer
from .tree import TranslationTreeRepository
from .workflow_support import (
    TranslationWorkflowContextBuilder,
    TranslationWorkflowOutputService,
)


class TranslationWorkflowService:
    """Coordinate PO parsing, KM loading, tree export, and PO rebuild steps.

    Args:
        source_lang: Source language code used by the workflow.
        target_lang: Target language code used by the workflow.
        tree_repository: Optional injected translation tree repository.
        model_service: Optional injected model service class or instance.
        po_writer: Optional injected PO writer.
        reviewer: Optional injected PO diff reviewer.
        synchronizer: Optional injected shared-string synchronizer.
        outline_builder: Optional injected outline builder.
        context_builder: Optional injected workflow-context builder.
        output_service: Optional injected workflow-output writer service.
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
        tree_repository: TranslationTreeRepository | None = None,
        model_service: KnowledgeModelService | None = None,
        po_writer: PoCatalogWriter | None = None,
        reviewer: PoDiffReviewer | None = None,
        synchronizer: SharedStringSynchronizer | None = None,
        outline_builder: TranslationOutlineBuilder | None = None,
        context_builder: TranslationWorkflowContextBuilder | None = None,
        output_service: TranslationWorkflowOutputService | None = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.tree_repository = tree_repository or TranslationTreeRepository(
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self.model_service = model_service or KnowledgeModelService()
        self.po_writer = po_writer or PoCatalogWriter()
        self.reviewer = reviewer or PoDiffReviewer()
        self.synchronizer = synchronizer or SharedStringSynchronizer(
            tree_repository=self.tree_repository,
            po_writer=self.po_writer,
        )
        self.outline_builder = outline_builder or TranslationOutlineBuilder(
            tree_repository=self.tree_repository,
        )
        self.context_builder = context_builder or TranslationWorkflowContextBuilder(
            model_service=self.model_service,
        )
        self.output_service = output_service or TranslationWorkflowOutputService(
            po_writer=self.po_writer,
        )

    def build_tree_context(self, po_path: str, model_path: str) -> WorkflowContext:
        """Build the in-memory workflow context for a PO/KM pair.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.

        Returns:
            Workflow context used by export and validation steps.
        """

        return self.context_builder.build(po_path=po_path, model_path=model_path)

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

        return self.context_builder.validate_po_against_model(
            po_path=po_path,
            model_path=model_path,
        )

    def write_report(self, report: dict[str, Any], report_path: str) -> None:
        """Write a validation report to disk as JSON.

        Args:
            report: Report dictionary to serialize.
            report_path: Output JSON file path.
        """

        self.output_service.write_report(
            report=report,
            report_path=report_path,
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

        po_entries = self.context_builder.parse_po_entries(original_po_path)
        tree_validation = self.tree_repository.validate(tree_dir, po_entries)
        if tree_validation.errors:
            preview = "\n".join(tree_validation.errors[:50])
            raise ValueError(f"Translation tree validation failed:\n{preview}")

        return self.output_service.build_po_result(
            original_po_path=original_po_path,
            out_po_path=out_po_path,
            validation=tree_validation,
        )

    def collect_status(self, tree_dir: str) -> TranslationStatusReport:
        """Collect translation status from the exported tree.

        Args:
            tree_dir: Translation tree directory.

        Returns:
            Translation status report.
        """

        return self.tree_repository.collect_status(tree_dir)

    def sync_shared_strings(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str | None = None,
        outline_out_path: str | None = None,
        group_by: str = "shared-block",
    ) -> SharedStringSyncResult:
        """Synchronize repeated translation groups across an exported tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the grouping source.
            out_po_path: Optional destination path for the refreshed PO file.
            outline_out_path: Optional destination path for outline markdown.
            group_by: Grouping strategy used to define shared-string sets.

        Returns:
            Summary of the shared-string synchronization run.
        """

        result = self.synchronizer.sync(
            tree_dir=tree_dir,
            original_po_path=original_po_path,
            out_po_path=out_po_path,
            group_by=group_by,
        )
        if not outline_out_path:
            return result

        outline_result = self.build_outline_markdown(
            tree_dir=tree_dir,
            out_outline_path=outline_out_path,
        )
        return replace(
            result,
            output_outline=str(outline_result.output_outline),
        )

    def build_outline_markdown(
        self,
        tree_dir: str,
        out_outline_path: str,
    ) -> OutlineBuildResult:
        """Build a markdown outline for the current collaboration tree.

        Args:
            tree_dir: Translation tree directory.
            out_outline_path: Destination markdown path.

        Returns:
            Outline build result.
        """

        return self.outline_builder.build(
            tree_dir=tree_dir,
            output_outline_path=out_outline_path,
        )

    def review_po_changes(
        self,
        original_po_path: str,
        generated_po_path: str,
        diff_out_path: str | None = None,
    ) -> PoDiffReviewResult:
        """Review semantic and textual differences between two PO files.

        Args:
            original_po_path: Original PO template path.
            generated_po_path: Generated PO file path to review.
            diff_out_path: Optional destination path for unified diff output.

        Returns:
            Structured diff-review result.
        """

        review = self.reviewer.review(
            original_po_path=original_po_path,
            generated_po_path=generated_po_path,
        )
        return self.output_service.write_diff_review(
            review=review,
            diff_out_path=diff_out_path,
        )
