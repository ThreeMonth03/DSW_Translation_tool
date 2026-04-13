"""CLI integration tests for PO review tooling."""

from __future__ import annotations

from tests.helpers import (
    apply_translation_map_to_tree,
    build_empty_msgstr_translation_map,
    export_tree_for_test,
)
from tests.infra.support import (
    CliArtifactPaths,
    assert_cli_success,
    run_review_po_cli,
    run_tree_to_po_cli,
)


def test_review_po_cli_reports_msgstr_only_changes_for_generated_output(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Verify that PO review CLI reports msgstr-only changes correctly.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="review-source.po",
        diff_name="review.diff",
    )

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    build_result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )
    assert_cli_success(build_result)

    assert artifacts.diff_path is not None
    review_result = run_review_po_cli(
        repo_root,
        po_path,
        artifacts.output_po,
        artifacts.diff_path,
        "--fail-on-non-msgstr",
    )

    assert_cli_success(review_result)
    assert "PO Review" in review_result.stdout
    assert "Msgstr only           : True" in review_result.stdout
    assert artifacts.diff_path.exists()
    assert "@@" in artifacts.diff_path.read_text(encoding="utf-8")
