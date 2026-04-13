#!/usr/bin/env python3
"""Review differences between an original and generated PO file."""

from __future__ import annotations

import argparse

from dsw_translation_tool import (
    DEFAULT_LAYOUT,
    DEFAULT_PO_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    TranslationWorkflowService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured argument parser for this command.
    """

    parser = argparse.ArgumentParser(
        description="Review semantic and textual differences between two PO files.",
    )
    parser.add_argument(
        "--original-po",
        default=str(DEFAULT_PO_PATH),
        help="Path to the original PO file used as the review baseline.",
    )
    parser.add_argument(
        "--generated-po",
        default=str(DEFAULT_LAYOUT.final_po_path),
        help="Path to the generated PO file being reviewed.",
    )
    parser.add_argument(
        "--diff-out",
        default=str(DEFAULT_LAYOUT.diff_path),
        help="Path to write the unified diff output.",
    )
    parser.add_argument("--source-lang", default=DEFAULT_SOURCE_LANG)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument(
        "--fail-on-non-msgstr",
        action="store_true",
        help="Exit with a non-zero code if changes are not limited to msgstr blocks.",
    )
    return parser


def main() -> None:
    """Run the PO review CLI."""

    args = build_argument_parser().parse_args()
    workflow = TranslationWorkflowService(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    review = workflow.review_po_changes(
        original_po_path=args.original_po,
        generated_po_path=args.generated_po,
        diff_out_path=args.diff_out,
    )

    print("PO Review")
    print(f"  Original PO           : {args.original_po}")
    print(f"  Generated PO          : {args.generated_po}")
    print(f"  Diff output           : {args.diff_out}")
    print(f"  Total blocks          : {review.total_blocks}")
    print(f"  Changed blocks        : {review.changed_blocks}")
    print(f"  Changed msgstr blocks : {review.changed_msgstr_blocks}")
    print(f"  Changed msgid blocks  : {review.changed_msgid_blocks}")
    print(f"  Changed refs          : {review.changed_reference_blocks}")
    print(f"  Changed fuzzy flags   : {review.changed_fuzzy_blocks}")
    print(f"  Inserted blocks       : {review.inserted_blocks}")
    print(f"  Deleted blocks        : {review.deleted_blocks}")
    print(f"  Msgstr only           : {review.msgstr_only}")

    if args.fail_on_non_msgstr and not review.msgstr_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
