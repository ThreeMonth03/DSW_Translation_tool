#!/usr/bin/env python3
import argparse
import os

from tree_utils import parse_po_file, rewrite_po_translations, validate_translation_tree


def main():
    parser = argparse.ArgumentParser(
        description="Convert a translation folder tree back to PO format.",
    )
    parser.add_argument("--tree-dir", default="output/tree", help="Path to the translation folder tree.")
    parser.add_argument(
        "--original-po",
        default="files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po",
        help="Path to the original PO file used as the structural template.",
    )
    parser.add_argument("--out-po", default="output/final_translated.po", help="Output PO file path.")
    parser.add_argument("--target-lang", default="zh_Hant")
    args = parser.parse_args()

    po_entries = parse_po_file(args.original_po)
    tree_validation = validate_translation_tree(args.tree_dir, po_entries, target_lang=args.target_lang)
    if tree_validation["errors"]:
        preview = "\n".join(tree_validation["errors"][:50])
        raise ValueError(f"Translation tree validation failed:\n{preview}")

    po_content = rewrite_po_translations(args.original_po, tree_validation["translations"])

    out_dir = os.path.dirname(args.out_po)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out_po, "w", encoding="utf-8") as handle:
        handle.write(po_content)

    print(
        f"Generated PO file: {args.out_po} "
        f"({len(tree_validation['nodeDirs'])} folders scanned, {len(tree_validation['translations'])} translation files)"
    )


if __name__ == "__main__":
    main()
