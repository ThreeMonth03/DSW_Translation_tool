#!/usr/bin/env python3
"""Backward-compatible facade over the refactored translation tooling package."""

from __future__ import annotations

from dataclasses import asdict

from dsw_translation_tool.constants import (
    FIELD_EXPORT_ORDER,
    MANIFEST_NAME,
    MAX_SEGMENT_TEXT_LENGTH,
    PRIMARY_NAME_FIELDS,
    RELATED_NAME_UUID_FIELDS,
    TRANSLATION_FILENAME,
    UUID_FILENAME,
    ZERO_UUID,
)
from dsw_translation_tool.model import DswModelService
from dsw_translation_tool.models import PoEntry, TreeNode
from dsw_translation_tool.po import PoCatalogParser, PoCatalogWriter
from dsw_translation_tool.tree import TranslationMarkdownDocument, TranslationTreeRepository
from dsw_translation_tool.workflow import TranslationWorkflowService


def parse_po_file(po_path):
    return [asdict(entry) for entry in PoCatalogParser(po_path).parse_entries()]


def rewrite_po_translations(original_po_path, translations_by_key):
    return PoCatalogWriter.rewrite_translations(original_po_path, translations_by_key)


def load_json_model(json_path):
    latest_by_uuid, model_info = DswModelService.load_model(json_path)
    return latest_by_uuid, {"id": model_info.id, "kmId": model_info.km_id, "name": model_info.name}


def build_ancestor_set(latest_by_uuid, referenced_uuids):
    return DswModelService.build_ancestor_set(latest_by_uuid, referenced_uuids)


def build_tree(latest_by_uuid, root_uuids):
    tree_roots, _ = DswModelService.build_tree(latest_by_uuid, root_uuids)
    roots_as_dicts = []
    nodes_map = {}
    for root in tree_roots:
        roots_as_dicts.append(_tree_node_to_dict(root, nodes_map))
    return roots_as_dicts, nodes_map


def annotate_tree_nodes(tree_roots, po_entries, nodes_map):
    del tree_roots
    for entry in po_entries:
        node = nodes_map.get(entry["uuid"])
        if node is not None:
            node.setdefault("poRefs", []).append(entry)


def validate_po_entries(po_entries, latest_by_uuid):
    entries = [_po_entry_from_dict(entry) for entry in po_entries]
    return DswModelService.validate_po_entries(entries, latest_by_uuid)


def read_existing_manifest(out_dir):
    return TranslationTreeRepository().read_existing_manifest(out_dir)


def export_translation_tree(
    out_dir,
    tree_roots,
    latest_by_uuid,
    model_name,
    source_lang="en",
    target_lang="zh_Hant",
    preserve_existing_translations=True,
):
    repository = TranslationTreeRepository(source_lang=source_lang, target_lang=target_lang)
    return repository.export_tree(
        out_dir=out_dir,
        tree_roots=[_tree_node_from_dict(node) for node in tree_roots],
        latest_by_uuid=latest_by_uuid,
        model_name=model_name,
        preserve_existing_translations=preserve_existing_translations,
    )


def scan_translation_tree(tree_dir, target_lang="zh_Hant"):
    scan_result = TranslationTreeRepository(target_lang=target_lang).scan(tree_dir)
    return scan_result["nodeDirs"], scan_result["translations"], scan_result["duplicateUuids"]


def validate_translation_tree(tree_dir, po_entries, target_lang="zh_Hant"):
    repository = TranslationTreeRepository(target_lang=target_lang)
    entries = [_po_entry_from_dict(entry) for entry in po_entries]
    return repository.validate(tree_dir, entries)


def collect_translation_status(tree_dir, source_lang="en", target_lang="zh_Hant"):
    status = TranslationWorkflowService(
        source_lang=source_lang,
        target_lang=target_lang,
    ).collect_status(tree_dir)
    return {
        "summary": status["summary"],
        "folders": [
            {
                "uuid": folder.uuid,
                "path": folder.path,
                "eventType": folder.event_type,
                "untranslatedFields": list(folder.untranslated_fields),
                "translatedFields": list(folder.translated_fields),
            }
            for folder in status["folders"]
        ],
    }


def render_translation_markdown(entity_uuid, event_type, fields, source_lang="en", target_lang="zh_Hant"):
    return TranslationMarkdownDocument.render(
        entity_uuid=entity_uuid,
        event_type=event_type,
        fields=_field_states_from_legacy(fields),
        source_lang=source_lang,
        target_lang=target_lang,
    )


def parse_translation_markdown(markdown_path):
    parsed = TranslationMarkdownDocument.parse(markdown_path)
    return {
        field: {"source": state.source_text, "target": state.target_text}
        for field, state in parsed.items()
    }


def _tree_node_to_dict(node: TreeNode, nodes_map: dict[str, dict]) -> dict:
    node_dict = {
        "entityUuid": node.entity_uuid,
        "parentUuid": node.parent_uuid,
        "eventType": node.event_type,
        "content": node.content,
        "poRefs": [asdict(reference) for reference in node.po_refs],
        "children": [],
    }
    nodes_map[node.entity_uuid] = node_dict
    node_dict["children"] = [_tree_node_to_dict(child, nodes_map) for child in node.children]
    return node_dict


def _tree_node_from_dict(node_dict: dict) -> TreeNode:
    node = TreeNode(
        entity_uuid=node_dict["entityUuid"],
        parent_uuid=node_dict.get("parentUuid"),
        event_type=node_dict.get("eventType"),
        content=node_dict.get("content", {}),
        po_refs=[_po_entry_from_dict(entry) for entry in node_dict.get("poRefs", [])],
        children=[],
    )
    node.children = [_tree_node_from_dict(child) for child in node_dict.get("children", [])]
    return node


def _po_entry_from_dict(entry: dict) -> PoEntry:
    return PoEntry(
        prefix=entry["prefix"],
        uuid=entry["uuid"],
        field=entry["field"],
        comment=entry["comment"],
        msgid=entry["msgid"],
        msgstr=entry["msgstr"],
    )


def _field_states_from_legacy(fields):
    from dsw_translation_tool.models import TranslationFieldState

    return {
        field: TranslationFieldState(
            source_text=values.get("msgid", ""),
            target_text=values.get("msgstr", ""),
        )
        for field, values in fields.items()
    }


__all__ = [
    "FIELD_EXPORT_ORDER",
    "MANIFEST_NAME",
    "MAX_SEGMENT_TEXT_LENGTH",
    "PRIMARY_NAME_FIELDS",
    "RELATED_NAME_UUID_FIELDS",
    "TRANSLATION_FILENAME",
    "UUID_FILENAME",
    "ZERO_UUID",
    "annotate_tree_nodes",
    "build_ancestor_set",
    "build_tree",
    "collect_translation_status",
    "export_translation_tree",
    "load_json_model",
    "parse_po_file",
    "parse_translation_markdown",
    "read_existing_manifest",
    "render_translation_markdown",
    "rewrite_po_translations",
    "scan_translation_tree",
    "validate_po_entries",
    "validate_translation_tree",
]
