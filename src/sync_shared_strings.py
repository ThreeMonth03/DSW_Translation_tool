#!/usr/bin/env python3
"""Synchronize shared strings across the translation tree."""

from __future__ import annotations

import argparse
import time
from argparse import Namespace
from pathlib import Path

from dsw_translation_tool import TranslationWorkflowService

DEFAULT_OUT_PO = "translation/zh_Hant/builds/final_translated.po"
DEFAULT_DIFF_OUT = "translation/zh_Hant/reviews/final_translated.diff"
DEFAULT_OUTLINE_OUT = "translation/zh_Hant/tree/outline.md"


def run_sync(args: Namespace) -> None:
    """Run one shared-string synchronization pass.

    Args:
        args: Parsed CLI arguments.
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

    print("Shared String Sync")
    print(f"  Group mode     : {args.group_by}")
    print(f"  Groups scanned : {result.groups_scanned}")
    print(f"  Groups updated : {result.groups_updated}")
    print(f"  Fields updated : {result.fields_updated}")
    print(f"  Conflicts      : {len(result.conflicts)}")
    if result.output_po:
        print(f"  Output PO      : {result.output_po}")
    if result.output_outline:
        print(f"  Output outline : {result.output_outline}")
    if review is not None:
        print(f"  Output diff    : {diff_out}")
        print(f"  Msgstr only    : {review.msgstr_only}")

    if not result.conflicts:
        return

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


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Sync repeated/shared source strings across a translation tree "
            "and optionally rebuild PO."
        ),
    )
    parser.add_argument("--tree-dir", default="translation/zh_Hant/tree")
    parser.add_argument(
        "--original-po",
        default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po",
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
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    parser.add_argument(
        "--group-by",
        choices=("shared-block", "msgid", "msgid-field"),
        default="shared-block",
        help="How to decide which tree fields should stay synchronized.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep syncing on an interval until interrupted.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Watch interval in seconds. Used only with --watch.",
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
    if args.tree_dir == "translation/zh_Hant/tree":
        return DEFAULT_OUTLINE_OUT
    return str(Path(args.tree_dir) / "outline.md")


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
        while True:
            print(f"[sync] Running at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            try:
                run_sync(args)
            except ValueError as error:
                print(f"[sync] Error: {error}")
            print()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped shared-string watch mode.")


if __name__ == "__main__":
    main()
