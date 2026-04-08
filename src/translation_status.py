#!/usr/bin/env python3
import argparse
import json

from tree_utils import collect_translation_status


def build_pending_items(folders):
    items = []
    for folder in folders:
        for field in folder["untranslatedFields"]:
            items.append({
                "path": folder["path"],
                "uuid": folder["uuid"],
                "field": field,
            })
    return items


def print_pending_item(index, item):
    print(f"{index:02d}. {item['field']}")
    print(f"    Folder : {item['path']}")
    print(f"    UUID   : {item['uuid']}")
    print()


def main():
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
        help="Optional path to write the full untranslated report as JSON.",
    )
    args = parser.parse_args()

    status = collect_translation_status(
        args.tree_dir,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    summary = status["summary"]
    pending_folders = [folder for folder in status["folders"] if folder["untranslatedFields"]]
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
                    "pendingFolders": pending_folders,
                    "pendingItems": pending_items,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"JSON report written to {args.json_out}")


if __name__ == "__main__":
    main()
