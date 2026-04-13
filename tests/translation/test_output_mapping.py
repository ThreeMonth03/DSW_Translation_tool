"""Tests that validate checked-in collaboration output state."""

from __future__ import annotations

import shutil

import pytest

from tests.helpers import (
    build_entry_map,
    build_outline_markdown,
    corrupt_translation_by_appending_outside_fence,
    corrupt_translation_by_breaking_final_fence,
    inspect_translation_tree_disk_state,
    parse_po_blocks,
    parse_po_entries,
    read_translation_markdown_header,
    read_tree_manifest,
)


def test_collaboration_tree_disk_state_matches_expected_uuid_field_mapping(
    workflow,
    po_entries,
    collaboration_tree_dir,
) -> None:
    """Verify that the checked-in collaboration tree is structurally intact.

    This test reads `translation/zh_Hant/tree` directly from disk. It is meant to
    fail when a translator accidentally deletes files, removes folders, edits
    outside the fenced blocks, or breaks the markdown template.

    Args:
        workflow: Workflow service fixture.
        po_entries: Flattened source PO entries fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
    """

    _, field_states = inspect_translation_tree_disk_state(
        workflow=workflow,
        tree_dir=collaboration_tree_dir,
    )
    source_entry_map = build_entry_map(po_entries)

    assert set(field_states) == set(source_entry_map)
    for key, state in field_states.items():
        entry = source_entry_map[key]
        assert state.source_text == entry.msgid


def test_collaboration_translation_markdown_headers_match_manifest_metadata(
    collaboration_tree_dir,
) -> None:
    """Verify that checked-in translation headers match manifest metadata.

    Args:
        collaboration_tree_dir: Checked-in collaboration tree directory.
    """

    manifest = read_tree_manifest(collaboration_tree_dir)
    for entity_uuid, node in manifest["nodes"].items():
        if not node.get("fields"):
            continue
        translation_path = collaboration_tree_dir / node["path"] / "translation.md"
        header_uuid, header_event_type = read_translation_markdown_header(
            translation_path
        )
        assert header_uuid == entity_uuid
        assert header_event_type == node.get("eventType")


def test_collaboration_tree_and_generated_po_stay_in_sync(
    workflow,
    po_path,
    po_entries,
    model_path,
    collaboration_tree_dir,
    collaboration_final_po_path,
) -> None:
    """Verify that checked-in tree translations match the generated PO file.

    This test is intentionally strict for collaboration workflows. If someone
    edits `translation.md` but forgets to run `make sync`, `make sync-watch`,
    or `make tree-to-po`, the test must fail and point at the mismatch.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        po_entries: Flattened source PO entries fixture.
        model_path: Fixture KM file path.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        collaboration_final_po_path: Checked-in generated PO path.
    """

    manifest, field_states = inspect_translation_tree_disk_state(
        workflow=workflow,
        tree_dir=collaboration_tree_dir,
    )
    assert collaboration_final_po_path.exists(), (
        "Missing generated collaboration PO file: "
        f"{collaboration_final_po_path}\n"
        "Run `make sync` or `make tree-to-po` before running translation tests."
    )

    po_entry_map = build_entry_map(parse_po_entries(collaboration_final_po_path))
    source_entry_map = build_entry_map(po_entries)

    assert set(po_entry_map) == set(field_states)
    for key, state in field_states.items():
        uuid, field = key
        node = manifest["nodes"][uuid]
        translation_path = collaboration_tree_dir / node["path"] / "translation.md"
        built_entry = po_entry_map[key]
        source_entry = source_entry_map[key]
        assert built_entry.msgid == source_entry.msgid
        assert built_entry.msgid == state.source_text
        assert built_entry.msgstr == state.target_text, (
            "Checked-in tree and generated PO are out of sync.\n"
            f"File: {translation_path}\n"
            f"UUID: {uuid}\n"
            f"Field: {field}\n"
            f"Tree target: {state.target_text!r}\n"
            f"PO msgstr: {built_entry.msgstr!r}\n"
            "Run `make sync`, `make sync-watch`, or `make tree-to-po`."
        )

    report = workflow.validate_po_against_model(
        str(collaboration_final_po_path),
        str(model_path),
    )
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0

    review = workflow.review_po_changes(
        original_po_path=str(po_path),
        generated_po_path=str(collaboration_final_po_path),
    )
    assert review.msgstr_only, (
        "Generated collaboration PO changed more than msgstr blocks.\n"
        f"Changed msgid blocks: {review.changed_msgid_blocks}\n"
        f"Changed reference blocks: {review.changed_reference_blocks}\n"
        f"Changed fuzzy blocks: {review.changed_fuzzy_blocks}\n"
        f"Inserted blocks: {review.inserted_blocks}\n"
        f"Deleted blocks: {review.deleted_blocks}"
    )


def test_collaboration_generated_diff_matches_current_po_review(
    workflow,
    po_path,
    collaboration_final_po_path,
    collaboration_diff_path,
) -> None:
    """Verify that the checked-in diff matches the current generated PO review.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        collaboration_final_po_path: Checked-in generated PO path.
        collaboration_diff_path: Checked-in generated diff path.
    """

    assert collaboration_final_po_path.exists(), (
        "Missing generated collaboration PO file: "
        f"{collaboration_final_po_path}"
    )
    assert collaboration_diff_path.exists(), (
        "Missing generated collaboration diff file: "
        f"{collaboration_diff_path}\n"
        "Run `make sync` or `make review-po` before running translation tests."
    )

    review = workflow.review_po_changes(
        original_po_path=str(po_path),
        generated_po_path=str(collaboration_final_po_path),
    )
    recorded_diff = collaboration_diff_path.read_text(encoding="utf-8")

    assert recorded_diff == review.diff_text, (
        "Checked-in diff file does not match the current PO review output.\n"
        f"Diff file: {collaboration_diff_path}\n"
        f"Generated PO: {collaboration_final_po_path}\n"
        "Run `make sync` or `make review-po` to refresh the diff."
    )


