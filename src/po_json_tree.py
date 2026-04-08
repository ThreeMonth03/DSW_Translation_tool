#!/usr/bin/env python3
"""Export a DSW PO/model pair into a translation tree and validate PO msgids."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dsw_translation_tool import TranslationWorkflowService


def confirm_force_overwrite(out_dir: str, target_lang: str) -> bool:
    tree_repository = TranslationWorkflowService(target_lang=target_lang).tree_repository
    output_dir = Path(out_dir)
    if not output_dir.is_dir():
        return True

    manifest = tree_repository.read_existing_manifest(out_dir)
    scan_result = tree_repository.scan(out_dir)
    if not manifest and not scan_result["nodeDirs"]:
        return True

    non_empty_translations = sum(
        1 for value in scan_result["translations"].values() if value.strip()
    )
    print("WARNING: --force will discard the current translation tree content in the target directory.")
    print(f"Target directory: {out_dir}")
    print(f"Existing node folders: {len(scan_result['nodeDirs'])}")
    print(f"Existing non-empty translated fields: {non_empty_translations}")
    answer = input("Type 'yes' to overwrite this tree, or anything else to cancel: ").strip()
    if answer != "yes":
        print("Cancelled. Existing translation tree was kept.")
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a DSW PO/model file as a translation folder tree and validate PO msgid values.",
    )
    parser.add_argument("--po", default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po")
    parser.add_argument("--json", default="files/dsw_root_2.7.0.km", help="Path to a .km or .json model file.")
    parser.add_argument("--out-dir", default=None, help="Write the generated translation folder tree here.")
    parser.add_argument("--tree-out", default=None, help="Optionally write the generated tree metadata to JSON.")
    parser.add_argument("--report-out", default=None, help="Write validation report to this JSON file.")
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target tree from the supplied PO instead of preserving existing translations.",
    )
    args = parser.parse_args()

    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )

    if args.out_dir:
        if args.force and not confirm_force_overwrite(args.out_dir, args.target_lang):
            raise SystemExit(1)
        context = workflow.export_tree(
            po_path=args.po,
            model_path=args.json,
            out_dir=args.out_dir,
            preserve_existing_translations=not args.force,
        )
        print(
            f"Wrote translation tree to {args.out_dir} "
            f"({len(context['manifest']['nodes'])} folders, {len(context['manifest']['rootPaths'])} root folders)"
        )
    else:
        context = workflow.build_tree_context(po_path=args.po, model_path=args.json)

    if args.tree_out:
        Path(args.tree_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.tree_out).write_text(
            json.dumps(
                {
                    "model": context["model"],
                    "roots": [asdict(root) for root in context["roots"]],
                    "report": context["report"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote tree output to {args.tree_out}")

    if args.report_out:
        workflow.write_report(context["report"], args.report_out)
        print(f"Wrote validation report to {args.report_out}")
    else:
        report = context["report"]
        print(
            "Validation summary: "
            f"totalComments={report['totalComments']}, "
            f"missingEntities={report['missingEntities']}, "
            f"missingFields={report['missingFields']}, "
            f"mismatches={report['mismatches']}"
        )


if __name__ == "__main__":
    main()
