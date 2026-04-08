python3 src/po_json_tree.py --po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po --json files/dsw_root_2.7.0.json --sync-po output/synced.po#!/usr/bin/env python3
import argparse
import subprocess
import os

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(result.stdout)
    return True

def main():
    parser = argparse.ArgumentParser(description='PO Translation Workflow with Markdown')
    parser.add_argument('--po', default='files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po')
    parser.add_argument('--json', default='files/dsw_root_2.7.0.json')
    parser.add_argument('--out-dir', default='output')
    parser.add_argument('--final-po', default='output/final_translated.po')
    args = parser.parse_args()
    
    os.makedirs(args.out_dir, exist_ok=True)
    
    # Step 1: Generate Markdown from original PO (already matches JSON)
    print("Step 1: Generating Markdown from original PO...")
    if not run_command(f"python3 src/po_json_tree.py --po {args.po} --json {args.json} --out-dir {args.out_dir}"):
        return
    
    # Step 2: Assume zh.md is edited by translator
    print("Step 2: Please edit output/zh.md with translations, then press Enter to continue.")
    input()
    
    # Step 3: Generate final PO from Markdown
    print("Step 3: Generating final PO from Markdown...")
    if not run_command(f"python3 src/md_to_po.py --en-md {args.out_dir}/en.md --zh-md {args.out_dir}/zh.md --original-po {args.po} --out-po {args.final_po}"):
        return
    
    # Step 4: Validate final PO
    print("Step 4: Validating final PO...")
    if not run_command(f"python3 src/po_json_tree.py --po {args.final_po} --json {args.json} --report-out {args.out_dir}/final_report.json"):
        return
    
    print(f"Workflow complete! Check {args.final_po} and {args.out_dir}/final_report.json")

if __name__ == '__main__':
    main()