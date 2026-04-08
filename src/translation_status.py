#!/usr/bin/env python3
"""Report untranslated fields from an exported translation tree."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from dsw_translation_tool import TranslationWorkflowService


def build_pending_items(folders) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for folder in folders:
        for field in folder.untranslated_fields:
            items.append(
                {
                    "path": folder.path,
                    "uuid": folder.uuid,
                    "field": field,
                }
            )
    return items


def print_pending_item(index: int, item: dict[str, str]) -> None:
    print(f"{index:02d}. {item['field']}")
    print(f"    Folder : {item['path']}")
    print(f"    UUID   : {item['uuid']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report untranslated fields for an exported translation folder tree.",
    )
    parser.add_argument("--tree-dir", default="output/tree")
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    parser.add_argument(
        "-k",
        "--limit",
        type=int,
        default=5,
        help="Show the first k untranslated fields in DFS folder order. Use 0 to show all.",
    )
    parser.add_argument("--json-out", default=None, help="Optional path to write the full report as JSON.")
    args = parser.parse_args()

    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    status = workflow.collect_status(args.tree_dir)
    summary = status["summary"]
    pending_folders = [folder for folder in status["folders"] if folder.untranslated_fields]
    pending_items = build_pending_items(pending_folders)

    print("Untranslated Summary")
    print(f"  Pending folders : {summary['pendingFolders']}")
    print(f"  Untranslated    : {summary['untranslatedFields']} field(s)")
    print(f"  Completed       : {summary['completeFolders']} folder(s)")
    print()

    items_to_show = pending_items[: args.limit] if args.limit else pending_items
    print(f"First {len(items_to_show)} Untranslated Field(s)")
    print()
    for index, item in enumerate(items_to_show, start=1):
        print_pending_item(index, item)

    if args.limit and len(pending_items) > args.limit:
        print(f"... and {len(pending_items) - args.limit} more untranslated field(s)")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "summary": summary,
                    "pendingFolders": [asdict(folder) for folder in pending_folders],
                    "pendingItems": pending_items,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"JSON report written to {args.json_out}")


if __name__ == "__main__":
    main()
