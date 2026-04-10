"""Helper functions shared by the pytest suite."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from dsw_translation_tool import TranslationWorkflowService
from dsw_translation_tool.constants import (
    MANIFEST_NAME,
    TRANSLATION_FILENAME,
    TREE_BACKUP_DIRNAME,
    UUID_FILENAME,
)
from dsw_translation_tool.models import (
    PoBlock,
    PoEntry,
    SharedStringSyncResult,
    TranslationFieldState,
    TreeFolderSnapshot,
    TreeScanResult,
    WorkflowContext,
)
from dsw_translation_tool.po import PoCatalogParser


def build_entry_map(entries: list[PoEntry]) -> dict[tuple[str, str], PoEntry]:
    """Build a unique `(uuid, field)` lookup from flattened PO entries.

    Args:
        entries: Flattened PO entries.

    Returns:
        A map keyed by `(uuid, field)`.

    Raises:
        AssertionError: If duplicate keys are present.
    """

    entry_map: dict[tuple[str, str], PoEntry] = {}
    for entry in entries:
        key = (entry.uuid, entry.field)
        assert key not in entry_map, f"Duplicate PO key detected: {key}"
        entry_map[key] = entry
    return entry_map


def build_expected_fields_by_uuid(
    entries: list[PoEntry],
) -> dict[str, set[str]]:
    """Group expected field names by UUID.

    Args:
        entries: Flattened PO entries.

    Returns:
        Mapping from UUID to expected field-name set.
    """

    expected_fields: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        expected_fields[entry.uuid].add(entry.field)
    return expected_fields


def read_tree_manifest(tree_dir: Path) -> dict[str, object]:
    """Read the collaboration tree manifest from disk.

    Args:
        tree_dir: Translation tree root directory.

    Returns:
        Parsed manifest dictionary.

    Raises:
        AssertionError: If the manifest file is missing.
    """

    manifest_path = tree_dir / MANIFEST_NAME
    assert manifest_path.exists(), f"Missing tree manifest: {manifest_path}"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def inspect_translation_tree_disk_state(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
) -> tuple[dict[str, object], dict[tuple[str, str], TranslationFieldState]]:
    """Inspect the checked-in tree without auto-healing missing files.

    This helper intentionally reads the on-disk tree directly instead of using
    repository `scan()` so that accidental deletions, malformed fences, or
    unsynchronized edits are surfaced by the test suite.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory to inspect.

    Returns:
        Parsed manifest and flattened translation field states.
    """

    assert tree_dir.is_dir(), f"Missing collaboration tree directory: {tree_dir}"
    manifest = read_tree_manifest(tree_dir)
    expected_nodes = manifest.get("nodes", {})
    assert isinstance(expected_nodes, dict), "Tree manifest nodes must be a dictionary"

    actual_uuid_dirs: dict[str, str] = {}
    for uuid_path in sorted(tree_dir.rglob(UUID_FILENAME)):
        entity_uuid = uuid_path.read_text(encoding="utf-8").strip()
        relative_folder = str(uuid_path.parent.relative_to(tree_dir))
        assert entity_uuid not in actual_uuid_dirs, (
            "Duplicate UUID folder detected for "
            f"{entity_uuid}: {actual_uuid_dirs[entity_uuid]} and {relative_folder}"
        )
        actual_uuid_dirs[entity_uuid] = relative_folder

    assert set(actual_uuid_dirs) == set(expected_nodes), (
        "Tree folder UUID set does not match manifest.\n"
        f"Missing: {sorted(set(expected_nodes) - set(actual_uuid_dirs))[:20]}\n"
        f"Unexpected: {sorted(set(actual_uuid_dirs) - set(expected_nodes))[:20]}"
    )

    field_states: dict[tuple[str, str], TranslationFieldState] = {}
    document = workflow.tree_repository.document
    for entity_uuid, node in sorted(expected_nodes.items()):
        assert isinstance(node, dict), f"Manifest node for {entity_uuid} must be a dictionary"
        relative_path = node["path"]
        folder_path = tree_dir / relative_path
        assert folder_path.is_dir(), f"Missing node folder: {folder_path}"

        uuid_path = folder_path / UUID_FILENAME
        assert uuid_path.exists(), f"Missing UUID file: {uuid_path}"
        assert uuid_path.read_text(encoding="utf-8").strip() == entity_uuid

        expected_fields = tuple(node.get("fields", ()))
        translation_path = folder_path / TRANSLATION_FILENAME
        if not expected_fields:
            assert not translation_path.exists(), (
                "Non-translatable node unexpectedly has translation markdown: "
                f"{translation_path}"
            )
            continue

        assert translation_path.exists(), f"Missing translation markdown: {translation_path}"
        parsed_fields = document.parse(str(translation_path))
        assert set(parsed_fields) == set(expected_fields), (
            f"Field set mismatch in {translation_path}: "
            f"expected {sorted(expected_fields)}, got {sorted(parsed_fields)}"
        )

        for field_name, state in parsed_fields.items():
            key = (entity_uuid, field_name)
            assert key not in field_states, f"Duplicate tree field detected: {key}"
            field_states[key] = state

    return manifest, field_states


def expected_backup_path_for_uuid(tree_dir: Path, entity_uuid: str) -> Path:
    """Return the expected central backup path for one tree UUID.

    Args:
        tree_dir: Translation tree root directory.
        entity_uuid: UUID represented by the translation markdown.

    Returns:
        Expected central backup path.
    """

    return tree_dir.parent / TREE_BACKUP_DIRNAME / tree_dir.name / (
        f"{entity_uuid}.{TRANSLATION_FILENAME}.bak"
    )


def find_markdown_fence_collisions(entries: list[PoEntry]) -> list[str]:
    """Detect strings that would break the `translation.md` fence parser.

    Args:
        entries: Flattened PO entries.

    Returns:
        Collision descriptions for any line starting with `~~~`.
    """

    collisions: list[str] = []
    for entry in entries:
        for role, value in (("msgid", entry.msgid), ("msgstr", entry.msgstr)):
            for line in value.split("\n"):
                if line.strip().startswith("~~~"):
                    collisions.append(
                        f"{entry.uuid}:{entry.field}:{role}:{line.strip()}"
                    )
                    break
    return collisions


def export_tree_for_test(
    workflow: TranslationWorkflowService,
    po_path: Path,
    model_path: Path,
    tree_dir: Path,
) -> WorkflowContext:
    """Export a fresh translation tree for a test case.

    Args:
        workflow: Workflow service under test.
        po_path: Source PO file path.
        model_path: KM file path.
        tree_dir: Output tree directory.

    Returns:
        Export workflow context.
    """

    return workflow.export_tree(
        po_path=str(po_path),
        model_path=str(model_path),
        out_dir=str(tree_dir),
        preserve_existing_translations=False,
    )


def validate_tree(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
    entries: list[PoEntry],
) -> TreeScanResult:
    """Validate an exported tree and return the scan result.

    Args:
        workflow: Workflow service under test.
        tree_dir: Exported tree directory.
        entries: Expected flattened PO entries.

    Returns:
        Tree scan result from repository validation.
    """

    validation = workflow.tree_repository.validate(str(tree_dir), entries)
    assert validation.errors == ()
    return validation.scan_result


def select_multi_reference_block(
    blocks: list[PoBlock],
    scan_result: TreeScanResult,
) -> tuple[PoBlock, list[tuple[str, str]]]:
    """Select a shared PO block that is fully accessible in the tree.

    Args:
        blocks: Parsed PO blocks.
        scan_result: Current tree scan result.

    Returns:
        The selected block and available `(uuid, field)` keys.

    Raises:
        AssertionError: If no suitable block exists.
    """

    for block in blocks:
        if len(block.references) < 2:
            continue
        available_keys = [
            (reference.uuid, reference.field)
            for reference in block.references
            if reference.uuid in scan_result.folders_by_uuid
            and reference.field in scan_result.folders_by_uuid[reference.uuid].fields
        ]
        if len(available_keys) >= 2:
            return block, available_keys
    raise AssertionError("No shared PO block with at least two tree-backed fields was found")


def update_tree_field(
    workflow: TranslationWorkflowService,
    scan_result: TreeScanResult,
    uuid: str,
    field: str,
    target_text: str,
    modified_at: float | None = None,
) -> None:
    """Update one tree field and persist it back to disk.

    Args:
        workflow: Workflow service under test.
        scan_result: Current tree scan result.
        uuid: Target UUID.
        field: Target field name.
        target_text: New translated text.
        modified_at: Optional mtime override for deterministic sync tests.
    """

    snapshot = scan_result.folders_by_uuid[uuid]
    current_state = snapshot.fields[field]
    snapshot.fields[field] = TranslationFieldState(
        source_text=current_state.source_text,
        target_text=target_text,
    )
    workflow.tree_repository.write_snapshot(snapshot)
    if modified_at is not None and snapshot.translation_path is not None:
        os.utime(snapshot.translation_path, (modified_at, modified_at))


def rebuild_po_from_tree(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
    original_po_path: Path,
    output_po_path: Path,
) -> Path:
    """Rebuild a PO file from a tree and return the output path.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.
        original_po_path: Original PO template path.
        output_po_path: Destination PO path.

    Returns:
        Output PO path.
    """

    result = workflow.build_po_from_tree(
        tree_dir=str(tree_dir),
        original_po_path=str(original_po_path),
        out_po_path=str(output_po_path),
    )
    assert result.validation.errors == ()
    return output_po_path


def parse_po_entries(po_path: Path) -> list[PoEntry]:
    """Parse flattened entries from a PO file.

    Args:
        po_path: PO file path.

    Returns:
        Flattened PO entries.
    """

    return PoCatalogParser(str(po_path)).parse_entries()


def parse_po_blocks(po_path: Path) -> list[PoBlock]:
    """Parse grouped blocks from a PO file.

    Args:
        po_path: PO file path.

    Returns:
        Parsed PO blocks.
    """

    return PoCatalogParser(str(po_path)).parse_blocks()


def run_shared_string_sync(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
    original_po_path: Path,
    output_po_path: Path,
) -> SharedStringSyncResult:
    """Run shared-string synchronization for a tree.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.
        original_po_path: Original PO template path.
        output_po_path: Destination PO path.

    Returns:
        Shared-string sync result.
    """

    return workflow.sync_shared_strings(
        tree_dir=str(tree_dir),
        original_po_path=str(original_po_path),
        out_po_path=str(output_po_path),
        group_by="shared-block",
    )


def future_timestamp(offset_seconds: float = 1.0) -> float:
    """Return a deterministic future timestamp for mtime ordering.

    Args:
        offset_seconds: Offset from the current time.

    Returns:
        Future timestamp.
    """

    return time.time() + offset_seconds


def run_cli_script(repo_root: Path, script_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one CLI script under the current Python interpreter.

    Args:
        repo_root: Repository root directory used as the process cwd.
        script_path: Repository-relative path to the Python CLI script.
        *args: Additional CLI arguments.

    Returns:
        Completed process result with captured stdout and stderr.
    """

    return subprocess.run(
        [sys.executable, script_path, *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def find_first_translatable_snapshot(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
) -> TreeFolderSnapshot:
    """Return the first tree snapshot that contains translatable fields.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.

    Returns:
        First snapshot that has at least one translation field.

    Raises:
        AssertionError: If no translatable snapshot exists.
    """

    scan_result = workflow.tree_repository.scan(str(tree_dir))
    for snapshot in scan_result.folders_by_uuid.values():
        if snapshot.fields and snapshot.translation_path is not None:
            return snapshot
    raise AssertionError("No translatable tree snapshot was found")


def corrupt_translation_by_appending_outside_fence(translation_path: Path) -> str:
    """Append translator text outside fences to simulate an invalid edit.

    Args:
        translation_path: Translation markdown file to corrupt.

    Returns:
        Original unmodified file content.
    """

    original_text = translation_path.read_text(encoding="utf-8")
    corrupted_text = original_text + "\n這段文字被寫在 fence 外面\n"
    translation_path.write_text(corrupted_text, encoding="utf-8")
    return original_text


def corrupt_translation_by_breaking_final_fence(translation_path: Path) -> str:
    """Break the final fence in a translation markdown file.

    Args:
        translation_path: Translation markdown file to corrupt.

    Returns:
        Original unmodified file content.

    Raises:
        AssertionError: If no closing fence was found to corrupt.
    """

    original_text = translation_path.read_text(encoding="utf-8")
    lines = original_text.split("\n")
    for index in range(len(lines) - 1, -1, -1):
        if lines[index] == "~~~":
            lines[index] = "~~~~"
            translation_path.write_text("\n".join(lines), encoding="utf-8")
            return original_text
    raise AssertionError("No closing fence was found to corrupt")


def build_stress_translation(
    uuid: str,
    field: str,
    source_text: str,
    ordinal: int,
) -> str:
    """Build a deterministic stress-test translation string.

    Args:
        uuid: Node UUID for the translated field.
        field: Field name being translated.
        source_text: Source-language text currently stored in the tree.
        ordinal: Stable ordinal number used to keep translations unique.

    Returns:
        A multiline translation string containing characters that must be
        escaped correctly in PO output.
    """

    first_line = next(
        (line.strip() for line in source_text.splitlines() if line.strip()),
        "",
    )
    preview = first_line[:24]
    return (
        f"[STRESS {ordinal:04d}] {uuid[:8]}:{field}\n"
        f'preview="{preview}"\n'
        "symbols=quote:\" backslash:\\ tab:\t marker:end"
    )


def populate_tree_with_stress_translations(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
) -> dict[tuple[str, str], str]:
    """Populate every translatable tree field with a stress-test translation.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.

    Returns:
        Mapping from `(uuid, field)` to the generated stress-test translation.
    """

    scan_result = workflow.tree_repository.scan(str(tree_dir))
    expected_translations: dict[tuple[str, str], str] = {}
    ordinal = 0

    for uuid, snapshot in scan_result.folders_by_uuid.items():
        if not snapshot.fields:
            continue
        for field, state in snapshot.fields.items():
            ordinal += 1
            translation = build_stress_translation(
                uuid=uuid,
                field=field,
                source_text=state.source_text,
                ordinal=ordinal,
            )
            snapshot.fields[field] = TranslationFieldState(
                source_text=state.source_text,
                target_text=translation,
            )
            expected_translations[(uuid, field)] = translation
        workflow.tree_repository.write_snapshot(snapshot)

    return expected_translations


def build_block_stress_translation(block: PoBlock, ordinal: int) -> str:
    """Build one deterministic stress translation for a whole PO block.

    Args:
        block: PO block receiving a generated translation.
        ordinal: Stable ordinal number used to keep translations unique.

    Returns:
        A multiline translation string shared by all references in the block.
    """

    first_line = next(
        (line.strip() for line in block.msgid.splitlines() if line.strip()),
        "",
    )
    preview = first_line[:24]
    return (
        f"[BLOCK {ordinal:04d}] refs={len(block.references)}\n"
        f'preview="{preview}"\n'
        "symbols=quote:\" backslash:\\ tab:\t marker:end"
    )


def build_empty_msgstr_translation_map(
    blocks: list[PoBlock],
) -> dict[tuple[str, str], str]:
    """Build translations only for PO blocks whose original `msgstr` is empty.

    Args:
        blocks: Parsed PO blocks from the original PO file.

    Returns:
        Mapping from `(uuid, field)` to generated translations for originally
        untranslated entries only.
    """

    return build_block_translation_map(
        blocks=blocks,
        include_originally_empty=True,
        multi_reference_only=False,
    )


def build_non_empty_msgstr_translation_map(
    blocks: list[PoBlock],
    multi_reference_only: bool = False,
) -> dict[tuple[str, str], str]:
    """Build translations for PO blocks whose original `msgstr` is non-empty.

    Args:
        blocks: Parsed PO blocks from the original PO file.
        multi_reference_only: Whether to target only shared blocks.

    Returns:
        Mapping from `(uuid, field)` to generated translations for originally
        translated entries.
    """

    return build_block_translation_map(
        blocks=blocks,
        include_originally_empty=False,
        multi_reference_only=multi_reference_only,
    )


def build_block_translation_map(
    blocks: list[PoBlock],
    include_originally_empty: bool,
    multi_reference_only: bool,
) -> dict[tuple[str, str], str]:
    """Build a deterministic translation map for a selected block subset.

    Args:
        blocks: Parsed PO blocks from the original PO file.
        include_originally_empty: Whether to target empty `msgstr` blocks.
        multi_reference_only: Whether to target only shared blocks.

    Returns:
        Mapping from `(uuid, field)` to generated translations for the selected
        blocks.
    """

    translations: dict[tuple[str, str], str] = {}
    ordinal = 0
    for block in blocks:
        if multi_reference_only and len(block.references) < 2:
            continue
        if include_originally_empty and block.msgstr != "":
            continue
        if not include_originally_empty and block.msgstr == "":
            continue
        ordinal += 1
        translation = build_block_stress_translation(block, ordinal)
        for reference in block.references:
            translations[(reference.uuid, reference.field)] = translation
    return translations


def apply_translation_map_to_tree(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
    translations_by_key: dict[tuple[str, str], str],
) -> None:
    """Apply a translation map directly to the tree.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.
        translations_by_key: Mapping from `(uuid, field)` to translated text.
    """

    scan_result = workflow.tree_repository.scan(str(tree_dir))
    snapshots_to_write: set[str] = set()

    for (uuid, field), target_text in translations_by_key.items():
        snapshot = scan_result.folders_by_uuid[uuid]
        current_state = snapshot.fields[field]
        snapshot.fields[field] = TranslationFieldState(
            source_text=current_state.source_text,
            target_text=target_text,
        )
        snapshots_to_write.add(uuid)

    for uuid in snapshots_to_write:
        workflow.tree_repository.write_snapshot(scan_result.folders_by_uuid[uuid])


def apply_sync_seed_translations_to_tree(
    workflow: TranslationWorkflowService,
    tree_dir: Path,
    blocks: list[PoBlock],
    translations_by_key: dict[tuple[str, str], str],
) -> None:
    """Seed the tree for sync tests while preserving shared-block propagation.

    For targeted multi-reference blocks, only the first reference is populated
    and the remaining references are left blank so that `sync` must propagate
    the shared translation. Untargeted blocks are left unchanged.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.
        blocks: Parsed PO blocks from the original PO file.
        translations_by_key: Mapping from `(uuid, field)` to translated text.
    """

    scan_result = workflow.tree_repository.scan(str(tree_dir))
    snapshots_to_write: set[str] = set()

    for block in blocks:
        block_keys = [(reference.uuid, reference.field) for reference in block.references]
        if not any(key in translations_by_key for key in block_keys):
            continue

        references = list(block.references)
        first_reference = references[0]
        first_key = (first_reference.uuid, first_reference.field)
        translation = translations_by_key[first_key]

        first_snapshot = scan_result.folders_by_uuid[first_reference.uuid]
        first_state = first_snapshot.fields[first_reference.field]
        first_snapshot.fields[first_reference.field] = TranslationFieldState(
            source_text=first_state.source_text,
            target_text=translation,
        )
        snapshots_to_write.add(first_reference.uuid)

        for reference in references[1:]:
            sibling_snapshot = scan_result.folders_by_uuid[reference.uuid]
            sibling_state = sibling_snapshot.fields[reference.field]
            sibling_snapshot.fields[reference.field] = TranslationFieldState(
                source_text=sibling_state.source_text,
                target_text="",
            )
            snapshots_to_write.add(reference.uuid)

    for uuid in snapshots_to_write:
        workflow.tree_repository.write_snapshot(scan_result.folders_by_uuid[uuid])


def assert_only_empty_msgstr_blocks_changed(
    original_po_path: Path,
    generated_po_path: Path,
    translations_by_key: dict[tuple[str, str], str],
) -> None:
    """Assert that generated PO differs from the original only in empty msgstrs.

    Args:
        original_po_path: Original PO template path.
        generated_po_path: Generated PO file path.
        translations_by_key: Expected translations for originally empty blocks.
    """

    assert_only_expected_msgstr_blocks_changed(
        original_po_path=original_po_path,
        generated_po_path=generated_po_path,
        translations_by_key=translations_by_key,
    )


def assert_only_expected_msgstr_blocks_changed(
    original_po_path: Path,
    generated_po_path: Path,
    translations_by_key: dict[tuple[str, str], str],
) -> None:
    """Assert that only expected `msgstr` blocks changed between two PO files.

    Args:
        original_po_path: Original PO template path.
        generated_po_path: Generated PO file path.
        translations_by_key: Expected per-reference translations for changed
            blocks only.
    """

    original_blocks = parse_po_blocks(original_po_path)
    generated_blocks = parse_po_blocks(generated_po_path)

    assert len(generated_blocks) == len(original_blocks)
    for original_block, generated_block in zip(
        original_blocks,
        generated_blocks,
        strict=True,
    ):
        original_refs = tuple(reference.comment for reference in original_block.references)
        generated_refs = tuple(reference.comment for reference in generated_block.references)
        assert generated_refs == original_refs
        assert generated_block.msgid == original_block.msgid
        assert generated_block.is_fuzzy == original_block.is_fuzzy

        expected_values = {
            translations_by_key[(reference.uuid, reference.field)]
            for reference in original_block.references
            if (reference.uuid, reference.field) in translations_by_key
        }
        if not expected_values:
            assert generated_block.msgstr == original_block.msgstr
            continue

        assert len(expected_values) == 1
        assert generated_block.msgstr == next(iter(expected_values))
