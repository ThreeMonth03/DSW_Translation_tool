#!/usr/bin/env python3
import argparse
import json
import os

from tree_utils import (
    annotate_tree_nodes,
    build_ancestor_set,
    build_tree,
    export_translation_tree,
    load_json_model,
    parse_po_file,
    read_existing_manifest,
    scan_translation_tree,
    validate_po_entries,
)


def confirm_force_overwrite(out_dir, target_lang):
    if not os.path.isdir(out_dir):
        return True

    manifest = read_existing_manifest(out_dir)
    node_dirs, translations, _ = scan_translation_tree(out_dir, target_lang=target_lang)
    if not manifest and not node_dirs:
        return True

    non_empty_translations = sum(1 for value in translations.values() if value.strip())
    print("WARNING: --force will discard the current translation tree content in the target directory.")
    print(f"Target directory: {out_dir}")
    print(f"Existing node folders: {len(node_dirs)}")
    print(f"Existing non-empty translated fields: {non_empty_translations}")
    answer = input("Type 'yes' to overwrite this tree, or anything else to cancel: ").strip()
    if answer != "yes":
        print("Cancelled. Existing translation tree was kept.")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Export a DSW PO/JSON model as a translation folder tree and validate PO msgid values.",
    )
    parser.add_argument("--po", default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po")
    parser.add_argument("--json", default="files/dsw_root_2.7.0.json")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Write the generated translation folder tree to this directory.",
    )
    parser.add_argument(
        "--tree-out",
        default=None,
        help="Optionally write the generated tree metadata to this JSON file.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Write validation report to this JSON file.",
    )
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target tree from the supplied PO instead of preserving existing translations.",
    )
    args = parser.parse_args()

    po_entries = parse_po_file(args.po)
    latest_by_uuid, model_info = load_json_model(args.json)

    po_uuids = {entry["uuid"] for entry in po_entries}
    relevant_uuids = build_ancestor_set(latest_by_uuid, po_uuids)
    tree_roots, nodes_map = build_tree(latest_by_uuid, relevant_uuids)
    annotate_tree_nodes(tree_roots, po_entries, nodes_map)
    report = validate_po_entries(po_entries, latest_by_uuid)

    if args.out_dir:
        if args.force and not confirm_force_overwrite(args.out_dir, args.target_lang):
            raise SystemExit(1)
        manifest = export_translation_tree(
            args.out_dir,
            tree_roots,
            latest_by_uuid,
            model_info["name"],
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            preserve_existing_translations=not args.force,
        )
        print(
            f"Wrote translation tree to {args.out_dir} "
            f"({len(manifest['nodes'])} folders, {len(manifest['rootPaths'])} root folders)"
        )

    if args.tree_out:
        with open(args.tree_out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "model": model_info,
                    "roots": tree_roots,
                    "report": report,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Wrote tree output to {args.tree_out}")

    if args.report_out:
        with open(args.report_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"Wrote validation report to {args.report_out}")
    else:
        print(
            "Validation summary: "
            f"totalComments={report['totalComments']}, "
            f"missingEntities={report['missingEntities']}, "
            f"missingFields={report['missingFields']}, "
            f"mismatches={report['mismatches']}"
        )


if __name__ == "__main__":
    main()
