#!/usr/bin/env python3
"""Export a DSW PO/model pair into a translation tree and validate PO msgids."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dsw_translation_tool import (
    DEFAULT_MODEL_PATH,
    DEFAULT_PO_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    TranslationWorkflowService,
)


def confirm_force_overwrite(out_dir: str, target_lang: str) -> bool:
    """Ask the user for confirmation before destroying an existing tree.

    Args:
        out_dir: Output tree directory.
        target_lang: Target language code for the tree.

    Returns:
        `True` when overwrite is confirmed, otherwise `False`.
    """

    tree_repository = TranslationWorkflowService(
        target_lang=target_lang,
    ).tree_repository
    output_dir = Path(out_dir)
    if not output_dir.is_dir():
        return True

    manifest = tree_repository.read_existing_manifest(out_dir)
    scan_result = tree_repository.scan(out_dir)
    if not manifest and not scan_result.node_dirs:
        return True

    non_empty_translations = sum(1 for value in scan_result.translations.values() if value.strip())
    print(
        "WARNING: --force will discard the current translation tree content "
        "in the target directory."
    )
    print(f"Target directory: {out_dir}")
    print(f"Existing node folders: {len(scan_result.node_dirs)}")
    print(f"Existing non-empty translated fields: {non_empty_translations}")
    answer = input("Type 'yes' to overwrite this tree, or anything else to cancel: ").strip()
    if answer != "yes":
        print("Cancelled. Existing translation tree was kept.")
        return False
    return True


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured argument parser for this command.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Export a DSW PO/model file as a translation folder tree and validate PO msgid values."
        ),
    )
    parser.add_argument(
        "--po",
        default=str(DEFAULT_PO_PATH),
    )
    parser.add_argument(
        "--json",
        default=str(DEFAULT_MODEL_PATH),
        help="Path to a .km or .json model file.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Write the generated translation folder tree here.",
    )
    parser.add_argument(
        "--tree-out",
        default=None,
        help="Optionally write the generated tree metadata to JSON.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Write validation report to this JSON file.",
    )
    parser.add_argument(
        "--outline-out",
        default=None,
        help=(
            "Write a tree outline markdown file. Defaults to "
            "<out-dir>/outline.md when --out-dir is set."
        ),
    )
    parser.add_argument(
        "--shared-blocks-dir-out",
        default=None,
        help=(
            "Write the canonical split shared-block directory. Defaults to "
            "<out-dir>/shared_blocks when --out-dir is set."
        ),
    )
    parser.add_argument("--source-lang", default=DEFAULT_SOURCE_LANG)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite the target tree from the supplied PO instead of "
            "preserving existing translations."
        ),
    )
    return parser


def main() -> None:
    """Run the export-and-validate CLI."""

    args = build_argument_parser().parse_args()
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
        manifest = context.manifest or {"nodes": {}, "rootPaths": []}
        print(
            f"Wrote translation tree to {args.out_dir} "
            f"({len(manifest['nodes'])} folders, "
            f"{len(manifest['rootPaths'])} root folders)"
        )
        outline_out = args.outline_out or str(Path(args.out_dir) / "outline.md")
        outline_result = workflow.build_outline_markdown(
            tree_dir=args.out_dir,
            out_outline_path=outline_out,
        )
        print(f"Wrote outline markdown to {outline_result.output_outline}")
        shared_blocks_dir_out = args.shared_blocks_dir_out or str(
            Path(args.out_dir) / "shared_blocks"
        )
        shared_blocks_result = workflow.build_shared_blocks_directory(
            tree_dir=args.out_dir,
            original_po_path=args.po,
            out_shared_blocks_root=shared_blocks_dir_out,
        )
        print(
            "Wrote shared-block directory to "
            f"{shared_blocks_result.output_shared_blocks_root}"
        )
        stale_shared_blocks_index = Path(args.out_dir) / "shared_blocks.md"
        stale_shared_blocks_outline = Path(args.out_dir) / "shared_blocks_outline.md"
        stale_shared_blocks_index.unlink(missing_ok=True)
        stale_shared_blocks_outline.unlink(missing_ok=True)
    else:
        context = workflow.build_tree_context(po_path=args.po, model_path=args.json)

    if args.tree_out:
        Path(args.tree_out).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": context.model_metadata,
            "roots": [asdict(root) for root in context.roots],
            "report": context.report,
        }
        Path(args.tree_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote tree output to {args.tree_out}")

    if args.report_out:
        workflow.write_report(context.report, args.report_out)
        print(f"Wrote validation report to {args.report_out}")
        return

    report = context.report
    print(
        "Validation summary: "
        f"totalComments={report['totalComments']}, "
        f"missingEntities={report['missingEntities']}, "
        f"missingFields={report['missingFields']}, "
        f"mismatches={report['mismatches']}"
    )


if __name__ == "__main__":
    main()
