"""CLI integration tests for translation entrypoints."""

from __future__ import annotations

import shutil
from argparse import Namespace

import sync_shared_strings
from tests.helpers import (
    apply_sync_seed_translations_to_tree,
    apply_translation_map_to_tree,
    assert_only_empty_msgstr_blocks_changed,
    assert_only_expected_msgstr_blocks_changed,
    build_empty_msgstr_translation_map,
    build_entry_map,
    build_non_empty_msgstr_translation_map,
    corrupt_translation_by_appending_outside_fence,
    corrupt_translation_by_breaking_final_fence,
    expected_backup_path_for_uuid,
    export_tree_for_test,
    find_first_translatable_snapshot,
    parse_po_entries,
    populate_tree_with_stress_translations,
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


def test_sync_cli_seeds_local_backups_for_tree_without_tracked_backup_files(
    repo_root,
    workflow,
    po_path,
    collaboration_tree_dir,
    workspace,
) -> None:
    """Verify that sync recreates local backups from a clean collaboration tree.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        collaboration_tree_dir: Checked-in collaboration tree directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "seeded-backups.po"
    diff_path = workspace / "seeded-backups.diff"
    shutil.copytree(collaboration_tree_dir, tree_dir)

    backup_root = tree_dir.parent / "backups" / tree_dir.name
    shutil.rmtree(backup_root, ignore_errors=True)

    manifest = workflow.tree_repository.read_existing_manifest(str(tree_dir))
    assert manifest is not None
    entity_uuid, node = next(
        (entity_uuid, node)
        for entity_uuid, node in manifest["nodes"].items()
        if node.get("fields")
    )
    translation_path = tree_dir / node["path"] / "translation.md"
    backup_path = expected_backup_path_for_uuid(tree_dir, entity_uuid)
    assert backup_path.exists() is False

    result = run_cli_script(
        repo_root,
        "src/sync_shared_strings.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(output_po),
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == translation_path.read_text(
        encoding="utf-8"
    )


def test_tree_to_po_cli_preserves_unicode_line_separator_in_msgstr(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_entries,
    workspace,
) -> None:
    """Verify that tree-to-PO CLI preserves Unicode line separators in msgstr.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-tree-to-po-unicode.po"

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

    target_uuid, snapshot = next(
        (uuid, snapshot)
        for uuid, snapshot in scan_result.folders_by_uuid.items()
        if snapshot.fields
    )
    target_field = next(iter(snapshot.fields))
    special_translation = f"Alpha\u2028Beta::{target_uuid[:8]}:{target_field}"
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=target_uuid,
        field=target_field,
        target_text=special_translation,
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
    rebuilt_entries = build_entry_map(parse_po_entries(output_po))
    assert rebuilt_entries[(target_uuid, target_field)].msgstr == special_translation


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
    diff_path = workspace / "cli-sync.diff"
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
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Shared String Sync" in result.stdout
    assert "Conflicts      : 0" in result.stdout
    assert f"Output diff    : {diff_path}" in result.stdout
    assert output_po.exists()
    assert diff_path.exists()
    assert "@@" in diff_path.read_text(encoding="utf-8")

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


def test_sync_shared_strings_cli_preserves_unicode_line_separator_when_syncing(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that sync CLI preserves Unicode line separators across a group.

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
    output_po = workspace / "cli-sync-unicode.po"
    diff_path = workspace / "cli-sync-unicode.diff"
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
    special_translation = f"Alpha\u2028Beta::{chosen_uuid[:8]}:{chosen_field}"
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
        target_text=special_translation,
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
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert diff_path.exists()
    synced_scan = workflow.tree_repository.scan(str(tree_dir))
    rebuilt_entries = build_entry_map(parse_po_entries(output_po))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == special_translation
        assert rebuilt_entries[(uuid, field)].msgstr == special_translation


def test_tree_to_po_cli_overwrites_targeted_non_empty_msgstr_blocks(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Verify that tree-to-PO CLI can overwrite selected existing translations.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-tree-to-po-overwrite.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    translations_by_key = build_non_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        translations_by_key=translations_by_key,
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
    assert output_po.exists()
    assert_only_expected_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=output_po,
        translations_by_key=translations_by_key,
    )


def test_sync_shared_strings_cli_overwrites_targeted_non_empty_shared_blocks(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Verify that sync CLI can overwrite and resync shared translated blocks.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-sync-overwrite.po"
    diff_path = workspace / "cli-sync-overwrite.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    translations_by_key = build_non_empty_msgstr_translation_map(
        po_blocks,
        multi_reference_only=True,
    )
    apply_sync_seed_translations_to_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        blocks=po_blocks,
        translations_by_key=translations_by_key,
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
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Shared String Sync" in result.stdout
    assert output_po.exists()
    assert diff_path.exists()
    assert_only_expected_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=output_po,
        translations_by_key=translations_by_key,
    )

    report = workflow.validate_po_against_model(str(output_po), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0


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

    tree_dir = workspace / "tree"
    generated_po = workspace / "review-source.po"
    diff_path = workspace / "review.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        translations_by_key=translations_by_key,
    )
    build_result = run_cli_script(
        repo_root,
        "src/tree_to_po.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(generated_po),
    )
    assert build_result.returncode == 0, build_result.stderr or build_result.stdout

    review_result = run_cli_script(
        repo_root,
        "src/review_po_changes.py",
        "--original-po",
        str(po_path),
        "--generated-po",
        str(generated_po),
        "--diff-out",
        str(diff_path),
        "--fail-on-non-msgstr",
    )

    assert review_result.returncode == 0, review_result.stderr or review_result.stdout
    assert "PO Review" in review_result.stdout
    assert "Msgstr only           : True" in review_result.stdout
    assert diff_path.exists()
    assert "@@" in diff_path.read_text(encoding="utf-8")


def test_tree_to_po_cli_handles_fully_translated_tree_stress_case(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_entries,
    workspace,
) -> None:
    """Verify that tree-to-PO CLI handles a fully translated stress fixture.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-tree-to-po-stress.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    expected_translations = populate_tree_with_stress_translations(
        workflow=workflow,
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

    rebuilt_entries = build_entry_map(parse_po_entries(output_po))
    assert len(rebuilt_entries) == len(po_entries)
    assert set(rebuilt_entries.keys()) == set(expected_translations.keys())

    for key, expected_translation in expected_translations.items():
        assert rebuilt_entries[key].msgstr == expected_translation

    raw_po = output_po.read_text(encoding="utf-8")
    assert '\\"' in raw_po
    assert "\\\\" in raw_po
    assert "\\n" in raw_po
    assert "\\t" in raw_po

    report = workflow.validate_po_against_model(str(output_po), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0


def test_tree_to_po_cli_changes_only_originally_empty_msgstr_blocks(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Verify that tree-to-PO CLI preserves structure when filling empty msgstrs.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-tree-to-po-empty-only.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        translations_by_key=translations_by_key,
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
    assert output_po.exists()
    assert_only_empty_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=output_po,
        translations_by_key=translations_by_key,
    )


def test_sync_shared_strings_cli_changes_only_originally_empty_msgstr_blocks(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    workspace,
) -> None:
    """Verify that sync CLI preserves structure while syncing empty msgstrs.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        workspace: Per-test temporary workspace fixture.
    """

    tree_dir = workspace / "tree"
    output_po = workspace / "cli-sync-empty-only.po"
    diff_path = workspace / "cli-sync-empty-only.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_sync_seed_translations_to_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        blocks=po_blocks,
        translations_by_key=translations_by_key,
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
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Shared String Sync" in result.stdout
    assert "Msgstr only    : True" in result.stdout
    assert output_po.exists()
    assert diff_path.exists()
    assert_only_empty_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=output_po,
        translations_by_key=translations_by_key,
    )

    report = workflow.validate_po_against_model(str(output_po), str(model_path))
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0


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

    tree_dir = workspace / "tree"
    output_po = workspace / "invalid-outside-fence.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_appending_outside_fence(
        snapshot.translation_path
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

    assert result.returncode != 0
    assert "restored from the last known-good backup" in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert output_po.exists() is False
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

    tree_dir = workspace / "tree"
    output_po = workspace / "invalid-broken-fence.po"
    diff_path = workspace / "invalid-broken-fence.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=tree_dir)
    assert snapshot.translation_path is not None
    original_text = corrupt_translation_by_breaking_final_fence(
        snapshot.translation_path
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
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode != 0
    assert "restored from the last known-good backup" in result.stderr
    assert str(snapshot.translation_path) in result.stderr
    assert output_po.exists() is False
    assert diff_path.exists() is False
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


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

    tree_dir = workspace / "tree"
    output_po = workspace / "restored-missing-translation.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=tree_dir)
    assert snapshot.translation_path is not None
    original_text = snapshot.translation_path.read_text(encoding="utf-8")
    snapshot.translation_path.unlink()

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
    assert output_po.read_bytes() == po_path.read_bytes()
    assert snapshot.translation_path.exists()
    assert snapshot.translation_path.read_text(encoding="utf-8") == original_text


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

    tree_dir = workspace / "tree"
    output_po = workspace / "restored-missing-uuid.po"
    diff_path = workspace / "restored-missing-uuid.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=tree_dir)
    assert snapshot.translation_path is not None
    uuid_path = snapshot.translation_path.parent / "_uuid.txt"
    uuid_path.unlink()

    result = run_cli_script(
        repo_root,
        "src/sync_shared_strings.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(output_po),
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert output_po.read_bytes() == po_path.read_bytes()
    assert uuid_path.exists()
    assert uuid_path.read_text(encoding="utf-8") == snapshot.entity_uuid
    assert diff_path.exists()
    assert diff_path.read_text(encoding="utf-8") == ""


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

    tree_dir = workspace / "tree"
    output_po = workspace / "restored-missing-folder.po"
    diff_path = workspace / "restored-missing-folder.diff"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    snapshot = find_first_translatable_snapshot(workflow=workflow, tree_dir=tree_dir)
    assert snapshot.translation_path is not None
    folder_path = snapshot.translation_path.parent
    original_text = snapshot.translation_path.read_text(encoding="utf-8")
    shutil.rmtree(folder_path)

    result = run_cli_script(
        repo_root,
        "src/sync_shared_strings.py",
        "--tree-dir",
        str(tree_dir),
        "--original-po",
        str(po_path),
        "--out-po",
        str(output_po),
        "--diff-out",
        str(diff_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert output_po.read_bytes() == po_path.read_bytes()
    assert folder_path.exists()
    assert (folder_path / "_uuid.txt").read_text(encoding="utf-8") == snapshot.entity_uuid
    assert (folder_path / "translation.md").read_text(encoding="utf-8") == original_text
    assert diff_path.exists()
    assert diff_path.read_text(encoding="utf-8") == ""


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
        source_lang="en",
        target_lang="zh_Hant",
        group_by="shared-block",
        watch=True,
        interval=0,
    )
    run_calls: list[int] = []

    class _Parser:
        def parse_args(self) -> Namespace:
            return args

    def fake_run_sync(_: Namespace) -> None:
        run_calls.append(1)
        if len(run_calls) == 1:
            raise ValueError("broken translation.md was restored")
        raise KeyboardInterrupt

    monkeypatch.setattr(sync_shared_strings, "build_argument_parser", lambda: _Parser())
    monkeypatch.setattr(sync_shared_strings, "run_sync", fake_run_sync)
    monkeypatch.setattr(sync_shared_strings.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        sync_shared_strings.time,
        "strftime",
        lambda _: "2026-04-09 18:00:00",
    )

    sync_shared_strings.main()

    captured = capsys.readouterr()
    assert run_calls == [1, 1]
    assert "[sync] Error: broken translation.md was restored" in captured.out
    assert "Stopped shared-string watch mode." in captured.out
