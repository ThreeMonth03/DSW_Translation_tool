#!/usr/bin/env python3
"""Optional full round-trip workflow for final smoke testing."""

from __future__ import annotations

import argparse

from dsw_translation_tool import TranslationWorkflowService


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description="PO translation workflow using a folder tree.",
    )
    parser.add_argument(
        "--po",
        default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po",
    )
    parser.add_argument("--json", default="files/dsw_root_2.7.0.km")
    parser.add_argument("--tree-dir", default="translation/zh_Hant/tree")
    parser.add_argument(
        "--final-po",
        default="translation/zh_Hant/builds/final_translated.po",
    )
    parser.add_argument(
        "--report-out",
        default="translation/zh_Hant/reports/final_report.json",
    )
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    return parser


def main() -> None:
    """Run the optional end-to-end workflow CLI."""

    args = build_argument_parser().parse_args()
    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )

    print("Step 1: Exporting translation folder tree...")
    export_result = workflow.export_tree(
        po_path=args.po,
        model_path=args.json,
        out_dir=args.tree_dir,
        preserve_existing_translations=True,
    )
    manifest = export_result.manifest or {"nodes": {}}
    print(
        f"Exported {len(manifest['nodes'])} folders to {args.tree_dir}. "
        "Edit each folder's translation.md target-language blocks, then press Enter to continue."
    )
    input()

    print("Step 2: Importing the translation folder tree back into PO...")
    build_result = workflow.build_po_from_tree(
        tree_dir=args.tree_dir,
        original_po_path=args.po,
        out_po_path=args.final_po,
    )
    print(f"Wrote PO file to {build_result.output_po}")

    print("Step 3: Validating the generated PO file...")
    report = workflow.validate_po_against_model(args.final_po, args.json)
    workflow.write_report(report, args.report_out)
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
