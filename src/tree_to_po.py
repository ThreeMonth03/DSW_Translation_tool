#!/usr/bin/env python3
"""Convert a translation tree back into a PO file."""

from __future__ import annotations

import argparse

from dsw_translation_tool import TranslationWorkflowService


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured argument parser for this command.
    """

    parser = argparse.ArgumentParser(
        description="Convert a translation folder tree back to PO format.",
    )
    parser.add_argument(
        "--tree-dir",
        default="output/tree",
        help="Path to the translation folder tree.",
    )
    parser.add_argument(
        "--original-po",
        default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po",
        help="Path to the original PO file used as the structural template.",
    )
    parser.add_argument(
        "--out-po",
        default="output/final_translated.po",
        help="Output PO file path.",
    )
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh_Hant")
    return parser


def main() -> None:
    """Run the tree-to-PO CLI."""

    args = build_argument_parser().parse_args()
    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    result = workflow.build_po_from_tree(
        tree_dir=args.tree_dir,
        original_po_path=args.original_po,
        out_po_path=args.out_po,
    )

    print(
        f"Generated PO file: {result.output_po} "
        f"({len(result.validation.scan_result.node_dirs)} folders scanned, "
        f"{len(result.validation.scan_result.translations)} translation files)"
    )


if __name__ == "__main__":
    main()