def test_collaboration_outline_matches_current_tree_progress(
    workflow,
    collaboration_tree_dir,
    collaboration_outline_path,
) -> None:
    """Verify that the checked-in outline matches the current tree state.

    Args:
        workflow: Workflow service fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        collaboration_outline_path: Checked-in outline markdown path.
    """

    assert collaboration_outline_path.exists(), (
        "Missing collaboration outline markdown file: "
        f"{collaboration_outline_path}\n"
        "Run `make sync` before running translation tests."
    )

    generated_outline_path = collaboration_outline_path.with_name(
        ".outline.test.generated.md"
    )
    try:
        result = build_outline_markdown(
            workflow=workflow,
            tree_dir=collaboration_tree_dir,
            output_outline_path=generated_outline_path,
        )
        recorded_outline = collaboration_outline_path.read_text(encoding="utf-8")

        assert recorded_outline == result.markdown_text, (
            "Checked-in outline markdown does not match the current tree state.\n"
            f"Outline file: {collaboration_outline_path}\n"
            f"Generated file: {generated_outline_path}\n"
            "Run `make sync` to refresh the outline."
        )
        assert "- [x] [layer 1] 0001 Common DSW Knowledge Model" in recorded_outline
        assert "[KM] [uuid](" in recorded_outline
        assert "[Q] [translation](" in recorded_outline
    finally:
        generated_outline_path.unlink(missing_ok=True)


def _po_block_skeleton(block) -> tuple[tuple[str, ...], str, bool]:
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


def test_collaboration_generated_po_preserves_translation_block_count(
    po_path,
    collaboration_final_po_path,
) -> None:
    """Verify that generated collaboration PO keeps the original block count.

    This protects shared PO blocks from being silently split into extra
    translation strings in the checked-in collaboration output.

    Args:
        po_path: Fixture PO file path.
        collaboration_final_po_path: Checked-in generated PO path.
    """

    assert collaboration_final_po_path.exists(), (
        "Missing generated collaboration PO file: "
        f"{collaboration_final_po_path}\n"
        "Run `make sync` or `make tree-to-po` before running translation tests."
    )

    source_blocks = parse_po_blocks(po_path)
    generated_blocks = parse_po_blocks(collaboration_final_po_path)

    assert len(generated_blocks) == len(source_blocks), (
        "Generated collaboration PO does not preserve the original translation "
        "string count.\n"
        f"Source PO blocks: {len(source_blocks)}\n"
        f"Generated PO blocks: {len(generated_blocks)}\n"
        "This usually means a shared PO block was split unexpectedly.\n"
        "Run `make sync` and check whether conflicting translations were "
        "introduced into nodes that originally shared one PO block."
    )
    assert [
        _po_block_skeleton(block) for block in generated_blocks
    ] == [
        _po_block_skeleton(block) for block in source_blocks
    ], (
        "Generated collaboration PO changed non-translation content.\n"
        "Only `msgstr` values are allowed to differ from the source PO.\n"
        "Check for changed references, `msgid`, fuzzy flags, block order, or "
        "unexpected shared-block splitting."
    )


def test_collaboration_tree_validation_catches_missing_translation_markdown(
    workflow,
    collaboration_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when `translation.md` is deleted.

    Args:
        workflow: Workflow service fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(collaboration_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    entity_uuid, node = next(
        (entity_uuid, node)
        for entity_uuid, node in manifest["nodes"].items()
        if node.get("fields")
    )
    translation_path = tree_copy / node["path"] / "translation.md"
    translation_path.unlink()

    with pytest.raises(AssertionError, match="Missing translation markdown"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_collaboration_tree_validation_catches_missing_node_folder(
    workflow,
    collaboration_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when a node folder is deleted.

    Args:
        workflow: Workflow service fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(collaboration_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node)
        for entity_uuid, node in manifest["nodes"].items()
        if node.get("fields")
    )
    shutil.rmtree(tree_copy / node["path"])

    with pytest.raises(AssertionError, match="Tree folder UUID set does not match manifest"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_collaboration_tree_validation_catches_text_outside_fence(
    workflow,
    collaboration_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails on text appended outside fences.

    Args:
        workflow: Workflow service fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(collaboration_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node)
        for entity_uuid, node in manifest["nodes"].items()
        if node.get("fields")
    )
    corrupt_translation_by_appending_outside_fence(
        tree_copy / node["path"] / "translation.md"
    )

    with pytest.raises(ValueError, match="Unexpected content outside a fenced translation block"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_collaboration_tree_validation_catches_broken_fence(
    workflow,
    collaboration_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when a closing fence is broken.

    Args:
        workflow: Workflow service fixture.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(collaboration_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node)
        for entity_uuid, node in manifest["nodes"].items()
        if node.get("fields")
    )
    corrupt_translation_by_breaking_final_fence(
        tree_copy / node["path"] / "translation.md"
    )

    with pytest.raises(ValueError, match="Broken fence detected|Unclosed fence"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )
