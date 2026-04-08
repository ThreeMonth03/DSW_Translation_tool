#!/usr/bin/env python3
"""Report untranslated fields from an exported translation tree."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from dsw_translation_tool import TranslationWorkflowService
from dsw_translation_tool.models import TranslationStatusFolder, TranslationStatusReport


def build_pending_items(
    folders: list[TranslationStatusFolder],
) -> list[dict[str, str]]:
    """Flatten folder status into one item per untranslated field.

    Args:
        folders: Folder status records containing untranslated fields.

    Returns:
        A flat list of pending field items.
    """

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
    """Print one pending untranslated item."""

    print(f"{index:02d}. {item['field']}")
    print(f"    Folder : {item['path']}")
    print(f"    UUID   : {item['uuid']}")
    print()


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

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
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write the full report as JSON.",
    )
    return parser


def print_status_report(
    status: TranslationStatusReport,
    limit: int,
) -> list[dict[str, str]]:
    """Print the human-readable status report and return pending items."""

    summary = status.summary.to_dict()
    pending_folders = [
        folder for folder in status.folders if folder.untranslated_fields
    ]
    pending_items = build_pending_items(pending_folders)

    print("Untranslated Summary")
    print(f"  Pending folders : {summary['pendingFolders']}")
    print(f"  Untranslated    : {summary['untranslatedFields']} field(s)")
    print(f"  Completed       : {summary['completeFolders']} folder(s)")
    print()

    items_to_show = pending_items[:limit] if limit else pending_items
    print(f"First {len(items_to_show)} Untranslated Field(s)")
    print()
    for index, item in enumerate(items_to_show, start=1):
        print_pending_item(index, item)

    if limit and len(pending_items) > limit:
        print(f"... and {len(pending_items) - limit} more untranslated field(s)")

    return pending_items


def main() -> None:
    """Run the translation-status CLI."""

    args = build_argument_parser().parse_args()
    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    status = workflow.collect_status(args.tree_dir)
    pending_items = print_status_report(status=status, limit=args.limit)

    if args.json_out:
        pending_folders = [
            folder for folder in status.folders if folder.untranslated_fields
        ]
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "summary": status.summary.to_dict(),
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
