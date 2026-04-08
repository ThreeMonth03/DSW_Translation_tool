"""Translation tree repository and document handling."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .constants import (
    FIELD_EXPORT_ORDER,
    MANIFEST_NAME,
    MAX_SEGMENT_TEXT_LENGTH,
    TRANSLATION_FILENAME,
    UUID_FILENAME,
)
from .model import DswModelService
from .models import TreeFolderSnapshot, TreeNode, TranslationFieldState, TranslationStatusFolder


class TranslationMarkdownDocument:
    """Handles rendering and parsing the translator-facing markdown file."""

    @staticmethod
    def sort_fields(fields) -> list[str]:
        return sorted(
            fields,
            key=lambda field: (
                FIELD_EXPORT_ORDER.index(field) if field in FIELD_EXPORT_ORDER else len(FIELD_EXPORT_ORDER),
                field,
            ),
        )

    @staticmethod
    def render(
        entity_uuid: str,
        event_type: str | None,
        fields: dict[str, TranslationFieldState],
        source_lang: str,
        target_lang: str,
    ) -> str:
        lines = [
            "# Translation",
            "",
            f"- UUID: `{entity_uuid}`",
            f"- Event Type: `{event_type}`",
            f"- Edit only the `Translation ({target_lang})` blocks below.",
            "",
        ]

        for field in TranslationMarkdownDocument.sort_fields(fields.keys()):
            state = fields[field]
            lines.extend(
                [
                    f"## {field}",
                    "",
                    f"### Source ({source_lang})",
                    "",
                    "~~~text",
                    state.source_text,
                    "~~~",
                    "",
                    f"### Translation ({target_lang})",
                    "",
                    "~~~text",
                    state.target_text,
                    "~~~",
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def parse(markdown_path: str) -> dict[str, TranslationFieldState]:
        lines = Path(markdown_path).read_text(encoding="utf-8").split("\n")
        fields: dict[str, dict[str, str]] = {}
        current_field: str | None = None
        current_role: str | None = None
        in_block = False
        block_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            if in_block:
                if stripped.startswith("~~~"):
                    fields.setdefault(current_field or "", {})[current_role or ""] = "\n".join(block_lines)
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

        return {
            field: TranslationFieldState(
                source_text=values.get("source", ""),
                target_text=values.get("target", ""),
            )
            for field, values in fields.items()
        }


class TranslationTreeRepository:
    """Owns export, scan, validate, and status collection for translation trees."""

    def __init__(self, source_lang: str = "en", target_lang: str = "zh_Hant"):
        self.source_lang = source_lang
        self.target_lang = target_lang

    def read_existing_manifest(self, out_dir: str) -> dict | None:
        manifest_path = Path(out_dir) / MANIFEST_NAME
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def remove_previous_export(self, out_dir: str) -> None:
        manifest = self.read_existing_manifest(out_dir)
        if not manifest:
            return

        for relative_root in manifest.get("rootPaths", []):
            absolute_root = Path(out_dir) / relative_root
            if absolute_root.is_dir():
                for current_root, dirnames, filenames in os.walk(absolute_root, topdown=False):
                    for filename in filenames:
                        (Path(current_root) / filename).unlink()
                    for dirname in dirnames:
                        (Path(current_root) / dirname).rmdir()
                absolute_root.rmdir()

        manifest_path = Path(out_dir) / MANIFEST_NAME
        if manifest_path.exists():
            manifest_path.unlink()

    def export_tree(
        self,
        out_dir: str,
        tree_roots: list[TreeNode],
        latest_by_uuid: dict[str, dict],
        model_name: str,
        preserve_existing_translations: bool = True,
    ) -> dict:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        existing_snapshots: dict[str, TreeFolderSnapshot] = {}
        if preserve_existing_translations and Path(out_dir).is_dir():
            existing_snapshots = self.scan(out_dir)["foldersByUuid"]
        self.remove_previous_export(out_dir)

        manifest = {
            "modelName": model_name,
            "sourceLang": self.source_lang,
            "targetLang": self.target_lang,
            "translationFile": TRANSLATION_FILENAME,
            "rootPaths": [],
            "nodes": {},
        }

        for root_index, root in enumerate(tree_roots, start=1):
            directory_name, _ = self._build_directory_name(root_index, root.entity_uuid, latest_by_uuid, model_name)
            manifest["rootPaths"].append(directory_name)
            self._write_node(
                node=root,
                parent_dir="",
                order_index=root_index,
                out_dir=out_dir,
                latest_by_uuid=latest_by_uuid,
                model_name=model_name,
                manifest=manifest,
                existing_snapshots=existing_snapshots,
            )

        (Path(out_dir) / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def scan(self, tree_dir: str) -> dict:
        node_dirs: dict[str, str] = {}
        translations: dict[tuple[str, str], str] = {}
        duplicate_uuids: list[tuple[str, str, str]] = []
        folders_by_uuid: dict[str, TreeFolderSnapshot] = {}

        for current_root, dirnames, filenames in os.walk(tree_dir):
            dirnames.sort()
            filenames.sort()
            if UUID_FILENAME not in filenames:
                continue

            uuid_path = Path(current_root) / UUID_FILENAME
            entity_uuid = uuid_path.read_text(encoding="utf-8").strip()
            if entity_uuid in node_dirs:
                duplicate_uuids.append((entity_uuid, node_dirs[entity_uuid], current_root))
                continue

            node_dirs[entity_uuid] = current_root
            translation_path = Path(current_root) / TRANSLATION_FILENAME
            folder_state = TreeFolderSnapshot(
                entity_uuid=entity_uuid,
                path=os.path.relpath(current_root, tree_dir),
                event_type=None,
                translation_path=translation_path if translation_path.exists() else None,
                modified_at=translation_path.stat().st_mtime if translation_path.exists() else uuid_path.stat().st_mtime,
                fields={},
            )

            if translation_path.exists():
                folder_state.fields = TranslationMarkdownDocument.parse(str(translation_path))
            else:
                folder_state.fields = self._scan_legacy_split_files(Path(current_root), filenames)

            for field, state in folder_state.fields.items():
                translations[(entity_uuid, field)] = state.target_text

            folders_by_uuid[entity_uuid] = folder_state

        return {
            "manifest": self.read_existing_manifest(tree_dir),
            "nodeDirs": node_dirs,
            "translations": translations,
            "duplicateUuids": duplicate_uuids,
            "foldersByUuid": folders_by_uuid,
        }

    def validate(self, tree_dir: str, po_entries: list) -> dict:
        scan_result = self.scan(tree_dir)
        manifest = scan_result["manifest"]
        node_dirs = scan_result["nodeDirs"]
        translations = scan_result["translations"]
        duplicate_uuids = scan_result["duplicateUuids"]

        errors: list[str] = []
        if duplicate_uuids:
            errors.extend(
                [
                    f"Duplicate UUID folder detected for {entity_uuid}: {first_path} and {second_path}"
                    for entity_uuid, first_path, second_path in duplicate_uuids
                ]
            )

        if manifest:
            expected_nodes = set(manifest.get("nodes", {}).keys())
            actual_nodes = set(node_dirs.keys())
            errors.extend([f"Missing UUID folder: {uuid}" for uuid in sorted(expected_nodes - actual_nodes)[:50]])
            errors.extend([f"Unexpected UUID folder: {uuid}" for uuid in sorted(actual_nodes - expected_nodes)[:50]])

        expected_fields_by_uuid: dict[str, set[str]] = {}
        for entry in po_entries:
            expected_fields_by_uuid.setdefault(entry.uuid, set()).add(entry.field)

        for entity_uuid, fields in sorted(expected_fields_by_uuid.items()):
            folder_path = node_dirs.get(entity_uuid)
            if folder_path is None:
                continue
            for field in sorted(fields):
                if (entity_uuid, field) not in translations:
                    translation_markdown_path = Path(folder_path) / TRANSLATION_FILENAME
                    if translation_markdown_path.exists():
                        errors.append(f"Missing translation block: {translation_markdown_path} -> {field}")
                    else:
                        errors.append(f"Missing translation file: {Path(folder_path) / f'{field}.{self.target_lang}.txt'}")

        return {
            **scan_result,
            "errors": errors,
        }

    def collect_status(self, tree_dir: str) -> dict:
        manifest = self.read_existing_manifest(tree_dir)
        if not manifest:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}")

        scan_result = self.scan(tree_dir)
        folders: list[TranslationStatusFolder] = []
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
            fields = tuple(node["fields"])
            if not fields:
                continue

            summary["translatableNodes"] += 1
            untranslated_fields: list[str] = []
            translated_fields: list[str] = []

            for field in fields:
                summary["totalFields"] += 1
                target_text = scan_result["translations"].get((entity_uuid, field))
                if target_text is None or not target_text.strip():
                    untranslated_fields.append(field)
                    summary["untranslatedFields"] += 1
                else:
                    translated_fields.append(field)
                    summary["translatedFields"] += 1

            if untranslated_fields:
                summary["pendingFolders"] += 1
            else:
                summary["completeFolders"] += 1

            folders.append(
                TranslationStatusFolder(
                    uuid=entity_uuid,
                    path=node["path"],
                    event_type=node["eventType"],
                    untranslated_fields=tuple(untranslated_fields),
                    translated_fields=tuple(translated_fields),
                )
            )

        return {"summary": summary, "folders": folders}

    def write_snapshot(self, snapshot: TreeFolderSnapshot) -> None:
        if snapshot.translation_path is None:
            return
        snapshot.translation_path.write_text(
            TranslationMarkdownDocument.render(
                entity_uuid=snapshot.entity_uuid,
                event_type=snapshot.event_type,
                fields=snapshot.fields,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
            ),
            encoding="utf-8",
        )

    def _write_node(
        self,
        node: TreeNode,
        parent_dir: str,
        order_index: int,
        out_dir: str,
        latest_by_uuid: dict[str, dict],
        model_name: str,
        manifest: dict,
        existing_snapshots: dict[str, TreeFolderSnapshot],
    ) -> None:
        directory_name, name_source = self._build_directory_name(order_index, node.entity_uuid, latest_by_uuid, model_name)
        relative_path = directory_name if not parent_dir else os.path.join(parent_dir, directory_name)
        absolute_path = Path(out_dir) / relative_path
        absolute_path.mkdir(parents=True, exist_ok=True)
        (absolute_path / UUID_FILENAME).write_text(node.entity_uuid, encoding="utf-8")

        fields = self._map_field_values(node)
        ordered_fields = TranslationMarkdownDocument.sort_fields(fields.keys())
        translation_fields: dict[str, TranslationFieldState] = {}
        for field in ordered_fields:
            state = fields[field]
            existing_snapshot = existing_snapshots.get(node.entity_uuid)
            preserved_target = ""
            if existing_snapshot and field in existing_snapshot.fields:
                preserved_target = existing_snapshot.fields[field].target_text
            translation_fields[field] = TranslationFieldState(
                source_text=state.source_text,
                target_text=preserved_target or state.target_text,
            )

        if translation_fields:
            (absolute_path / TRANSLATION_FILENAME).write_text(
                TranslationMarkdownDocument.render(
                    entity_uuid=node.entity_uuid,
                    event_type=node.event_type,
                    fields=translation_fields,
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                ),
                encoding="utf-8",
            )

        manifest["nodes"][node.entity_uuid] = {
            "path": relative_path,
            "fields": ordered_fields,
            "eventType": node.event_type,
            "nameSource": name_source,
        }

        for child_index, child in enumerate(node.children, start=1):
            self._write_node(
                node=child,
                parent_dir=relative_path,
                order_index=child_index,
                out_dir=out_dir,
                latest_by_uuid=latest_by_uuid,
                model_name=model_name,
                manifest=manifest,
                existing_snapshots=existing_snapshots,
            )

    @staticmethod
    def _map_field_values(node: TreeNode) -> dict[str, TranslationFieldState]:
        fields: dict[str, TranslationFieldState] = {}
        for ref in node.po_refs:
            if ref.field not in fields:
                fields[ref.field] = TranslationFieldState(source_text=ref.msgid, target_text=ref.msgstr)
        return fields

    @staticmethod
    def _sanitize_path_text(value: str) -> str:
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

    @staticmethod
    def _truncate_path_text(value: str, max_length: int = MAX_SEGMENT_TEXT_LENGTH) -> str:
        if len(value) <= max_length:
            return value
        shortened = value[: max_length - 3].rstrip()
        if " " in shortened:
            shortened = shortened.rsplit(" ", 1)[0]
        shortened = shortened.rstrip(" .-_")
        return (shortened or value[: max_length - 3]).rstrip() + "..."

    def _build_directory_name(
        self,
        order_index: int,
        entity_uuid: str,
        latest_by_uuid: dict[str, dict],
        model_name: str,
    ) -> tuple[str, dict]:
        raw_name, name_source = DswModelService.resolve_node_display_name(
            entity_uuid,
            latest_by_uuid,
            model_name=model_name,
        )
        safe_name = self._truncate_path_text(self._sanitize_path_text(raw_name))
        return f"{order_index:04d} {safe_name} [{entity_uuid[:8]}]", name_source

    def _scan_legacy_split_files(self, folder_path: Path, filenames: list[str]) -> dict[str, TranslationFieldState]:
        fields: dict[str, TranslationFieldState] = {}
        target_suffix = f".{self.target_lang}.txt"
        source_suffix = f".{self.source_lang}.txt"

        for filename in filenames:
            if not filename.endswith(target_suffix):
                continue
            field = filename[: -len(target_suffix)]
            source_text = ""
            source_path = folder_path / f"{field}{source_suffix}"
            target_path = folder_path / filename
            if source_path.exists():
                source_text = source_path.read_text(encoding="utf-8")
            fields[field] = TranslationFieldState(
                source_text=source_text,
                target_text=target_path.read_text(encoding="utf-8"),
            )
        return fields
