"""Shared support helpers for infrastructure-oriented CLI tests."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from dsw_translation_tool.workflow import TranslationWorkflowService
from tests.helpers import run_cli_script


@dataclass(frozen=True)
class CliArtifactPaths:
    """Group the filesystem artifacts produced by one CLI test scenario.

    Args:
        tree_dir: Translation tree directory for the test workspace.
        output_po: Optional generated PO output path.
        diff_path: Optional diff output path.
        outline_path: Optional outline markdown path.
        shared_blocks_outline_path: Optional shared-block outline markdown path.
    """

    tree_dir: Path
    output_po: Path | None = None
    diff_path: Path | None = None
    outline_path: Path | None = None
    shared_blocks_outline_path: Path | None = None

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        output_po_name: str | None = None,
        diff_name: str | None = None,
        outline_name: str | None = None,
        shared_blocks_outline_name: str | None = None,
        tree_name: str = "tree",
    ) -> "CliArtifactPaths":
        """Build one artifact bundle rooted in a pytest workspace directory.

        Args:
            workspace: Per-test workspace root.
            output_po_name: Optional PO filename placed under the workspace root.
            diff_name: Optional diff filename placed under the workspace root.
            outline_name: Optional outline filename placed under the workspace root.
            shared_blocks_outline_name: Optional shared-block outline filename
                placed under the tree directory.
            tree_name: Directory name to use for the translation tree.

        Returns:
            Artifact path bundle rooted in the supplied workspace.
        """

        return cls(
            tree_dir=workspace / tree_name,
            output_po=workspace / output_po_name if output_po_name else None,
            diff_path=workspace / diff_name if diff_name else None,
            outline_path=workspace / outline_name if outline_name else None,
            shared_blocks_outline_path=(
                (workspace / tree_name / shared_blocks_outline_name)
                if shared_blocks_outline_name
                else None
            ),
        )

    @property
    def shared_blocks_dir_path(self) -> Path:
        """Return the canonical split shared-block directory path."""

        return self.tree_dir / "shared_blocks"


def assert_cli_success(result: subprocess.CompletedProcess[str]) -> None:
    """Assert that one CLI process completed successfully.

    Args:
        result: Completed CLI process.
    """

    assert result.returncode == 0, result.stderr or result.stdout


def assert_clean_model_validation(
    workflow: TranslationWorkflowService,
    po_path: Path,
    model_path: Path,
) -> None:
    """Assert that one generated PO validates cleanly against the KM model.

    Args:
        workflow: Workflow service fixture.
        po_path: Generated PO path.
        model_path: KM file path.
    """

    report = workflow.validate_po_against_model(str(po_path), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0


def po_block_skeleton(block) -> tuple[tuple[str, ...], str, bool]:
    """Return the non-translation identity of one PO block.

    Args:
        block: Parsed PO block.

    Returns:
        Tuple containing references, `msgid`, and fuzzy status.
    """

    return (
        tuple(reference.comment for reference in block.references),
        block.msgid,
        block.is_fuzzy,
    )


def run_export_tree_cli(
    repo_root: Path,
    po_path: Path,
    model_path: Path,
    tree_dir: Path,
    outline_path: Path | None = None,
    shared_blocks_dir_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the export-tree CLI script for one test scenario.

    Args:
        repo_root: Repository root used as subprocess cwd.
        po_path: Source PO path.
        model_path: KM model path.
        tree_dir: Destination tree directory.
        outline_path: Optional explicit outline output path.
        shared_blocks_dir_path: Optional explicit shared-block directory path.

    Returns:
        Completed subprocess result.
    """

    args = [
        "--po",
        str(po_path),
        "--json",
        str(model_path),
        "--out-dir",
        str(tree_dir),
    ]
    if outline_path is not None:
        args.extend(["--outline-out", str(outline_path)])
    if shared_blocks_dir_path is not None:
        args.extend(["--shared-blocks-dir-out", str(shared_blocks_dir_path)])
    return run_cli_script(repo_root, "src/po_json_tree.py", *args)


def run_tree_to_po_cli(
    repo_root: Path,
    tree_dir: Path,
    original_po_path: Path,
    output_po_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the tree-to-PO CLI script for one test scenario.

    Args:
        repo_root: Repository root used as subprocess cwd.
        tree_dir: Translation tree directory.
        original_po_path: Original PO template path.
        output_po_path: Generated PO output path.

    Returns:
        Completed subprocess result.
    """

    return run_cli_script(
        repo_root,
        "src/tree_to_po.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(original_po_path),
        "--out-po",
        str(output_po_path),
    )


def run_sync_cli(
    repo_root: Path,
    tree_dir: Path,
    original_po_path: Path,
    output_po_path: Path,
    diff_path: Path | None = None,
    outline_path: Path | None = None,
    shared_blocks_dir_path: Path | None = None,
    shared_blocks_outline_path: Path | None = None,
    group_by: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the shared-string sync CLI script for one test scenario.

    Args:
        repo_root: Repository root used as subprocess cwd.
        tree_dir: Translation tree directory.
        original_po_path: Original PO template path.
        output_po_path: Generated PO output path.
        diff_path: Optional diff output path.
        outline_path: Optional outline markdown output path.
        shared_blocks_dir_path: Optional canonical shared-block directory path.
        shared_blocks_outline_path: Optional shared-block outline output path.
        group_by: Optional grouping strategy override.

    Returns:
        Completed subprocess result.
    """

    args = [
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(original_po_path),
        "--out-po",
        str(output_po_path),
    ]
    if diff_path is not None:
        args.extend(["--diff-out", str(diff_path)])
    if outline_path is not None:
        args.extend(["--outline-out", str(outline_path)])
    if shared_blocks_dir_path is not None:
        args.extend(["--shared-blocks-dir-out", str(shared_blocks_dir_path)])
    if shared_blocks_outline_path is not None:
        args.extend(["--shared-blocks-outline-out", str(shared_blocks_outline_path)])
    if group_by is not None:
        args.extend(["--group-by", group_by])
    return run_cli_script(repo_root, "src/sync_shared_strings.py", *args)


def run_review_po_cli(
    repo_root: Path,
    original_po_path: Path,
    generated_po_path: Path,
    diff_path: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    """Run the PO review CLI script for one test scenario.

    Args:
        repo_root: Repository root used as subprocess cwd.
        original_po_path: Original PO baseline path.
        generated_po_path: Generated PO path under review.
        diff_path: Unified diff output path.
        *extra_args: Additional CLI arguments.

    Returns:
        Completed subprocess result.
    """

    return run_cli_script(
        repo_root,
        "src/review_po_changes.py",
        "--original-po",
        str(original_po_path),
        "--generated-po",
        str(generated_po_path),
        "--diff-out",
        str(diff_path),
        *extra_args,
    )
