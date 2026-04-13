"""PO review and diff-reporting services."""

from __future__ import annotations

import difflib
from pathlib import Path

from .data_models import PoBlock, PoDiffReviewResult
from .po import PoCatalogParser


class PoDiffReviewer:
    """Review semantic and textual differences between two PO files."""

    def review(
        self,
        original_po_path: str,
        generated_po_path: str,
    ) -> PoDiffReviewResult:
        """Compare two PO files and summarize their differences.

        Args:
            original_po_path: Original PO template path.
            generated_po_path: Generated PO file path.

        Returns:
            Structured review summary including unified diff text.
        """

        original_blocks = PoCatalogParser(original_po_path).parse_blocks()
        generated_blocks = PoCatalogParser(generated_po_path).parse_blocks()
        diff_text = self._build_unified_diff(
            original_po_path=original_po_path,
            generated_po_path=generated_po_path,
        )

        changed_blocks = 0
        changed_msgstr_blocks = 0
        changed_msgid_blocks = 0
        changed_reference_blocks = 0
        changed_fuzzy_blocks = 0

        paired_length = min(len(original_blocks), len(generated_blocks))
        for index in range(paired_length):
            original_block = original_blocks[index]
            generated_block = generated_blocks[index]
            block_changed = False

            if self._reference_tokens(original_block) != self._reference_tokens(generated_block):
                changed_reference_blocks += 1
                block_changed = True
            if original_block.msgid != generated_block.msgid:
                changed_msgid_blocks += 1
                block_changed = True
            if original_block.msgstr != generated_block.msgstr:
                changed_msgstr_blocks += 1
                block_changed = True
            if original_block.is_fuzzy != generated_block.is_fuzzy:
                changed_fuzzy_blocks += 1
                block_changed = True

            if block_changed:
                changed_blocks += 1

        inserted_blocks = max(0, len(generated_blocks) - len(original_blocks))
        deleted_blocks = max(0, len(original_blocks) - len(generated_blocks))
        msgstr_only = (
            changed_msgid_blocks == 0
            and changed_reference_blocks == 0
            and changed_fuzzy_blocks == 0
            and inserted_blocks == 0
            and deleted_blocks == 0
        )

        return PoDiffReviewResult(
            total_blocks=len(original_blocks),
            changed_blocks=changed_blocks + inserted_blocks + deleted_blocks,
            changed_msgstr_blocks=changed_msgstr_blocks,
            changed_msgid_blocks=changed_msgid_blocks,
            changed_reference_blocks=changed_reference_blocks,
            changed_fuzzy_blocks=changed_fuzzy_blocks,
            inserted_blocks=inserted_blocks,
            deleted_blocks=deleted_blocks,
            msgstr_only=msgstr_only,
            diff_text=diff_text,
        )

    @staticmethod
    def _reference_tokens(block: PoBlock) -> tuple[str, ...]:
        """Return stable reference tokens for one PO block."""

        return tuple(reference.comment for reference in block.references)

    @staticmethod
    def _build_unified_diff(
        original_po_path: str,
        generated_po_path: str,
    ) -> str:
        """Build unified diff text for two PO files."""

        original_lines = (
            Path(original_po_path).read_text(encoding="utf-8").splitlines(keepends=True)
        )
        generated_lines = (
            Path(generated_po_path).read_text(encoding="utf-8").splitlines(keepends=True)
        )
        return "".join(
            difflib.unified_diff(
                original_lines,
                generated_lines,
                fromfile=Path(original_po_path).name,
                tofile=Path(generated_po_path).name,
            )
        )
