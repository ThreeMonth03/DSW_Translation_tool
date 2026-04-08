"""High-level translation workflow services."""

from __future__ import annotations

import json
from pathlib import Path

from .model import DswModelService
from .po import PoCatalogParser, PoCatalogWriter
from .tree import TranslationTreeRepository


class TranslationWorkflowService:
    """Coordinates PO, model, and tree operations."""

    def __init__(self, source_lang: str = "en", target_lang: str = "zh_Hant"):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.tree_repository = TranslationTreeRepository(
            source_lang=source_lang,
            target_lang=target_lang,
        )

    def build_tree_context(self, po_path: str, model_path: str) -> dict:
        po_entries = PoCatalogParser(po_path).parse_entries()
        latest_by_uuid, model_info = DswModelService.load_model(model_path)
        relevant_uuids = DswModelService.build_ancestor_set(
            latest_by_uuid,
            {entry.uuid for entry in po_entries},
        )
        tree_roots, nodes_map = DswModelService.build_tree(latest_by_uuid, relevant_uuids)
        DswModelService.annotate_tree_nodes(po_entries, nodes_map)
        report = DswModelService.validate_po_entries(po_entries, latest_by_uuid)
        return {
            "report": report,
            "model": {
                "id": model_info.id,
                "kmId": model_info.km_id,
                "name": model_info.name,
            },
            "roots": tree_roots,
            "entries": po_entries,
            "latestByUuid": latest_by_uuid,
        }

    def export_tree(
        self,
        po_path: str,
        model_path: str,
        out_dir: str,
        preserve_existing_translations: bool = True,
    ) -> dict:
        context = self.build_tree_context(po_path=po_path, model_path=model_path)
        manifest = self.tree_repository.export_tree(
            out_dir=out_dir,
            tree_roots=context["roots"],
            latest_by_uuid=context["latestByUuid"],
            model_name=context["model"]["name"],
            preserve_existing_translations=preserve_existing_translations,
        )
        return {
            **context,
            "manifest": manifest,
        }

    def validate_po_against_model(self, po_path: str, model_path: str) -> dict:
        po_entries = PoCatalogParser(po_path).parse_entries()
        latest_by_uuid, _ = DswModelService.load_model(model_path)
        return DswModelService.validate_po_entries(po_entries, latest_by_uuid)

    def write_report(self, report: dict, report_path: str) -> None:
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_po_from_tree(self, tree_dir: str, original_po_path: str, out_po_path: str) -> dict:
        po_entries = PoCatalogParser(original_po_path).parse_entries()
        tree_validation = self.tree_repository.validate(tree_dir, po_entries)
        if tree_validation["errors"]:
            preview = "\n".join(tree_validation["errors"][:50])
            raise ValueError(f"Translation tree validation failed:\n{preview}")

        po_content = PoCatalogWriter.rewrite_translations(
            original_po_path,
            tree_validation["translations"],
        )
        out_po_file = Path(out_po_path)
        out_po_file.parent.mkdir(parents=True, exist_ok=True)
        out_po_file.write_text(po_content, encoding="utf-8")

        return {
            "poContent": po_content,
            "translations": tree_validation["translations"],
            "validation": tree_validation,
            "outPo": str(out_po_file),
        }

    def collect_status(self, tree_dir: str) -> dict:
        return self.tree_repository.collect_status(tree_dir)
