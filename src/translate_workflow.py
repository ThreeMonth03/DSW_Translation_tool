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
    rewrite_po_translations,
    validate_po_entries,
    validate_translation_tree,
)


def main():
    parser = argparse.ArgumentParser(description="PO translation workflow using a folder tree.")
    parser.add_argument("--po", default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po")
    parser.add_argument("--json", default="files/dsw_root_2.7.0.json")
    parser.add_argument("--tree-dir", default="output/tree")
    parser.add_argument("--final-po", default="output/final_translated.po")
    parser.add_argument("--report-out", default="output/final_report.json")
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    args = parser.parse_args()

    po_entries = parse_po_file(args.po)
    latest_by_uuid, model_info = load_json_model(args.json)
    relevant_uuids = build_ancestor_set(latest_by_uuid, {entry["uuid"] for entry in po_entries})
    tree_roots, nodes_map = build_tree(latest_by_uuid, relevant_uuids)
    annotate_tree_nodes(tree_roots, po_entries, nodes_map)

    print("Step 1: Exporting translation folder tree...")
    manifest = export_translation_tree(
        args.tree_dir,
        tree_roots,
        latest_by_uuid,
        model_info["name"],
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    print(
        f"Exported {len(manifest['nodes'])} folders to {args.tree_dir}. "
        "Edit each folder's translation.md target-language blocks, then press Enter to continue."
    )
    input()

    print("Step 2: Importing the translation folder tree back into PO...")
    tree_validation = validate_translation_tree(args.tree_dir, po_entries, target_lang=args.target_lang)
    if tree_validation["errors"]:
        preview = "\n".join(tree_validation["errors"][:50])
        raise ValueError(f"Translation tree validation failed:\n{preview}")

    po_content = rewrite_po_translations(args.po, tree_validation["translations"])
    final_po_dir = os.path.dirname(args.final_po)
    if final_po_dir:
        os.makedirs(final_po_dir, exist_ok=True)
    with open(args.final_po, "w", encoding="utf-8") as handle:
        handle.write(po_content)
    print(f"Wrote PO file to {args.final_po}")

    print("Step 3: Validating the generated PO file...")
    final_entries = parse_po_file(args.final_po)
    report = validate_po_entries(final_entries, latest_by_uuid)
    report_dir = os.path.dirname(args.report_out)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
    with open(args.report_out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"Wrote validation report to {args.report_out}")
    print(
        "Workflow complete: "
        f"totalComments={report['totalComments']}, "
        f"missingEntities={report['missingEntities']}, "
        f"missingFields={report['missingFields']}, "
        f"mismatches={report['mismatches']}"
    )


if __name__ == "__main__":
    main()
