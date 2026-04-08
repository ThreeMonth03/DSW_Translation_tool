#!/usr/bin/env python3
import argparse
import re
import os
from collections import defaultdict

def parse_markdown(md_path):
    """
    Parse Markdown file to extract nodes with UUID, level, and text content per field.
    Returns a list of (level, uuid, fields_dict) tuples.
    """
    nodes_dict = {}  # uuid -> (level, uuid, fields_dict)
    current_level = 0
    current_uuid = None
    current_field = None
    current_text = []
    in_code_block = False
    
    with open(md_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.rstrip()
            if line.startswith('```'):
                if in_code_block:
                    # End of code block
                    in_code_block = False
                    if current_uuid and current_field:
                        text = '\n'.join(current_text).strip()
                        # Get or create node
                        if current_uuid not in nodes_dict:
                            nodes_dict[current_uuid] = (current_level, current_uuid, {})
                        nodes_dict[current_uuid][2][current_field] = text
                        current_text = []
                        current_field = None
                else:
                    # Start of code block
                    in_code_block = True
                    current_text = []
            elif in_code_block:
                current_text.append(line)
            elif line.startswith('<!-- UUID: ') and line.endswith(' -->'):
                # Extract full UUID from HTML comment
                full_uuid = line[12:-4]  # Remove "<!-- UUID: " and " -->"
                current_uuid = full_uuid
                # Ensure node exists even if it has no fields
                if current_uuid not in nodes_dict:
                    nodes_dict[current_uuid] = (current_level, current_uuid, {})
            elif re.match(r'^#+\s+[0-9a-f]{8}\.\.\.[0-9a-f]{4}', line):
                # UUID header with shortened UUID - extract level
                match = re.match(r'^(#+)\s+', line)
                if match:
                    current_level = len(match.group(1))
                    # UUID will be set by the following HTML comment
            elif line.startswith('### ') or line.startswith('#### ') or line.startswith('##### ') or line.startswith('###### '):
                # Field header (any level deeper than UUID header)
                field = line.lstrip('#').strip()
                current_field = field
    
    return list(nodes_dict.values())

def build_tree_from_nodes(nodes):
    """
    Build a tree structure from nodes list.
    Returns roots and a dict of uuid -> node.
    """
    node_dict = {}
    roots = []
    stack = []  # Stack for parent tracking
    
    for level, uuid, text in nodes:
        node = {
            'uuid': uuid,
            'level': level,
            'text': text,
            'children': []
        }
        node_dict[uuid] = node
        
        # Find parent: pop stack until we find a parent with level < current
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        
        if stack:
            parent = stack[-1]
            parent['children'].append(node)
        else:
            roots.append(node)
        
        stack.append(node)
    
    return roots, node_dict

def validate_structure(en_nodes, zh_nodes):
    """
    Validate that en.md and zh.md have matching UUIDs and levels.
    """
    en_uuids = {(level, uuid) for level, uuid, _ in en_nodes}
    zh_uuids = {(level, uuid) for level, uuid, _ in zh_nodes}
    
    if en_uuids != zh_uuids:
        missing_in_zh = en_uuids - zh_uuids
        extra_in_zh = zh_uuids - en_uuids
        errors = []
        if missing_in_zh:
            errors.append(f"UUIDs/levels missing in zh.md: {missing_in_zh}")
        if extra_in_zh:
            errors.append(f"Extra UUIDs/levels in zh.md: {extra_in_zh}")
        raise ValueError("Structure mismatch between en.md and zh.md: " + "; ".join(errors))
    
    print("Structure validation passed: UUIDs and levels match between en.md and zh.md")

def generate_po_entries(en_nodes, zh_nodes, original_po_path):
    """
    Generate PO entries: preserve original PO structure, only override 
    Chinese translations from zh.md if they were edited.
    """
    zh_dict = {uuid: fields for _, uuid, fields in zh_nodes}
    
    # Read original PO completely to preserve all formatting
    po_lines = []
    with open(original_po_path, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for comment line with UUID/field info
        if line.startswith('#:'):
            # Extract uuid and field from comment
            comment_text = line[2:].strip()
            parts = comment_text.split(':')
            if len(parts) >= 3:
                prefix = parts[0]
                uuid = parts[1]
                field = parts[2]
                
                # Output comment as is
                po_lines.append(line)
                i += 1
                
                # Read msgid
                if i < len(lines) and lines[i].startswith('msgid'):
                    po_lines.append(lines[i])
                    i += 1
                
                # Read msgstr - this is what we might override
                if i < len(lines) and lines[i].startswith('msgstr'):
                    original_msgstr_line = lines[i]
                    zh_value = zh_dict.get(uuid, {}).get(field, '')
                    
                    if zh_value:
                        # User edited this field - use the new value
                        escaped = zh_value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
                        po_lines.append(f'msgstr "{escaped}"\n')
                    else:
                        # Keep original msgstr (even if empty)
                        po_lines.append(original_msgstr_line)
                    i += 1
            else:
                po_lines.append(line)
                i += 1
        else:
            po_lines.append(line)
            i += 1
    
    return ''.join(po_lines)



def main():
    parser = argparse.ArgumentParser(
        description='Convert Markdown files back to PO format.',
    )
    parser.add_argument('--en-md', default='output/en.md', help='Path to English Markdown file.')
    parser.add_argument('--zh-md', default='output/zh.md', help='Path to Chinese Markdown file.')
    parser.add_argument('--original-po', default='files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po', help='Path to original PO file for reference.')
    parser.add_argument('--out-po', default='output/translated.po', help='Output PO file path.')
    args = parser.parse_args()
    
    # Parse Markdown files
    en_nodes = parse_markdown(args.en_md)
    zh_nodes = parse_markdown(args.zh_md)
    
    # Validate structure
    validate_structure(en_nodes, zh_nodes)
    
    # Generate PO
    po_content = generate_po_entries(en_nodes, zh_nodes, args.original_po)
    
    # Write output
    os.makedirs(os.path.dirname(args.out_po), exist_ok=True)
    with open(args.out_po, 'w', encoding='utf-8') as fh:
        fh.write(po_content)
    
    print(f'Generated PO file: {args.out_po}')

if __name__ == '__main__':
    main()