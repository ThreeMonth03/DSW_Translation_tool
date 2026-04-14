"""CLI integration tests for shared-string synchronization behavior."""

from __future__ import annotations

import os
import shutil

from tests.helpers import (
    apply_sync_seed_translations_to_tree,
    apply_translation_map_to_tree,
    assert_only_empty_msgstr_blocks_changed,
    assert_only_expected_msgstr_blocks_changed,
    build_empty_msgstr_translation_map,
    build_entry_map,
    build_non_empty_msgstr_translation_map,
    build_shared_blocks_markdown,
    expected_backup_path_for_uuid,
    export_tree_for_test,
    future_timestamp,
    parse_po_blocks,
    parse_po_entries,
    read_translation_markdown_header,
    select_multi_reference_block,
    update_shared_block_translation,
    update_tree_field,
    validate_tree,
)
from tests.infra.support import (
    CliArtifactPaths,
    assert_clean_model_validation,
    assert_cli_success,
    po_block_skeleton,
    run_sync_cli,
)


def test_sync_cli_seeds_local_backups_for_tree_without_tracked_backup_files(
    repo_root,
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify that sync recreates local backups from a clean collaboration tree.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="seeded-backups.po",
        diff_name="seeded-backups.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )

    backup_root = artifacts.tree_dir.parent / "backups" / artifacts.tree_dir.name
    shutil.rmtree(backup_root, ignore_errors=True)

    manifest = workflow.tree_repository.read_existing_manifest(str(artifacts.tree_dir))
    assert manifest is not None
    entity_uuid, node = next(
        (entity_uuid, node) for entity_uuid, node in manifest["nodes"].items() if node.get("fields")
    )
    translation_path = artifacts.tree_dir / node["path"] / "translation.md"
    backup_path = expected_backup_path_for_uuid(artifacts.tree_dir, entity_uuid)
    assert backup_path.exists() is False

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == translation_path.read_text(encoding="utf-8")


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync.po",
        diff_name="cli-sync.diff",
        outline_name="outline.md",
        shared_blocks_name="shared_blocks.md",
        shared_blocks_outline_name="shared_blocks_outline.md",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        entries=po_entries,
    )
    _, available_keys = select_multi_reference_block(po_blocks, scan_result)
    header_metadata_before = {
        key: read_translation_markdown_header(scan_result.folders_by_uuid[key[0]].translation_path)
        for key in available_keys
    }

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

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
        outline_path=artifacts.outline_path,
        shared_blocks_path=artifacts.shared_blocks_path,
        shared_blocks_outline_path=artifacts.shared_blocks_outline_path,
    )

    assert_cli_success(result)
    assert "Shared String Sync" in result.stdout
    assert "Conflicts      : 0" in result.stdout
    assert artifacts.outline_path is not None
    assert artifacts.diff_path is not None
    assert f"Output outline : {artifacts.outline_path}" in result.stdout
    assert f"Output diff    : {artifacts.diff_path}" in result.stdout
    assert artifacts.output_po.exists()
    assert artifacts.diff_path.exists()
    assert artifacts.outline_path.exists()
    assert artifacts.shared_blocks_path is not None
    assert artifacts.shared_blocks_outline_path is not None
    assert artifacts.shared_blocks_path.exists()
    assert artifacts.shared_blocks_outline_path.exists()
    assert "@@" in artifacts.diff_path.read_text(encoding="utf-8")
    assert "# Shared Blocks Outline" in artifacts.shared_blocks_outline_path.read_text(
        encoding="utf-8"
    )

    synced_scan = workflow.tree_repository.scan(str(artifacts.tree_dir))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == custom_translation
        translation_path = synced_scan.folders_by_uuid[uuid].translation_path
        assert translation_path is not None
        assert (
            read_translation_markdown_header(translation_path)
            == header_metadata_before[(uuid, field)]
        )

    rebuilt_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    outline_text = artifacts.outline_path.read_text(encoding="utf-8")
    for uuid, field in available_keys:
        assert rebuilt_entries[(uuid, field)].msgstr == custom_translation
        translation_path = synced_scan.folders_by_uuid[uuid].translation_path
        assert translation_path is not None
        relative_link = os.path.relpath(translation_path, artifacts.outline_path.parent)
        assert uuid[:8] in outline_text
        assert f"](<{relative_link}>)" in outline_text

    assert_clean_model_validation(workflow, artifacts.output_po, model_path)


