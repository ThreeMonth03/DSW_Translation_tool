"""Tests for shared-block split and synchronization behaviour."""

from __future__ import annotations

from tests.helpers import (
    build_entry_map,
    export_tree_for_test,
    future_timestamp,
    parse_po_blocks,
    parse_po_entries,
    rebuild_po_from_tree,
    run_shared_string_sync,
    select_multi_reference_block,
    update_tree_field,
    validate_tree,
)


def test_tree_to_po_splits_shared_block_when_one_translation_diverges(
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Changing one shared reference should split, not corrupt, the PO block."""

    tree_dir = workspace / "tree"
    output_po = workspace / "split.po"
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    scan_result = workflow.tree_repository.scan(str(tree_dir))
    block, available_keys = select_multi_reference_block(po_blocks, scan_result)

    changed_uuid, changed_field = available_keys[0]
    custom_translation = f"[ROUNDTRIP_SPLIT_TEST] {changed_uuid[:8]}:{changed_field}"
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=changed_uuid,
        field=changed_field,
        target_text=custom_translation,
    )

    rebuilt_po = rebuild_po_from_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        original_po_path=po_path,
        output_po_path=output_po,
    )
    rebuilt_blocks = parse_po_blocks(rebuilt_po)
    rebuilt_entry_map = build_entry_map(parse_po_entries(rebuilt_po))

    assert rebuilt_entry_map[(changed_uuid, changed_field)].msgstr == custom_translation
    for sibling_key in available_keys[1:]:
        assert rebuilt_entry_map[sibling_key].msgstr == block.msgstr

    original_keys = {(reference.uuid, reference.field) for reference in block.references}
    matching_blocks = []
    covered_keys = set()
    for rebuilt_block in rebuilt_blocks:
        rebuilt_keys = {
            (reference.uuid, reference.field)
            for reference in rebuilt_block.references
        }
        if not rebuilt_keys.intersection(original_keys):
            continue
        matching_blocks.append(rebuilt_block)
        covered_keys.update(rebuilt_keys)

    assert len(matching_blocks) >= 2
    assert covered_keys == original_keys


def test_shared_string_sync_propagates_translation_across_matching_nodes(
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Sync should fill sibling references in the same shared block."""

    tree_dir = workspace / "tree"
    output_po = workspace / "synced.po"
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
    block, available_keys = select_multi_reference_block(po_blocks, scan_result)

    custom_translation = f"[SYNC_TEST] {available_keys[0][0][:8]}:{available_keys[0][1]}"
    stale_timestamp = future_timestamp(-5.0)
    fresh_timestamp = future_timestamp(5.0)

    for sibling_uuid, sibling_field in available_keys[1:]:
        update_tree_field(
            workflow=workflow,
            scan_result=scan_result,
            uuid=sibling_uuid,
            field=sibling_field,
            target_text="",
            modified_at=stale_timestamp,
        )
    chosen_uuid, chosen_field = available_keys[0]
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=chosen_uuid,
        field=chosen_field,
        target_text=custom_translation,
        modified_at=fresh_timestamp,
    )

    result = run_shared_string_sync(
        workflow=workflow,
        tree_dir=tree_dir,
        original_po_path=po_path,
        output_po_path=output_po,
    )

    assert result.groups_updated >= 1
    assert result.fields_updated >= len(available_keys) - 1
    assert result.conflicts == ()

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

    original_keys = {(reference.uuid, reference.field) for reference in block.references}
    assert set(available_keys).issubset(original_keys)
