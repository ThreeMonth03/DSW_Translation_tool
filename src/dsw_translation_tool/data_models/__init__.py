"""Structured data-model exports grouped by translation-tooling concern."""

from .knowledge_model import ModelInfo, TreeNode
from .po import (
    PoBlock,
    PoDiffReviewResult,
    PoEntry,
    PoReference,
    PoReferenceSection,
    PoTranslationGroup,
)
from .sync import SharedStringCandidate, SharedStringConflict, SharedStringSyncResult
from .tree import (
    OutlineBuildResult,
    TranslationFieldState,
    TranslationStatusFolder,
    TranslationStatusReport,
    TranslationStatusSummary,
    TreeFolderSnapshot,
    TreeScanResult,
    TreeValidationResult,
)
from .workflow import PoBuildResult, WorkflowContext

__all__ = [
    "ModelInfo",
    "OutlineBuildResult",
    "PoBlock",
    "PoBuildResult",
    "PoDiffReviewResult",
    "PoEntry",
    "PoReference",
    "PoReferenceSection",
    "PoTranslationGroup",
    "SharedStringCandidate",
    "SharedStringConflict",
    "SharedStringSyncResult",
    "TranslationFieldState",
    "TranslationStatusFolder",
    "TranslationStatusReport",
    "TranslationStatusSummary",
    "TreeFolderSnapshot",
    "TreeNode",
    "TreeScanResult",
    "TreeValidationResult",
    "WorkflowContext",
]
