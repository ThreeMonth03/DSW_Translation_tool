#!/usr/bin/env python3
import argparse
import codecs
import json
import os
import re
from collections import defaultdict

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

PO_FIELD_FALLBACKS = {
    'text': ['text', 'title', 'label', 'description', 'name', 'url'],
    'title': ['title', 'text', 'label', 'description', 'name'],
    'label': ['label', 'text', 'title', 'description', 'name'],
    'description': ['description', 'label', 'text', 'title', 'name'],
    'name': ['name', 'title', 'text', 'label', 'description'],
    'url': ['url'],
    'advice': ['advice', 'label', 'description', 'text'],
}

EVENT_TEXT_FIELDS = [
    'text',
    'title',
    'label',
    'description',
    'name',
    'url',
    'advice',
]

ZERO_UUID = '00000000-0000-0000-0000-000000000000'


def decode_po_string(value):
    if '\\' not in value:
        return value
    replacements = [
        ('\\\\', '\\'),
        ('\\n', '\n'),
        ('\\t', '\t'),
        ('\\r', '\r'),
        ('\\"', '"'),
        ("\\'", "'"),
        ('\\u2028', '\u2028'),
        ('\\u2029', '\u2029'),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def parse_po_string(first_line, lines_iter):
    text = ''
    current = first_line.strip()
    if current.startswith('msgid ') or current.startswith('msgstr '):
        current = current.split(' ', 1)[1].strip()
    if current.startswith('"'):
        if current == '""':
            text = ''
        elif current.endswith('"'):
            return decode_po_string(current[1:-1])
        else:
            text = current[1:]
    for line in lines_iter:
        line = line.strip()
        if not line.startswith('"'):
            break
        piece = line[1:-1]
        text += decode_po_string(piece)
    return decode_po_string(text)


def parse_po_file(po_path):
    entries = []
    current_comments = []
    current_msgid = None
    current_msgstr = None

    with open(po_path, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        if line.startswith('#:'):
            current_comments.extend(line[2:].strip().split())
            i += 1
            continue
        if line.startswith('msgid '):
            current_msgid = parse_po_string(line, iter(lines[i + 1:]))
            # advance past multiline msgid
            while i + 1 < len(lines) and lines[i + 1].strip().startswith('"'):
                i += 1
            i += 1
            continue
        if line.startswith('msgstr '):
            current_msgstr = parse_po_string(line, iter(lines[i + 1:]))
            while i + 1 < len(lines) and lines[i + 1].strip().startswith('"'):
                i += 1
            if current_comments and current_msgid is not None:
                for token in current_comments:
                    parts = token.split(':')
                    if len(parts) >= 3 and UUID_RE.fullmatch(parts[1]):
                        prefix = parts[0]
                        uuid = parts[1]
                        field = parts[2]
                        entries.append({
                            'prefix': prefix,
                            'uuid': uuid,
                            'field': field,
                            'comment': token,
                            'msgid': current_msgid,
                            'msgstr': current_msgstr,
                        })
            current_comments = []
            current_msgid = None
            current_msgstr = None
            i += 1
            continue
        i += 1
    return entries


def normalize_delta_value(value):
    if isinstance(value, dict) and 'changed' in value:
        if value.get('changed'):
            return value.get('value')
        return None
    return value


def merge_event_content(base, delta):
    result = dict(base)
    for key, value in delta.items():
        if key == 'eventType' or key == 'annotations':
            continue
        normalized = normalize_delta_value(value)
        if normalized is None:
            if key not in result:
                result[key] = None
            continue
        result[key] = normalized
    return result


def load_json_events(json_path):
    with open(json_path, 'r', encoding='utf-8') as fh:
        root = json.load(fh)

    events = []
    for pkg in root.get('packages', []):
        for idx, ev in enumerate(pkg.get('events', [])):
            created_at = ev.get('createdAt', '')
            events.append((created_at, idx, ev))
    events.sort(key=lambda item: (item[0], item[1]))

    entity_history = defaultdict(list)
    for _, _, ev in events:
        entity_history[ev['entityUuid']].append(ev)

    final_state = {}
    for entity_uuid, history in entity_history.items():
        state = None
        for ev in history:
            content = ev.get('content', {})
            if state is None:
                state = dict(content)
            else:
                state = merge_event_content(state, content)
            state['eventType'] = content.get('eventType')
            state['annotations'] = content.get('annotations', [])
            state['parentUuid'] = ev.get('parentUuid')
            state['entityUuid'] = entity_uuid
            state['uuid'] = ev.get('uuid')
            state['createdAt'] = ev.get('createdAt')
        final_state[entity_uuid] = {
            'content': state,
            'parentUuid': state.get('parentUuid'),
            'entityUuid': entity_uuid,
        }
    return final_state


def get_event_text_value(event, field):
    content = event.get('content', {})
    if field in content and content[field] is not None:
        return content[field]
    if field in PO_FIELD_FALLBACKS:
        for alt in PO_FIELD_FALLBACKS[field]:
            if alt in content and content[alt] is not None:
                return content[alt]
    if field in content:
        return content[field]
    return None


def build_ancestor_set(latest_by_uuid, referenced_uuids):
    collected = set()
    to_scan = list(referenced_uuids)
    while to_scan:
        uuid = to_scan.pop()
        if uuid in collected:
            continue
        collected.add(uuid)
        event = latest_by_uuid.get(uuid)
        if not event:
            continue
        parent_uuid = event.get('parentUuid')
        if parent_uuid and parent_uuid != ZERO_UUID and parent_uuid not in collected:
            to_scan.append(parent_uuid)
    return collected


def build_tree(latest_by_uuid, root_uuids):
    nodes = {}
    children = defaultdict(list)
    for uuid, event in latest_by_uuid.items():
        if uuid not in root_uuids:
            continue
        parent = event.get('parentUuid')
        nodes[uuid] = {
            'entityUuid': uuid,
            'parentUuid': parent,
            'eventType': event.get('content', {}).get('eventType'),
            'content': event.get('content', {}),
            'poRefs': [],
            'children': [],
        }
        if parent and parent != ZERO_UUID:
            children[parent].append(uuid)

    roots = []
    for uuid, node in nodes.items():
        parent = node['parentUuid']
        if parent and parent in nodes:
            nodes[parent]['children'].append(node)
        else:
            roots.append(node)
    return roots, nodes


def annotate_tree_nodes(tree_roots, po_entries, nodes_map):
    for entry in po_entries:
        node = nodes_map.get(entry['uuid'])
        if node is not None:
            node['poRefs'].append(entry)


def map_field_values(po_refs, key):
    result = {}
    for ref in po_refs:
        field = ref['field']
        value = ref.get(key)
        if field in result:
            if isinstance(result[field], list):
                result[field].append(value)
            else:
                result[field] = [result[field], value]
        else:
            result[field] = value
    return result


def map_field_values_no_filter(po_refs):
    """
    Map all field values from po_refs, preserving structure.
    Returns dict with field -> value mapping (only first occurrence).
    Also returns all_fields set for consistency checking.
    """
    result = {}
    all_fields = set()
    
    for ref in po_refs:
        field = ref['field']
        all_fields.add(field)
        
        # Only keep first value per field
        if field not in result:
            result[field] = {
                'msgid': ref.get('msgid', ''),
                'msgstr': ref.get('msgstr', ''),
            }
    
    return result, all_fields


def build_yaml_node(node, lang):
    yaml_node = {
        'entityUuid': node['entityUuid'],
        'parentUuid': node['parentUuid'],
        'eventType': node['eventType'],
    }
    
    # Collect all fields with both msgid and msgstr for consistent structure
    fields, _ = map_field_values_no_filter(node['poRefs'])
    
    # Build fields dict based on language
    yaml_node['fields'] = {}
    for field, values in fields.items():
        if lang == 'en':
            yaml_node['fields'][field] = values['msgid']
        else:  # lang == 'zh'
            yaml_node['fields'][field] = values['msgstr']
    
    yaml_node['children'] = [build_yaml_node(child, lang) for child in node['children']]
    return yaml_node


def build_yaml_tree(tree_roots, lang):
    return [build_yaml_node(root, lang) for root in tree_roots]


def markdown_dump(data, stream, indent=0, lang='en'):
    if isinstance(data, dict):
        uuid = data.get('entityUuid', 'unknown')
        fields = data.get('fields', {})
        children = data.get('children', [])
        
        # Shorten UUID for better readability (first 8 + last 4 chars)
        short_uuid = f"{uuid[:8]}...{uuid[-4:]}" if len(uuid) == 36 else uuid
        
        # Write header for this node
        header_level = '#' * (indent + 1)
        stream.write(f"{header_level} {short_uuid}\n")
        stream.write(f"<!-- UUID: {uuid} -->\n\n")
        
        # Write fields with consistent indentation (always one level deeper than UUID header)
        field_level = '#' * (indent + 2)
        for field, value in fields.items():
            stream.write(f"{field_level} {field}\n\n")
            if value:
                stream.write(f"```\n{str(value)}\n```\n\n")
            else:
                # Empty placeholder for untranslated field
                stream.write("```\n```\n\n")
        
        # Recursively write children
        for child in children:
            markdown_dump(child, stream, indent + 1, lang)
    elif isinstance(data, list):
        for item in data:
            markdown_dump(item, stream, indent, lang)


def validate_po_entries(po_entries, latest_by_uuid):
    missing_entities = []
    missing_fields = []
    mismatches = []
    for entry in po_entries:
        uuid = entry['uuid']
        if uuid not in latest_by_uuid:
            missing_entities.append(entry)
            continue
        event = latest_by_uuid[uuid]
        actual = get_event_text_value(event, entry['field'])
        if actual is None:
            missing_fields.append({**entry, 'availableFields': list(event.get('content', {}).keys())})
            continue
        expected = entry['msgid']
        if actual != expected:
            mismatches.append({
                **entry,
                'actual': actual,
            })
    return {
        'totalComments': len(po_entries),
        'missingEntities': len(missing_entities),
        'missingFields': len(missing_fields),
        'mismatches': len(mismatches),
        'missingEntitiesDetails': missing_entities,
        'missingFieldsDetails': missing_fields,
        'mismatchesDetails': mismatches,
    }


def sync_po_with_json(po_path, json_path, synced_po_path):
    """
    Sync PO msgid with JSON latest values to ensure no mismatches.
    Creates a new PO with msgid from JSON, msgstr from original PO.
    """
    po_entries = parse_po_file(po_path)
    latest_by_uuid = load_json_events(json_path)
    
    synced_lines = [
        '# Synced PO file with JSON latest values',
        '# Original PO: ' + po_path,
        '',
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '',
    ]
    
    for entry in po_entries:
        uuid = entry['uuid']
        field = entry['field']
        prefix = entry['prefix']
        msgstr = entry['msgstr']
        
        # Get latest msgid from JSON
        msgid = get_event_text_value(latest_by_uuid.get(uuid), field)
        if msgid is None:
            msgid = entry['msgid']  # Fallback to original
        
        comment = f"#: {prefix}:{uuid}:{field}"
        synced_lines.extend([
            '',
            comment,
            f'msgid "{msgid.replace(chr(10), "\\n").replace(chr(13), "\\r").replace("\\", "\\\\").replace("\"", "\\\"")}"',
            f'msgstr "{msgstr.replace(chr(10), "\\n").replace(chr(13), "\\r").replace("\\", "\\\\").replace("\"", "\\\"")}"',
        ])
    
    with open(synced_po_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(synced_lines))
    
    print(f'Created synced PO: {synced_po_path}')


def main():
    parser = argparse.ArgumentParser(
        description='Build a tree from dsw JSON and validate PO comment UUIDs against latest event values.',
    )
    parser.add_argument('--po', default='files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po')
    parser.add_argument('--json', default='files/dsw_root_2.7.0.json')
    parser.add_argument('--out-dir', default='output',
                        help='Write the generated en.yaml, zh.yaml, and uuid.yaml files to this directory.')
    parser.add_argument('--tree-out', default=None,
                        help='Optionally write the generated tree to this JSON file.')
    parser.add_argument('--report-out', default=None,
                        help='Write validation report to this JSON file.')
    parser.add_argument('--sync-po', default=None,
                        help='Create a synced PO file with msgid from JSON latest values, msgstr from original PO.')
    args = parser.parse_args()

    po_entries = parse_po_file(args.po)
    latest_by_uuid = load_json_events(args.json)

    po_uuids = {entry['uuid'] for entry in po_entries}
    relevant_uuids = build_ancestor_set(latest_by_uuid, po_uuids)
    tree_roots, nodes_map = build_tree(latest_by_uuid, relevant_uuids)
    annotate_tree_nodes(tree_roots, po_entries, nodes_map)
    report = validate_po_entries(po_entries, latest_by_uuid)

    if args.sync_po:
        sync_po_with_json(args.po, args.json, args.sync_po)
        return  # Exit after syncing

    os.makedirs(args.out_dir, exist_ok=True)
    en_path = os.path.join(args.out_dir, 'en.md')
    zh_path = os.path.join(args.out_dir, 'zh.md')

    en_tree = build_yaml_tree(tree_roots, 'en')
    zh_tree = build_yaml_tree(tree_roots, 'zh')

    with open(en_path, 'w', encoding='utf-8') as fh:
        markdown_dump(en_tree, fh, lang='en')
    print(f'Wrote English Markdown tree to {en_path}')

    with open(zh_path, 'w', encoding='utf-8') as fh:
        markdown_dump(zh_tree, fh, lang='zh')
    print(f'Wrote Chinese Markdown tree to {zh_path}')

    if args.tree_out:
        with open(args.tree_out, 'w', encoding='utf-8') as fh:
            json.dump({'roots': tree_roots, 'report': report}, fh, ensure_ascii=False, indent=2)
        print(f'Wrote tree output to {args.tree_out}')
    if args.report_out:
        with open(args.report_out, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f'Wrote validation report to {args.report_out}')

if __name__ == '__main__':
    main()
