#!/usr/bin/env python3
"""Synchronize shared strings across the translation tree."""

from __future__ import annotations

import argparse
import time
from argparse import Namespace
from pathlib import Path

from dsw_translation_tool import (
    DEFAULT_LAYOUT,
    DEFAULT_PO_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    TranslationWorkflowService,
)
from dsw_translation_tool.sync_support import SyncWatchService, SyncWatchSettings

DEFAULT_OUT_PO = str(DEFAULT_LAYOUT.final_po_path)
DEFAULT_DIFF_OUT = str(DEFAULT_LAYOUT.diff_path)
DEFAULT_OUTLINE_OUT = str(DEFAULT_LAYOUT.outline_path)
DEFAULT_SHARED_BLOCKS_OUT = str(DEFAULT_LAYOUT.shared_blocks_path)
DEFAULT_SHARED_BLOCKS_OUTLINE_OUT = str(DEFAULT_LAYOUT.shared_blocks_outline_path)


def build_watch_service(args: Namespace) -> SyncWatchService:
    """Build the watch-mode service for one CLI invocation.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Configured watch service.
    """

    return SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path(args.tree_dir),
            watch_shared_blocks=args.group_by == "shared-block",
        ),
        run_cycle=lambda: run_sync(args),
        time_module=time,
    )


def run_sync(args: Namespace) -> set[Path]:
    """Run one shared-string synchronization pass.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Set of filesystem paths written during the sync cycle.
    """

    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    result = workflow.sync_shared_strings(
        tree_dir=args.tree_dir,
        original_po_path=args.original_po,
        out_po_path=args.out_po,
        outline_out_path=resolve_outline_out_path(args),
        shared_blocks_out_path=resolve_shared_blocks_out_path(args),
        shared_blocks_outline_out_path=resolve_shared_blocks_outline_out_path(args),
        group_by=args.group_by,
    )
    diff_out = resolve_diff_out_path(args)
    review = None
    if result.output_po and diff_out:
        review = workflow.review_po_changes(
            original_po_path=args.original_po,
            generated_po_path=result.output_po,
            diff_out_path=diff_out,
        )

    written_paths = {Path(path).resolve() for path in result.written_tree_paths}
    print("Shared String Sync")
    print(f"  Group mode     : {args.group_by}")
    print(f"  Groups scanned : {result.groups_scanned}")
    print(f"  Groups updated : {result.groups_updated}")
    print(f"  Fields updated : {result.fields_updated}")
    print(f"  Conflicts      : {len(result.conflicts)}")
    if result.output_po:
        print(f"  Output PO      : {result.output_po}")
        written_paths.add(Path(result.output_po).resolve())
    if result.output_outline:
        print(f"  Output outline : {result.output_outline}")
        written_paths.add(Path(result.output_outline).resolve())
    if result.output_shared_blocks:
        print(f"  Output shared  : {result.output_shared_blocks}")
        written_paths.add(Path(result.output_shared_blocks).resolve())
    if result.output_shared_blocks_outline:
        print(f"  Output shared-outline : {result.output_shared_blocks_outline}")
        written_paths.add(Path(result.output_shared_blocks_outline).resolve())
    if review is not None:
        print(f"  Output diff    : {diff_out}")
        print(f"  Msgstr only    : {review.msgstr_only}")
        if diff_out:
            written_paths.add(Path(diff_out).resolve())

    if not result.conflicts:
        return written_paths

    print()
    print("First 5 Conflict Group(s)")
    print()
    for index, conflict in enumerate(result.conflicts[:5], start=1):
        preview = ", ".join(repr(value) for value in conflict.translations[:3])
        if len(conflict.translations) > 3:
            preview += ", ..."
        print(f"{index:02d}. {conflict.msgid}")
        print(f"    References   : {len(conflict.references)}")
        print(f"    Translations : {preview}")
        print()

    return written_paths


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Sync repeated/shared source strings across a translation tree "
            "and optionally rebuild PO."
        ),
    )
    parser.add_argument("--tree-dir", default=str(DEFAULT_LAYOUT.tree_dir))
    parser.add_argument(
        "--original-po",
        default=str(DEFAULT_PO_PATH),
        help="Original PO file used as the grouping/template source.",
    )
    parser.add_argument(
        "--out-po",
        default=DEFAULT_OUT_PO,
        help="Optional output PO path to refresh after sync.",
    )
    parser.add_argument(
        "--diff-out",
        default=None,
        help="Optional unified diff output path for reviewing PO changes.",
    )
    parser.add_argument(
        "--outline-out",
        default=None,
        help="Optional markdown outline output path for tree progress review.",
    )
    parser.add_argument(
        "--shared-blocks-out",
        default=None,
        help=(
            "Optional shared-block markdown path used as input/output for "
            "canonical shared translations."
        ),
    )
    parser.add_argument(
        "--shared-blocks-outline-out",
        default=None,
        help="Optional compact shared-block overview markdown output path.",
    )
    parser.add_argument("--source-lang", default=DEFAULT_SOURCE_LANG)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument(
        "--group-by",
        choices=("shared-block", "msgid", "msgid-field"),
        default="shared-block",
        help="How to decide which tree fields should stay synchronized.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep syncing on filesystem changes until interrupted.",
    )
    return parser


def resolve_diff_out_path(args: Namespace) -> str | None:
    """Resolve the diff output path for one sync run.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Diff output path or `None` when no review file should be written.
    """

    if args.diff_out:
        return args.diff_out
    if args.out_po == DEFAULT_OUT_PO:
        return DEFAULT_DIFF_OUT
    output_po = Path(args.out_po)
    return str(output_po.with_suffix(".diff"))


def resolve_outline_out_path(args: Namespace) -> str | None:
    """Resolve the outline markdown output path for one sync run.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Outline markdown output path or `None`.
    """

    if args.outline_out:
        return args.outline_out
    if Path(args.tree_dir) == DEFAULT_LAYOUT.tree_dir:
        return DEFAULT_OUTLINE_OUT
    return str(Path(args.tree_dir) / "outline.md")


def resolve_shared_blocks_out_path(args: Namespace) -> str | None:
    """Resolve the shared-block markdown path for one sync run.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Shared-block markdown path or `None`.
    """

    if args.shared_blocks_out:
        return args.shared_blocks_out
    if Path(args.tree_dir) == DEFAULT_LAYOUT.tree_dir:
        return DEFAULT_SHARED_BLOCKS_OUT
    return str(Path(args.tree_dir) / "shared_blocks.md")


def resolve_shared_blocks_outline_out_path(args: Namespace) -> str | None:
    """Resolve the shared-block outline markdown path for one sync run.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Shared-block outline markdown path or `None`.
    """

    if args.shared_blocks_outline_out:
        return args.shared_blocks_outline_out
    if Path(args.tree_dir) == DEFAULT_LAYOUT.tree_dir:
        return DEFAULT_SHARED_BLOCKS_OUTLINE_OUT
    return str(Path(args.tree_dir) / "shared_blocks_outline.md")


def main() -> None:
    """Run the shared-string synchronization CLI."""

    args = build_argument_parser().parse_args()
    try:
        if not args.watch:
            try:
                run_sync(args)
            except ValueError as error:
                raise SystemExit(str(error)) from error
            return
        try:
            build_watch_service(args).run()
        except ValueError as error:
            raise SystemExit(str(error)) from error
    except KeyboardInterrupt:
        print("Stopped shared-string watch mode.")


if __name__ == "__main__":
    main()
