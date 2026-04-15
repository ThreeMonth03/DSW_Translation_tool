"""CLI integration tests for backup, restore, and watch-mode resilience."""

from __future__ import annotations

import shutil
from argparse import Namespace

import sync_shared_strings
from tests.helpers import (
    corrupt_translation_by_appending_outside_fence,
    corrupt_translation_by_appending_to_event_type_header,
    corrupt_translation_by_breaking_final_fence,
    corrupt_translation_by_renaming_first_field_heading,
    export_tree_for_test,
    find_first_translatable_snapshot,
)
from tests.infra.support import (
    CliArtifactPaths,
    assert_cli_success,
    run_sync_cli,
    run_tree_to_po_cli,
)


def test_tree_to_po_cli_restores_file_when_text_is_written_outside_fence(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that tree-to-PO restores the last good file after fence leakage.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="invalid-outside-fence.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_appending_outside_fence(snapshot.translation_path)

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert result.returncode != 0
    assert "restored from the last known-good backup" in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert artifacts.output_po.exists() is False
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


def test_sync_cli_restores_file_when_fence_structure_is_broken(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync restores the last good file after a broken fence.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="invalid-broken-fence.po",
        diff_name="invalid-broken-fence.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_breaking_final_fence(snapshot.translation_path)

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert result.returncode != 0
    assert "restored from the last known-good backup" in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert artifacts.output_po.exists() is False
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists() is False
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


def test_sync_cli_restores_shared_block_translation_file_when_a_group_file_is_deleted(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync restores one shared-block context file after deletion.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="invalid-shared-blocks.po",
        diff_name="invalid-shared-blocks.diff",
        shared_blocks_outline_name="shared_blocks_outline.md",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    workflow.build_shared_blocks_directory(
        tree_dir=str(artifacts.tree_dir),
        original_po_path=str(po_path),
        out_shared_blocks_root=str(artifacts.shared_blocks_dir_path),
    )
    context_files = sorted(artifacts.shared_blocks_dir_path.glob("*/context.md"))
    assert context_files
    deleted_context_path = context_files[1]
    original_text = deleted_context_path.read_text(encoding="utf-8")
    deleted_context_path.unlink()

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
        shared_blocks_dir_path=artifacts.shared_blocks_dir_path,
        shared_blocks_outline_path=artifacts.shared_blocks_outline_path,
    )

    assert result.returncode != 0
    assert (
        "Invalid shared-block context files were restored from the last known-good backup"
        in result.stderr
    )
    assert str(deleted_context_path) in result.stderr
    assert artifacts.output_po.exists() is False
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists() is False
    assert deleted_context_path.read_text(encoding="utf-8") == original_text


def test_sync_cli_restores_file_when_event_type_header_is_corrupted(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync restores the last good file after header corruption.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="invalid-event-type-header.po",
        diff_name="invalid-event-type-header.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_appending_to_event_type_header(snapshot.translation_path)

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert result.returncode != 0
    assert "restored from the last known-good backup" in result.stderr
    assert "Malformed Event Type metadata header." in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert artifacts.output_po.exists() is False
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists() is False
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


def test_sync_cli_rejects_renamed_field_heading_before_group_sync(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync rejects invalid field headings before propagating.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="invalid-field-heading.po",
        diff_name="invalid-field-heading.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_renaming_first_field_heading(snapshot.translation_path)

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert result.returncode != 0
    assert "Translation tree validation failed:" in result.stderr
    assert "Missing translation block:" in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert artifacts.output_po.exists() is False
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists() is False
    assert snapshot.translation_path.read_text(encoding="utf-8") != original_text


def test_sync_cli_restores_deleted_uuid_file_and_succeeds(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync restores a deleted `_uuid.txt` file from manifest.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="restored-missing-uuid.po",
        diff_name="restored-missing-uuid.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    uuid_path = snapshot.translation_path.parent / "_uuid.txt"
    uuid_path.unlink()

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert artifacts.output_po.read_bytes() == po_path.read_bytes()
    assert uuid_path.exists()
    assert uuid_path.read_text(encoding="utf-8") == snapshot.entity_uuid
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()
    assert artifacts.diff_path.read_text(encoding="utf-8") == ""


def test_tree_to_po_cli_restores_deleted_translation_file_and_succeeds(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that tree-to-PO restores a deleted translation file from backup.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="restored-missing-translation.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    original_text = snapshot.translation_path.read_text(encoding="utf-8")
    snapshot.translation_path.unlink()

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    assert artifacts.output_po.read_bytes() == po_path.read_bytes()
    assert snapshot.translation_path.exists()
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


def test_sync_cli_restores_deleted_node_folder_and_succeeds(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync restores a deleted translatable node folder.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="restored-missing-folder.po",
        diff_name="restored-missing-folder.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=artifacts.tree_dir)
    assert snapshot.translation_path is not None
    folder_path = snapshot.translation_path.parent
    original_text = snapshot.translation_path.read_text(encoding="utf-8")
    shutil.rmtree(folder_path)

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert artifacts.output_po.read_bytes() == po_path.read_bytes()
    assert folder_path.exists()
    assert (folder_path / "_uuid.txt").read_text(encoding="utf-8") == snapshot.entity_uuid
    assert (folder_path / "translation.md").read_text(encoding="utf-8") == original_text
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()
    assert artifacts.diff_path.read_text(encoding="utf-8") == ""


def test_sync_watch_reports_errors_without_exiting_the_loop(
    monkeypatch,
    capsys,
) -> None:
    """Verify that watch mode reports sync errors and continues running.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Pytest output capture fixture.
    """

    args = Namespace(
        tree_dir="unused-tree",
        original_po="unused.po",
        out_po="unused-final.po",
        diff_out="unused.diff",
        outline_out="unused-outline.md",
        shared_blocks_dir_out="unused-shared-dir",
        shared_blocks_outline_out="unused-shared-outline.md",
        source_lang="en",
        target_lang="zh_Hant",
        group_by="shared-block",
        watch=True,
    )
    service_calls: list[str] = []

    class _Parser:
        """Minimal parser stub for watch-mode testing."""

        def parse_args(self) -> Namespace:
            """Return the preconstructed watch-mode arguments."""

            return args

    monkeypatch.setattr(sync_shared_strings, "build_argument_parser", lambda: _Parser())

    class _Service:
        """Minimal watch-service stub that simulates one failed rerun."""

        def run(self) -> None:
            """Emit two watch cycles, then stop through keyboard interrupt."""

            service_calls.append("run")
            print("[sync] Running at 2026-04-09 18:00:00")
            print("[sync] Error: broken translation.md was restored")
            print()
            print("[sync] Running at 2026-04-09 18:00:00")
            raise KeyboardInterrupt

    monkeypatch.setattr(sync_shared_strings, "build_watch_service", lambda _: _Service())

    sync_shared_strings.main()

    captured = capsys.readouterr()
    assert service_calls == ["run"]
    assert "[sync] Error: broken translation.md was restored" in captured.out
    assert "Stopped shared-string watch mode." in captured.out
