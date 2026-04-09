"""Tests that validate checked-in collaboration output state."""

from __future__ import annotations

import shutil

import pytest

from tests.helpers import (
    build_entry_map,
    corrupt_translation_by_appending_outside_fence,
    corrupt_translation_by_breaking_final_fence,
    expected_backup_path_for_uuid,
    inspect_translation_tree_disk_state,
    parse_po_entries,
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


def test_collaboration_tree_has_complete_and_current_backups(
    collaboration_tree_dir,
) -> None:
    """Verify that every checked-in translation markdown has a matching backup.

    The checked-in backup set should stay in lockstep with `translation/tree` so PRs
    do not merge a collaboration tree that cannot be restored safely.

    Args:
        collaboration_tree_dir: Checked-in collaboration tree directory.
    """

    manifest = read_tree_manifest(collaboration_tree_dir)
    expected_backup_paths: dict[str, str] = {}

    for entity_uuid, node in manifest["nodes"].items():
        if not node.get("fields"):
            continue
        translation_path = collaboration_tree_dir / node["path"] / "translation.md"
        backup_path = expected_backup_path_for_uuid(
            collaboration_tree_dir,
            entity_uuid,
        )
        expected_backup_paths[entity_uuid] = str(backup_path.relative_to(
            collaboration_tree_dir.parent.parent
        ))

        assert backup_path.exists(), (
            "Missing checked-in translation backup.\n"
            f"File: {translation_path}\n"
            f"Expected backup: {backup_path}"
        )
        assert backup_path.read_text(encoding="utf-8") == translation_path.read_text(
            encoding="utf-8"
        ), (
            "Checked-in backup is stale and no longer matches translation.md.\n"
            f"File: {translation_path}\n"
            f"Backup: {backup_path}\n"
            "Run `make sync`, `make tree-to-po`, or another write path that "
            "refreshes backups before opening the PR."
        )

    backup_root = collaboration_tree_dir.parent / "backups" / collaboration_tree_dir.name
    assert backup_root.is_dir(), f"Missing collaboration backup directory: {backup_root}"

    actual_backup_uuids = {
        backup_path.name.removesuffix(".translation.md.bak")
        for backup_path in backup_root.glob("*.translation.md.bak")
    }
    expected_backup_uuids = set(expected_backup_paths)
    assert actual_backup_uuids == expected_backup_uuids, (
        "Checked-in backup set does not match translatable tree nodes.\n"
        f"Missing backups: {sorted(expected_backup_uuids - actual_backup_uuids)[:20]}\n"
        f"Unexpected backups: {sorted(actual_backup_uuids - expected_backup_uuids)[:20]}"
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
