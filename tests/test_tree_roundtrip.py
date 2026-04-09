"""Tests for tree -> PO round-trip integrity."""

from __future__ import annotations

from tests.helpers import export_tree_for_test, parse_po_entries, rebuild_po_from_tree


def test_untouched_tree_roundtrip_rebuilds_byte_identical_po(
    workflow,
    po_path,
    model_path,
    po_entries,
    workspace,
) -> None:
    """Untouched export/import should rebuild the exact same PO bytes."""

    tree_dir = workspace / "tree"
    output_po = workspace / "roundtrip.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    rebuilt_po = rebuild_po_from_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        original_po_path=po_path,
        output_po_path=output_po,
    )

    assert rebuilt_po.read_bytes() == po_path.read_bytes()

    rebuilt_entries = parse_po_entries(rebuilt_po)
    assert len(rebuilt_entries) == len(po_entries)

    report = workflow.validate_po_against_model(str(rebuilt_po), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0
