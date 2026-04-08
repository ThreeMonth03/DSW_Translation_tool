#!/usr/bin/env python3
"""Synchronize shared strings across the translation tree."""

from __future__ import annotations

import argparse
import time

from dsw_translation_tool import SharedStringSynchronizer, TranslationTreeRepository


def run_sync(args) -> None:
    repository = TranslationTreeRepository(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    synchronizer = SharedStringSynchronizer(repository)
    result = synchronizer.sync(
        tree_dir=args.tree_dir,
        original_po_path=args.original_po,
        out_po_path=args.out_po,
        group_by=args.group_by,
    )

    print("Shared String Sync")
    print(f"  Group mode     : {args.group_by}")
    print(f"  Groups scanned : {result.groups_scanned}")
    print(f"  Groups updated : {result.groups_updated}")
    print(f"  Fields updated : {result.fields_updated}")
    print(f"  Conflicts      : {len(result.conflicts)}")
    if result.output_po:
        print(f"  Output PO      : {result.output_po}")

    if result.conflicts:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync repeated/shared source strings across a translation tree and optionally rebuild PO.",
    )
    parser.add_argument("--tree-dir", default="output/tree")
    parser.add_argument(
        "--original-po",
        default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po",
        help="Original PO file used as the grouping/template source.",
    )
    parser.add_argument(
        "--out-po",
        default="output/final_translated.po",
        help="Optional output PO path to refresh after sync.",
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
    args = parser.parse_args()

    if not args.watch:
        run_sync(args)
        return

    try:
        while True:
            print(f"[sync] Running at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            run_sync(args)
            print()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped shared-string watch mode.")


if __name__ == "__main__":
    main()
