"""File-output helpers for high-level translation workflow services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..data_models import PoBuildResult, PoDiffReviewResult, TreeValidationResult
from ..po import PoCatalogWriter


class TranslationWorkflowOutputService:
    """Persist workflow outputs such as reports, PO files, and diffs.

    Args:
        po_writer: PO writer used to generate final PO text from translations.
    """

    def __init__(self, po_writer: PoCatalogWriter):
        self.po_writer = po_writer

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

    def build_po_result(
        self,
        original_po_path: str,
        out_po_path: str,
        validation: TreeValidationResult,
    ) -> PoBuildResult:
        """Write a generated PO file from a validated tree scan.

        Args:
            original_po_path: Original PO used as the structural template.
            out_po_path: Destination path for the generated PO.
            validation: Validation result produced for the source tree.

        Returns:
            Generated PO build result.
        """

        po_content = self.po_writer.rewrite_translations(
            original_po_path,
            validation.scan_result.translations,
        )
        out_po_file = Path(out_po_path)
        out_po_file.parent.mkdir(parents=True, exist_ok=True)
        out_po_file.write_text(po_content, encoding="utf-8")
        return PoBuildResult(
            po_content=po_content,
            translations=validation.scan_result.translations,
            validation=validation,
            output_po=out_po_file,
        )

    def write_diff_review(
        self,
        review: PoDiffReviewResult,
        diff_out_path: str | None = None,
    ) -> PoDiffReviewResult:
        """Persist a diff review when an output path is requested.

        Args:
            review: Review result to persist.
            diff_out_path: Optional destination path for unified diff output.

        Returns:
            The original review result for fluent workflow composition.
        """

        if not diff_out_path:
            return review
        diff_file = Path(diff_out_path)
        diff_file.parent.mkdir(parents=True, exist_ok=True)
        diff_file.write_text(review.diff_text, encoding="utf-8")
        return review