def test_sync_cli_uses_shared_blocks_markdown_as_canonical_source(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that shared-block markdown drives synchronization for shared fields.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-shared-blocks.po",
        diff_name="cli-sync-shared-blocks.diff",
        outline_name="outline.md",
        shared_blocks_name="shared_blocks.md",
        shared_blocks_outline_name="shared_blocks_outline.md",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    assert artifacts.shared_blocks_path is not None
    build_shared_blocks_markdown(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_shared_blocks_path=artifacts.shared_blocks_path,
    )
    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        entries=po_entries,
    )
    block, available_keys = select_multi_reference_block(po_blocks, scan_result)
    shared_group_key = tuple((reference.uuid, reference.field) for reference in block.references)
    canonical_translation = f"[SHARED_BLOCKS] {available_keys[0][0][:8]}:{available_keys[0][1]}"

    update_shared_block_translation(
        shared_blocks_path=artifacts.shared_blocks_path,
        group_key=shared_group_key,
        target_text=canonical_translation,
    )
    for uuid, field in available_keys:
        update_tree_field(
            workflow=workflow,
            scan_result=scan_result,
            uuid=uuid,
            field=field,
            target_text="",
        )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
        outline_path=artifacts.outline_path,
        shared_blocks_path=artifacts.shared_blocks_path,
        shared_blocks_outline_path=artifacts.shared_blocks_outline_path,
    )

    assert_cli_success(result)
    assert f"Output shared  : {artifacts.shared_blocks_path}" in result.stdout
    assert f"Output shared-outline : {artifacts.shared_blocks_outline_path}" in result.stdout

    synced_scan = workflow.tree_repository.scan(str(artifacts.tree_dir))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == canonical_translation

    synced_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    for uuid, field in available_keys:
        assert synced_entries[(uuid, field)].msgstr == canonical_translation

    regenerated_shared_blocks = artifacts.shared_blocks_path.read_text(encoding="utf-8")
    assert canonical_translation in regenerated_shared_blocks
    assert artifacts.shared_blocks_outline_path is not None
    shared_blocks_outline_text = artifacts.shared_blocks_outline_path.read_text(encoding="utf-8")
    assert "## Untranslated" not in shared_blocks_outline_text
    assert "## Translated" not in shared_blocks_outline_text
    assert "shared_blocks.md#translation-zh-hant-group-" in shared_blocks_outline_text
    assert "- [x] [Group " not in shared_blocks_outline_text
    assert "- [ ] [Group " not in shared_blocks_outline_text
    assert_clean_model_validation(workflow, artifacts.output_po, model_path)


def test_sync_shared_strings_cli_uses_latest_non_empty_field_edit(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that sync propagates the latest non-empty field edit in a group.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-latest-non-empty.po",
    )
    seed_po = workspace / "seed.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    seed_result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=seed_po,
        group_by="msgid",
    )
    assert_cli_success(seed_result)

    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        entries=po_entries,
    )
    _, available_keys = select_multi_reference_block(po_blocks, scan_result)
    first_key, second_key = available_keys[:2]

    older_translation = f"[OLDER] {first_key[0][:8]}:{first_key[1]}"
    newer_translation = f"[NEWER] {second_key[0][:8]}:{second_key[1]}"
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=first_key[0],
        field=first_key[1],
        target_text=older_translation,
        modified_at=future_timestamp(1.0),
    )
    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=second_key[0],
        field=second_key[1],
        target_text=newer_translation,
        modified_at=future_timestamp(2.0),
    )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        group_by="msgid",
    )

    assert_cli_success(result)
    synced_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    for uuid, field in available_keys:
        assert synced_entries[(uuid, field)].msgstr == newer_translation


