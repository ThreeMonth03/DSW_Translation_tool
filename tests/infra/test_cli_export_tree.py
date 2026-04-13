"""CLI integration tests for translation tree export entrypoints."""

from __future__ import annotations

from tests.infra.support import CliArtifactPaths, assert_cli_success, run_export_tree_cli


def test_export_tree_cli_generates_outline_inside_tree_directory(
    repo_root,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that export-tree CLI writes the default outline under the tree.

    Args:
        repo_root: Repository root fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        outline_name="outline.md",
    )
    outline_path = artifacts.tree_dir / "outline.md"

    result = run_export_tree_cli(
        repo_root=repo_root,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )

    assert_cli_success(result)
    assert f"Wrote translation tree to {artifacts.tree_dir}" in result.stdout
    assert f"Wrote outline markdown to {outline_path}" in result.stdout
    assert outline_path.exists()
    outline_text = outline_path.read_text(encoding="utf-8")
    assert "### Common DSW Knowledge Model" in outline_text
    assert "[KM] [uuid](" in outline_text
