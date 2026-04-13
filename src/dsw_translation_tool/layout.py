"""Canonical path layout helpers for translation collaboration artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE_LANG = "en"
DEFAULT_TARGET_LANG = "zh_Hant"
DEFAULT_PO_PATH = Path("files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po")
DEFAULT_MODEL_PATH = Path("files/dsw_root_2.7.0.km")


@dataclass(frozen=True)
class TranslationOutputLayout:
    """Describe the default collaboration output layout for one language.

    Args:
        output_root: Root directory containing the collaboration artifacts.
        target_lang: Target language code for this layout.
    """

    output_root: Path
    target_lang: str = DEFAULT_TARGET_LANG

    @classmethod
    def for_target_lang(
        cls,
        target_lang: str = DEFAULT_TARGET_LANG,
    ) -> "TranslationOutputLayout":
        """Build the canonical output layout for one target language.

        Args:
            target_lang: Target language code.

        Returns:
            Layout instance rooted under `translation/<target_lang>`.
        """

        return cls(
            output_root=Path("translation") / target_lang,
            target_lang=target_lang,
        )

    @property
    def tree_dir(self) -> Path:
        """Return the translation tree directory."""

        return self.output_root / "tree"

    @property
    def outline_path(self) -> Path:
        """Return the outline markdown path inside the tree root."""

        return self.tree_dir / "outline.md"

    @property
    def final_po_path(self) -> Path:
        """Return the generated final PO path."""

        return self.output_root / "builds" / "final_translated.po"

    @property
    def diff_path(self) -> Path:
        """Return the generated review diff path."""

        return self.output_root / "reviews" / "final_translated.diff"

    @property
    def report_path(self) -> Path:
        """Return the generated validation report path."""

        return self.output_root / "reports" / "final_report.json"

    @property
    def tree_snapshot_path(self) -> Path:
        """Return the optional JSON tree snapshot path."""

        return self.output_root / "reports" / "tree_snapshot.json"

    @property
    def backup_root(self) -> Path:
        """Return the local backup root for this collaboration tree."""

        return self.output_root / "backups" / "tree"


DEFAULT_LAYOUT = TranslationOutputLayout.for_target_lang()
