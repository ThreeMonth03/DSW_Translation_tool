"""CLI integration tests for tree-to-PO rebuild behavior."""

from __future__ import annotations

from tests.helpers import (
    apply_translation_map_to_tree,
    assert_only_empty_msgstr_blocks_changed,
    assert_only_expected_msgstr_blocks_changed,
    build_empty_msgstr_translation_map,
    build_entry_map,
    build_non_empty_msgstr_translation_map,
    export_tree_for_test,
    parse_po_entries,
    populate_tree_with_stress_translations,
    update_tree_field,
    validate_tree,
)
from tests.infra.support import (
    CliArtifactPaths,
    assert_clean_model_validation,
    assert_cli_success,
    run_tree_to_po_cli,
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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-tree-to-po.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    assert "Generated PO file:" in result.stdout
    assert artifacts.output_po.exists()
    assert artifacts.output_po.read_bytes() == po_path.read_bytes()

    rebuilt_entries = parse_po_entries(artifacts.output_po)
    assert len(rebuilt_entries) == len(po_entries)


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-tree-to-po-unicode.po",
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

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    rebuilt_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    assert rebuilt_entries[(target_uuid, target_field)].msgstr == special_translation


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-tree-to-po-overwrite.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_non_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    assert artifacts.output_po.exists()
    assert_only_expected_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=artifacts.output_po,
        translations_by_key=translations_by_key,
    )


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-tree-to-po-stress.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    expected_translations = populate_tree_with_stress_translations(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
    )

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    assert "Generated PO file:" in result.stdout
    assert artifacts.output_po.exists()

    rebuilt_entries = build_entry_map(parse_po_entries(artifacts.output_po))
    assert len(rebuilt_entries) == len(po_entries)
    assert set(rebuilt_entries.keys()) == set(expected_translations.keys())

    for key, expected_translation in expected_translations.items():
        assert rebuilt_entries[key].msgstr == expected_translation

    raw_po = artifacts.output_po.read_text(encoding="utf-8")
    assert '\\"' in raw_po
    assert "\\\\" in raw_po
    assert "\\n" in raw_po
    assert "\\t" in raw_po

    assert_clean_model_validation(workflow, artifacts.output_po, model_path)


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

    artifacts = CliArtifactPaths.from_workspace(
        workspace,
        output_po_name="cli-tree-to-po-empty-only.po",
    )
    export_tree_for_test(
        workflow=workflow,
        po_path=po_path,
        model_path=model_path,
        tree_dir=artifacts.tree_dir,
    )
    translations_by_key = build_empty_msgstr_translation_map(po_blocks)
    apply_translation_map_to_tree(
        workflow=workflow,
        tree_dir=artifacts.tree_dir,
        translations_by_key=translations_by_key,
    )

    assert artifacts.output_po is not None
    result = run_tree_to_po_cli(
        repo_root=repo_root,
        tree_dir=artifacts.tree_dir,
        original_po_path=po_path,
        output_po_path=artifacts.output_po,
    )

    assert_cli_success(result)
    assert artifacts.output_po.exists()
    assert_only_empty_msgstr_blocks_changed(
        original_po_path=po_path,
        generated_po_path=artifacts.output_po,
        translations_by_key=translations_by_key,
    )
