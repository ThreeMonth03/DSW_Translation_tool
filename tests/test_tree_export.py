"""Tests for PO -> tree export coverage."""

from __future__ import annotations

from tests.helpers import (
    build_entry_map,
    build_expected_fields_by_uuid,
    export_tree_for_test,
    find_markdown_fence_collisions,
    validate_tree,
)


def test_export_tree_contains_all_expected_translation_fields(
    workflow,
    po_path,
    model_path,
    po_entries,
    workspace,
) -> None:
    """Verify that tree export preserves every PO translation field.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    entry_map = build_entry_map(po_entries)
    expected_fields = build_expected_fields_by_uuid(po_entries)
    tree_dir = workspace / "tree"

    assert find_markdown_fence_collisions(po_entries) == []

    context = export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )

    assert context.report["missingEntities"] == 0
    assert context.report["missingFields"] == 0
    assert context.report["mismatches"] == 0

    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        entries=po_entries,
    )

    assert len(scan_result.translations) == len(entry_map)
    assert scan_result.duplicate_uuids == ()

    for entry in entry_map.values():
        snapshot = scan_result.folders_by_uuid[entry.uuid]
        state = snapshot.fields[entry.field]
        assert state.source_text == entry.msgid
        assert state.target_text == entry.msgstr

    for entity_uuid, snapshot in scan_result.folders_by_uuid.items():
        assert set(snapshot.fields.keys()) == expected_fields.get(entity_uuid, set())