def test_sync_shared_strings_cli_uses_latest_blank_field_edit(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that sync can propagate a latest blank field edit across a group.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-latest-blank.po",
    )
    seed_po = workspace / "seed.po"
    baseline_po = workspace / "baseline.po"

    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    seed_result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=seed_po,
        group_by="msgid",
    )
    assert_cli_success(seed_result)

    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        entries=po_entries,
    )
    _, available_keys = select_multi_reference_block(po_blocks, scan_result)
    first_key, second_key = available_keys[:2]
    baseline_translation = f"[BASELINE] {first_key[0][:8]}:{first_key[1]}"

    update_tree_field(
        workflow=workflow,
        scan_result=scan_result,
        uuid=first_key[0],
        field=first_key[1],
        target_text=baseline_translation,
        modified_at=future_timestamp(1.0),
    )
    baseline_result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=baseline_po,
        group_by="msgid",
    )
    assert_cli_success(baseline_result)

    refreshed_scan = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        entries=po_entries,
    )
    update_tree_field(
        workflow=workflow,
        scan_result=refreshed_scan,
        uuid=second_key[0],
        field=second_key[1],
        target_text="",
        modified_at=future_timestamp(2.0),
    )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        group_by="msgid",
    )

    assert_cli_success(result)
    synced_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    for uuid, field in available_keys:
        assert synced_entries[(uuid, field)].msgstr == ""


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-unicode.po",
        diff_name="cli-sync-unicode.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
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

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()
    synced_scan = workflow.tree_repository.scan(str(artifacts.tree_dir))
    rebuilt_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == special_translation
        assert rebuilt_entries[(uuid, field)].msgstr == special_translation


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-overwrite.po",
        diff_name="cli-sync-overwrite.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_non_empty_msgstr_translation_map(
        po_blocks,
        multi_reference_only=True,
    )
    apply_sync_seed_translations_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        blocks=po_blocks,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert "Shared String Sync" in result.stdout
    assert artifacts.output_po.exists()
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()
    assert_only_expected_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=artifacts.output_po,
        translations_by_key=translations_by_key,
    )

    assert_clean_model_validation(workflow, artifacts.output_po, model_path)


def test_sync_shared_strings_cli_handles_fully_translated_tree_stress_case(
    repo_root,
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify that sync CLI keeps a fully translated tree fully translated.

    Args:
        repo_root: Repository root fixture.
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        model_path: Fixture KM file path.
        po_blocks: Parsed PO blocks fixture.
        po_entries: Flattened PO entries fixture.
        workspace: Per-test temporary workspace fixture.
    """

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-full-tree.po",
        diff_name="cli-sync-full-tree.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(
        po_blocks
    ) | build_non_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert "Shared String Sync" in result.stdout
    assert artifacts.output_po.exists()
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()

    rebuilt_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    rebuilt_blocks = parse_po_blocks(artifacts.output_po)
    assert len(rebuilt_entries) == len(po_entries)
    assert set(rebuilt_entries.keys()) == set(translations_by_key.keys())
    assert all(entry.msgstr != "" for entry in rebuilt_entries.values())

    for key, expected_translation in translations_by_key.items():
        assert rebuilt_entries[key].msgstr == expected_translation
    assert [po_block_skeleton(block) for block in rebuilt_blocks] == [
        po_block_skeleton(block) for block in po_blocks
    ], (
        "Sync changed non-translation PO block structure during the fully "
        "translated stress case.\n"
        "Shared blocks should remain merged when every member ends up with the "
        "same translation."
    )

    assert_clean_model_validation(workflow, artifacts.output_po, model_path)


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-sync-empty-only.po",
        diff_name="cli-sync-empty-only.diff",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_sync_seed_translations_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        blocks=po_blocks,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    result = run_sync_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
        diff_path=artifacts.diff_path,
    )

    assert_cli_success(result)
    assert "Shared String Sync" in result.stdout
    assert "Msgstr only    : True" in result.stdout
    assert artifacts.output_po.exists()
    assert artifacts.diff_path is not None
    assert artifacts.diff_path.exists()
    assert_only_empty_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=artifacts.output_po,
        translations_by_key=translations_by_key,
    )

    assert_clean_model_validation(workflow, artifacts.output_po, model_path)
