"""Helper functions shared by the pytest suite."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path

from dsw_translation_tool import SharedStringSynchronizer, TranslationWorkflowService
from dsw_translation_tool.models import PoBlock, PoEntry, TranslationFieldState, TreeScanResult
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
):
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
):
    """Run shared-string synchronization for a tree.

    Args:
        workflow: Workflow service under test.
        tree_dir: Translation tree directory.
        original_po_path: Original PO template path.
        output_po_path: Destination PO path.

    Returns:
        Shared-string sync result.
    """

    synchronizer = SharedStringSynchronizer(workflow.tree_repository)
    return synchronizer.sync(
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
