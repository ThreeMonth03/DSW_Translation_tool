#!/usr/bin/env python3
import json
import os
import re
from collections import defaultdict

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

PO_FIELD_FALLBACKS = {
    "text": ["text", "title", "label", "description", "name", "url"],
    "title": ["title", "text", "label", "description", "name"],
    "label": ["label", "text", "title", "description", "name"],
    "description": ["description", "label", "text", "title", "name"],
    "name": ["name", "title", "text", "label", "description"],
    "url": ["url"],
    "advice": ["advice", "label", "description", "text"],
}

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
TRANSLATABLE_FIELDS = ("text", "title", "label", "description", "name", "url", "advice")
PRIMARY_NAME_FIELDS = ("title", "label", "name", "text")
RELATED_NAME_UUID_FIELDS = ("targetUuid", "resourcePageUuid")
MANIFEST_NAME = "_translation_tree.json"
UUID_FILENAME = "_uuid.txt"
TRANSLATION_FILENAME = "translation.md"
MAX_SEGMENT_TEXT_LENGTH = 72
FIELD_EXPORT_ORDER = ("title", "label", "text", "advice", "description", "name", "url")


def decode_po_string(value):
    if "\\" not in value:
        return value
    replacements = [
        ("\\\\", "\\"),
        ("\\n", "\n"),
        ("\\t", "\t"),
        ("\\r", "\r"),
        ('\\"', '"'),
        ("\\'", "'"),
        ("\\u2028", "\u2028"),
        ("\\u2029", "\u2029"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def escape_po_string(value):
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def parse_po_string_block(lines, start_index):
    line = lines[start_index].rstrip("\n")
    current = line.split(" ", 1)[1]
    parts = []
    if current != '""':
        parts.append(decode_po_string(current[1:-1]))

    index = start_index + 1
    while index < len(lines):
        current_line = lines[index].rstrip("\n")
        if not current_line.startswith('"'):
            break
        parts.append(decode_po_string(current_line[1:-1]))
        index += 1
    return "".join(parts), index


def parse_po_comment_token(token):
    parts = token.split(":")
    if len(parts) < 3:
        return None
    if not UUID_RE.fullmatch(parts[1]):
        return None
    return {
        "prefix": parts[0],
        "uuid": parts[1],
        "field": parts[2],
        "comment": token,
    }


def parse_po_file(po_path):
    entries = []
    current_comments = []
    current_msgid = None

    with open(po_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\n")

        if line.startswith("#:"):
            current_comments.extend(line[2:].strip().split())
            index += 1
            continue

        if line.startswith("msgid "):
            current_msgid, index = parse_po_string_block(lines, index)
            continue

        if line.startswith("msgstr "):
            current_msgstr, index = parse_po_string_block(lines, index)
            if current_comments and current_msgid is not None:
                for token in current_comments:
                    parsed = parse_po_comment_token(token)
                    if not parsed:
                        continue
                    entries.append({
                        **parsed,
                        "msgid": current_msgid,
                        "msgstr": current_msgstr,
                    })
            current_comments = []
            current_msgid = None
            continue

        if not line:
            current_comments = []
        index += 1

    return entries


def format_po_string_block(keyword, value):
    return [f'{keyword} "{escape_po_string(value)}"\n']


def rewrite_po_translations(original_po_path, translations_by_key):
    with open(original_po_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    output_lines = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line.startswith("#:"):
            output_lines.append(line)
            index += 1
            continue

        comment_lines = []
        comment_tokens = []
        while index < len(lines) and lines[index].startswith("#:"):
            comment_tokens.extend(lines[index][2:].strip().split())
            comment_lines.append(lines[index])
            index += 1

        parsed_tokens = [parse_po_comment_token(token) for token in comment_tokens]
        parsed_tokens = [token for token in parsed_tokens if token]

        extra_comment_lines = []
        while index < len(lines) and lines[index].startswith("#") and not lines[index].startswith("#:"):
            extra_comment_lines.append(lines[index])
            index += 1

        msgid_lines = []
        if index < len(lines) and lines[index].startswith("msgid "):
            _, next_index = parse_po_string_block(lines, index)
            msgid_lines = lines[index:next_index]
            index = next_index

        if index < len(lines) and lines[index].startswith("msgstr "):
            current_msgstr, next_index = parse_po_string_block(lines, index)
            if not parsed_tokens:
                output_lines.extend(comment_lines)
                output_lines.extend(extra_comment_lines)
                output_lines.extend(msgid_lines)
                output_lines.extend(lines[index:next_index])
            else:
                grouped_tokens = []
                for token in parsed_tokens:
                    key = (token["uuid"], token["field"])
                    msgstr_value = translations_by_key.get(key, current_msgstr)
                    if grouped_tokens and grouped_tokens[-1]["msgstr"] == msgstr_value:
                        grouped_tokens[-1]["tokens"].append(token)
                    else:
                        grouped_tokens.append({"msgstr": msgstr_value, "tokens": [token]})

                if len(grouped_tokens) == 1 and len(grouped_tokens[0]["tokens"]) == len(parsed_tokens):
                    output_lines.extend(comment_lines)
                    output_lines.extend(extra_comment_lines)
                    output_lines.extend(msgid_lines)
                    output_lines.extend(format_po_string_block("msgstr", grouped_tokens[0]["msgstr"]))
                else:
                    for group_index, group in enumerate(grouped_tokens):
                        for token in group["tokens"]:
                            output_lines.append(f"#: {token['comment']}\n")
                        output_lines.extend(extra_comment_lines)
                        output_lines.extend(msgid_lines)
                        output_lines.extend(format_po_string_block("msgstr", group["msgstr"]))
                        if group_index < len(grouped_tokens) - 1:
                            output_lines.append("\n")
            index = next_index

    return "".join(output_lines)


def normalize_delta_value(value):
    if isinstance(value, dict) and "changed" in value:
        if value.get("changed"):
            return value.get("value")
        return None
    return value


def merge_event_content(base, delta):
    result = dict(base)
    for key, value in delta.items():
        if key in {"eventType", "annotations"}:
            continue
        normalized = normalize_delta_value(value)
        if normalized is None:
            if key not in result:
                result[key] = None
            continue
        result[key] = normalized
    return result


def load_json_model(json_path):
    with open(json_path, "r", encoding="utf-8") as handle:
        root = json.load(handle)

    events = []
    for package in root.get("packages", []):
        for index, event in enumerate(package.get("events", [])):
            events.append((event.get("createdAt", ""), index, event))
    events.sort(key=lambda item: (item[0], item[1]))

    entity_history = defaultdict(list)
    for _, _, event in events:
        entity_history[event["entityUuid"]].append(event)

    latest_by_uuid = {}
    for entity_uuid, history in entity_history.items():
        state = None
        for event in history:
            content = event.get("content", {})
            if state is None:
                state = dict(content)
            else:
                state = merge_event_content(state, content)
            state["eventType"] = content.get("eventType")
            state["annotations"] = content.get("annotations", [])
            state["parentUuid"] = event.get("parentUuid")
            state["entityUuid"] = entity_uuid
            state["uuid"] = event.get("uuid")
            state["createdAt"] = event.get("createdAt")
        latest_by_uuid[entity_uuid] = {
            "content": state,
            "parentUuid": state.get("parentUuid"),
            "entityUuid": entity_uuid,
        }

    model_info = {
        "id": root.get("id"),
        "kmId": root.get("kmId"),
        "name": root.get("name") or root.get("kmId") or "Knowledge Model",
    }
    return latest_by_uuid, model_info


def get_event_text_value(event, field):
    if not event:
        return None
    content = event.get("content", {})
    if field in content and content[field] is not None:
        return content[field]
    for fallback_field in PO_FIELD_FALLBACKS.get(field, []):
        if fallback_field in content and content[fallback_field] is not None:
            return content[fallback_field]
    if field in content:
        return content[field]
    return None


def build_ancestor_set(latest_by_uuid, referenced_uuids):
    collected = set()
    to_scan = list(referenced_uuids)

    while to_scan:
        current_uuid = to_scan.pop()
        if current_uuid in collected:
            continue
        collected.add(current_uuid)
        event = latest_by_uuid.get(current_uuid)
        if not event:
            continue
        parent_uuid = event.get("parentUuid")
        if parent_uuid and parent_uuid != ZERO_UUID and parent_uuid not in collected:
            to_scan.append(parent_uuid)

    return collected


def build_child_order_lookup(content):
    ordered_child_uuids = []
    for key, value in content.items():
        if key.endswith("Uuids") and isinstance(value, list):
            ordered_child_uuids.extend(value)

    order_lookup = {}
    for index, child_uuid in enumerate(ordered_child_uuids):
        order_lookup.setdefault(child_uuid, index)
    return order_lookup


def sort_tree_children(node):
    order_lookup = build_child_order_lookup(node["content"])
    fallback_index = len(order_lookup) + 1
    node["children"].sort(
        key=lambda child: (
            order_lookup.get(child["entityUuid"], fallback_index),
            child["content"].get("createdAt") or "",
            child["entityUuid"],
        )
    )
    for child in node["children"]:
        sort_tree_children(child)


def build_tree(latest_by_uuid, root_uuids):
    nodes = {}

    for entity_uuid, event in latest_by_uuid.items():
        if entity_uuid not in root_uuids:
            continue
        nodes[entity_uuid] = {
            "entityUuid": entity_uuid,
            "parentUuid": event.get("parentUuid"),
            "eventType": event.get("content", {}).get("eventType"),
            "content": event.get("content", {}),
            "poRefs": [],
            "children": [],
        }

    roots = []
    for entity_uuid, node in nodes.items():
        parent_uuid = node["parentUuid"]
        if parent_uuid and parent_uuid in nodes:
            nodes[parent_uuid]["children"].append(node)
        else:
            roots.append(node)

    roots.sort(key=lambda node: (node["content"].get("createdAt") or "", node["entityUuid"]))
    for root in roots:
        sort_tree_children(root)

    return roots, nodes


def annotate_tree_nodes(tree_roots, po_entries, nodes_map):
    del tree_roots
    for entry in po_entries:
        node = nodes_map.get(entry["uuid"])
        if node is not None:
            node["poRefs"].append(entry)


def validate_po_entries(po_entries, latest_by_uuid):
    missing_entities = []
    missing_fields = []
    mismatches = []

    for entry in po_entries:
        entity_uuid = entry["uuid"]
        if entity_uuid not in latest_by_uuid:
            missing_entities.append(entry)
            continue

        event = latest_by_uuid[entity_uuid]
        actual = get_event_text_value(event, entry["field"])
        if actual is None:
            missing_fields.append({**entry, "availableFields": list(event.get("content", {}).keys())})
            continue

        if actual != entry["msgid"]:
            mismatches.append({**entry, "actual": actual})

    return {
        "totalComments": len(po_entries),
        "missingEntities": len(missing_entities),
        "missingFields": len(missing_fields),
        "mismatches": len(mismatches),
        "missingEntitiesDetails": missing_entities,
        "missingFieldsDetails": missing_fields,
        "mismatchesDetails": mismatches,
    }


def map_field_values_no_filter(po_refs):
    fields = {}
    for ref in po_refs:
        field = ref["field"]
        if field not in fields:
            fields[field] = {
                "msgid": ref.get("msgid", ""),
                "msgstr": ref.get("msgstr", ""),
            }
    return fields


def clean_display_text(value):
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    first_non_empty_line = next((line.strip() for line in text.split("\n") if line.strip()), "")
    return first_non_empty_line or text


def sanitize_path_text(value):
    sanitized = value
    for source, replacement in (
        ("/", " "),
        ("\\", " "),
        (":", " - "),
        ("*", " "),
        ("?", ""),
        ('"', ""),
        ("<", ""),
        (">", ""),
        ("|", " "),
    ):
        sanitized = sanitized.replace(source, replacement)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or "Untitled"


def truncate_path_text(value, max_length=MAX_SEGMENT_TEXT_LENGTH):
    if len(value) <= max_length:
        return value
    shortened = value[: max_length - 3].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    shortened = shortened.rstrip(" .-_")
    return (shortened or value[: max_length - 3]).rstrip() + "..."


def resolve_node_display_name(entity_uuid, latest_by_uuid, model_name=None, visited=None):
    if visited is None:
        visited = set()
    if entity_uuid in visited:
        return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "cycle"}
    visited.add(entity_uuid)

    event = latest_by_uuid.get(entity_uuid)
    if not event:
        return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "missing"}

    content = event.get("content", {})
    for field in PRIMARY_NAME_FIELDS:
        value = clean_display_text(content.get(field))
        if value:
            return value, {"sourceUuid": entity_uuid, "field": field, "relation": "self"}

    for relation_field in RELATED_NAME_UUID_FIELDS:
        related_uuid = content.get(relation_field)
        if related_uuid and related_uuid != ZERO_UUID:
            related_name, related_source = resolve_node_display_name(
                related_uuid,
                latest_by_uuid,
                model_name=model_name,
                visited=set(visited),
            )
            if related_name:
                return related_name, {
                    "sourceUuid": related_source.get("sourceUuid", related_uuid),
                    "field": related_source.get("field"),
                    "relation": relation_field,
                }

    for field in ("description", "url", "advice"):
        value = clean_display_text(content.get(field))
        if value:
            return value, {"sourceUuid": entity_uuid, "field": field, "relation": "self"}

    parent_uuid = event.get("parentUuid")
    if parent_uuid and parent_uuid != ZERO_UUID:
        parent_name, parent_source = resolve_node_display_name(
            parent_uuid,
            latest_by_uuid,
            model_name=model_name,
            visited=set(visited),
        )
        if parent_name:
            return parent_name, {
                "sourceUuid": parent_source.get("sourceUuid", parent_uuid),
                "field": parent_source.get("field"),
                "relation": "parentUuid",
            }

    if model_name:
        return model_name, {"sourceUuid": entity_uuid, "field": "modelName", "relation": "model"}
    return entity_uuid, {"sourceUuid": entity_uuid, "field": "uuid", "relation": "self"}


def build_directory_name(order_index, entity_uuid, latest_by_uuid, model_name):
    raw_name, name_source = resolve_node_display_name(entity_uuid, latest_by_uuid, model_name=model_name)
    safe_name = truncate_path_text(sanitize_path_text(raw_name))
    return f"{order_index:04d} {safe_name} [{entity_uuid[:8]}]", name_source


def field_filename(field, lang):
    return f"{field}.{lang}.txt"


def sort_fields(fields):
    return sorted(fields, key=lambda field: (FIELD_EXPORT_ORDER.index(field) if field in FIELD_EXPORT_ORDER else len(FIELD_EXPORT_ORDER), field))


def render_translation_markdown(entity_uuid, event_type, fields, source_lang="en", target_lang="zh_Hant"):
    ordered_fields = sort_fields(fields.keys())
    lines = [
        "# Translation",
        "",
        f"- UUID: `{entity_uuid}`",
        f"- Event Type: `{event_type}`",
        f"- Edit only the `Translation ({target_lang})` blocks below.",
        "",
    ]

    for field in ordered_fields:
        values = fields[field]
        lines.extend(
            [
                f"## {field}",
                "",
                f"### Source ({source_lang})",
                "",
                "~~~text",
                values.get("msgid", ""),
                "~~~",
                "",
                f"### Translation ({target_lang})",
                "",
                "~~~text",
                values.get("msgstr", ""),
                "~~~",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def parse_translation_markdown(markdown_path):
    with open(markdown_path, "r", encoding="utf-8") as handle:
        lines = handle.read().split("\n")

    fields = {}
    current_field = None
    current_role = None
    in_block = False
    block_lines = []

    for line in lines:
        stripped = line.strip()

        if in_block:
            if stripped.startswith("~~~"):
                fields.setdefault(current_field, {})[current_role] = "\n".join(block_lines)
                in_block = False
                block_lines = []
            else:
                block_lines.append(line)
            continue

        if stripped.startswith("## "):
            current_field = stripped[3:].strip()
            current_role = None
            fields.setdefault(current_field, {})
            continue

        if stripped.startswith("### Source ("):
            current_role = "source"
            continue

        if stripped.startswith("### Translation ("):
            current_role = "target"
            continue

        if stripped.startswith("~~~") and current_field and current_role:
            in_block = True
            block_lines = []

    return fields


def read_existing_manifest(out_dir):
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def remove_previous_export(out_dir):
    manifest = read_existing_manifest(out_dir)
    if not manifest:
        return

    for relative_root in manifest.get("rootPaths", []):
        absolute_root = os.path.join(out_dir, relative_root)
        if os.path.isdir(absolute_root):
            for current_root, dirnames, filenames in os.walk(absolute_root, topdown=False):
                for filename in filenames:
                    os.remove(os.path.join(current_root, filename))
                for dirname in dirnames:
                    os.rmdir(os.path.join(current_root, dirname))
            os.rmdir(absolute_root)

    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    if os.path.exists(manifest_path):
        os.remove(manifest_path)


def export_translation_tree(
    out_dir,
    tree_roots,
    latest_by_uuid,
    model_name,
    source_lang="en",
    target_lang="zh_Hant",
    preserve_existing_translations=True,
):
    os.makedirs(out_dir, exist_ok=True)
    existing_translations = {}
    if preserve_existing_translations and os.path.isdir(out_dir):
        _, existing_translations, _ = scan_translation_tree(out_dir, target_lang=target_lang)
    remove_previous_export(out_dir)

    manifest = {
        "modelName": model_name,
        "sourceLang": source_lang,
        "targetLang": target_lang,
        "translationFile": TRANSLATION_FILENAME,
        "rootPaths": [],
        "nodes": {},
    }

    def write_node(node, parent_dir, order_index):
        directory_name, name_source = build_directory_name(order_index, node["entityUuid"], latest_by_uuid, model_name)
        relative_path = directory_name if not parent_dir else os.path.join(parent_dir, directory_name)
        absolute_path = os.path.join(out_dir, relative_path)
        os.makedirs(absolute_path, exist_ok=True)

        with open(os.path.join(absolute_path, UUID_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(node["entityUuid"])

        fields = map_field_values_no_filter(node["poRefs"])
        ordered_fields = sort_fields(fields.keys())
        translation_fields = {}
        for field in ordered_fields:
            values = fields[field]
            translation_fields[field] = {
                "msgid": values["msgid"],
                "msgstr": existing_translations.get((node["entityUuid"], field), values["msgstr"]),
            }

        if translation_fields:
            with open(os.path.join(absolute_path, TRANSLATION_FILENAME), "w", encoding="utf-8") as handle:
                handle.write(
                    render_translation_markdown(
                        node["entityUuid"],
                        node["eventType"],
                        translation_fields,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )
                )

        manifest["nodes"][node["entityUuid"]] = {
            "path": relative_path,
            "fields": ordered_fields,
            "eventType": node["eventType"],
            "nameSource": name_source,
        }

        for child_index, child in enumerate(node["children"], start=1):
            write_node(child, relative_path, child_index)

    for root_index, root in enumerate(tree_roots, start=1):
        directory_name, _ = build_directory_name(root_index, root["entityUuid"], latest_by_uuid, model_name)
        manifest["rootPaths"].append(directory_name)
        write_node(root, "", root_index)

    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    return manifest


def scan_translation_tree(tree_dir, target_lang="zh_Hant"):
    node_dirs = {}
    translations = {}
    duplicate_uuids = []

    for current_root, dirnames, filenames in os.walk(tree_dir):
        dirnames.sort()
        filenames.sort()
        if UUID_FILENAME not in filenames:
            continue

        uuid_path = os.path.join(current_root, UUID_FILENAME)
        with open(uuid_path, "r", encoding="utf-8") as handle:
            entity_uuid = handle.read().strip()

        if entity_uuid in node_dirs:
            duplicate_uuids.append((entity_uuid, node_dirs[entity_uuid], current_root))
            continue
        node_dirs[entity_uuid] = current_root

        translation_markdown_path = os.path.join(current_root, TRANSLATION_FILENAME)
        if os.path.exists(translation_markdown_path):
            parsed_fields = parse_translation_markdown(translation_markdown_path)
            for field, values in parsed_fields.items():
                if "target" in values:
                    translations[(entity_uuid, field)] = values.get("target", "")
            continue

        lang_suffix = f".{target_lang}.txt"
        for filename in filenames:
            if filename.endswith(lang_suffix):
                field = filename[: -len(lang_suffix)]
                with open(os.path.join(current_root, filename), "r", encoding="utf-8") as handle:
                    translations[(entity_uuid, field)] = handle.read()

    return node_dirs, translations, duplicate_uuids


def validate_translation_tree(tree_dir, po_entries, target_lang="zh_Hant"):
    manifest = read_existing_manifest(tree_dir)
    node_dirs, translations, duplicate_uuids = scan_translation_tree(tree_dir, target_lang=target_lang)

    errors = []
    if duplicate_uuids:
        errors.extend(
            [
                "Duplicate UUID folder detected for "
                + entity_uuid
                + f": {first_path} and {second_path}"
                for entity_uuid, first_path, second_path in duplicate_uuids
            ]
        )

    if manifest:
        expected_nodes = set(manifest.get("nodes", {}).keys())
        actual_nodes = set(node_dirs.keys())
        missing_nodes = sorted(expected_nodes - actual_nodes)
        extra_nodes = sorted(actual_nodes - expected_nodes)
        if missing_nodes:
            errors.extend([f"Missing UUID folder: {entity_uuid}" for entity_uuid in missing_nodes[:50]])
        if extra_nodes:
            errors.extend([f"Unexpected UUID folder: {entity_uuid}" for entity_uuid in extra_nodes[:50]])

    expected_fields_by_uuid = defaultdict(set)
    for entry in po_entries:
        expected_fields_by_uuid[entry["uuid"]].add(entry["field"])

    for entity_uuid, fields in sorted(expected_fields_by_uuid.items()):
        folder_path = node_dirs.get(entity_uuid)
        if folder_path is None:
            continue
        for field in sorted(fields):
            if (entity_uuid, field) not in translations:
                translation_markdown_path = os.path.join(folder_path, TRANSLATION_FILENAME)
                if os.path.exists(translation_markdown_path):
                    errors.append(f"Missing translation block: {translation_markdown_path} -> {field}")
                else:
                    expected_path = os.path.join(folder_path, field_filename(field, target_lang))
                    errors.append(f"Missing translation file: {expected_path}")

    return {
        "manifest": manifest,
        "nodeDirs": node_dirs,
        "translations": translations,
        "errors": errors,
    }


def collect_translation_status(tree_dir, source_lang="en", target_lang="zh_Hant"):
    manifest = read_existing_manifest(tree_dir)
    if not manifest:
        raise ValueError(f"Translation tree manifest not found in {tree_dir}")

    _, translations, _ = scan_translation_tree(tree_dir, target_lang=target_lang)
    folders = []
    summary = {
        "totalNodes": len(manifest.get("nodes", {})),
        "translatableNodes": 0,
        "completeFolders": 0,
        "pendingFolders": 0,
        "totalFields": 0,
        "translatedFields": 0,
        "untranslatedFields": 0,
    }

    for entity_uuid, node in manifest.get("nodes", {}).items():
        if not node["fields"]:
            continue

        summary["translatableNodes"] += 1
        folder_status = {
            "uuid": entity_uuid,
            "path": node["path"],
            "eventType": node["eventType"],
            "untranslatedFields": [],
            "translatedFields": [],
        }

        for field in node["fields"]:
            summary["totalFields"] += 1
            target_text = translations.get((entity_uuid, field))
            if target_text is None or not target_text.strip():
                folder_status["untranslatedFields"].append(field)
                summary["untranslatedFields"] += 1
            else:
                folder_status["translatedFields"].append(field)
                summary["translatedFields"] += 1

        if folder_status["untranslatedFields"]:
            summary["pendingFolders"] += 1
        else:
            summary["completeFolders"] += 1

        folders.append(folder_status)

    return {
        "summary": summary,
        "folders": folders,
    }
