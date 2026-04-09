"""CLI integration tests for translation entrypoints."""

from __future__ import annotations

from tests.helpers import (
    build_entry_map,
    export_tree_for_test,
    parse_po_entries,
    run_cli_script,
    select_multi_reference_block,
    update_tree_field,
    validate_tree,
)


def test_tree_to_po_cli_generates_expected_po(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_entries,
    workspace,
) -> None:
    """Verify that the tree-to-PO CLI rebuilds the expected PO output.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-tree-to-po.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )

    result = run_cli_script(
        repo_root,
        "src/tree_to_po.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(output_po),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Generated PO file:" in result.stdout
    assert output_po.exists()
    assert output_po.read_bytes() == po_path.read_bytes()

    rebuilt_entries = parse_po_entries(output_po)
    assert len(rebuilt_entries) == len(po_entries)


def test_sync_shared_strings_cli_updates_tree_and_outputs_synced_po(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that the sync CLI updates shared strings and writes a PO file.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-sync.po"
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        entries=po_entries,
    )
    _, available_keys = select_multi_reference_block(po_blocks, scan_result)

    chosen_uuid, chosen_field = available_keys[0]
    custom_translation = f"[CLI_SYNC_TEST] {chosen_uuid[:8]}:{chosen_field}"
    for sibling_uuid, sibling_field in available_keys[1:]:
        update_tree_field(
            workflow=workflow,
            scan_result=scan_result,
            uuid=sibling_uuid,
            field=sibling_field,
            target_text="",
        )
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=chosen_uuid,
        field=chosen_field,
        target_text=custom_translation,
    )

    result = run_cli_script(
        repo_root,
        "src/sync_shared_strings.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(output_po),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Shared String Sync" in result.stdout
    assert "Conflicts      : 0" in result.stdout
    assert output_po.exists()

    synced_scan = workflow.tree_repository.scan(str(tree_dir))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == custom_translation

    rebuilt_entries = build_entry_map(parse_po_entries(output_po))
    for uuid, field in available_keys:
        assert rebuilt_entries[(uuid, field)].msgstr == custom_translation

    report = workflow.validate_po_against_model(str(output_po), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0
