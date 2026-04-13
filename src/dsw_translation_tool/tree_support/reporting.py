"""Validation and status-report helpers for translation trees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..constants import TRANSLATION_FILENAME
from ..data_models import (
    PoEntry,
    TranslationStatusFolder,
    TranslationStatusReport,
    TranslationStatusSummary,
    TreeScanResult,
    TreeValidationResult,
)


class TranslationTreeValidator:
    """Build validation results for scanned translation trees.

    Args:
        target_lang: Target language code used by legacy split-file paths.
    """

    def __init__(self, target_lang: str):
        self.target_lang = target_lang

    def build_result(
        self,
        scan_result: TreeScanResult,
        po_entries: list[PoEntry],
    ) -> TreeValidationResult:
        """Build a validation result for a scanned translation tree.

        Args:
            scan_result: Parsed scan result for the translation tree.
            po_entries: Flattened PO entries expected to exist in the tree.

        Returns:
            Validation result including discovered errors.
        """

        errors = self.build_errors(scan_result, po_entries)
        return TreeValidationResult(
            scan_result=scan_result,
            errors=tuple(errors),
        )

    def build_errors(
        self,
        scan_result: TreeScanResult,
        po_entries: list[PoEntry],
    ) -> list[str]:
        """Build validation errors for one scanned translation tree.

        Args:
            scan_result: Parsed scan result for the translation tree.
            po_entries: Flattened PO entries expected to exist in the tree.

        Returns:
            Validation error messages.
        """

        errors: list[str] = []
        errors.extend(self.build_duplicate_uuid_errors(scan_result.duplicate_uuids))
        errors.extend(
            self.build_manifest_node_errors(
                manifest=scan_result.manifest,
                node_dirs=scan_result.node_dirs,
            )
        )
        errors.extend(
            self.build_missing_field_errors(
                po_entries=po_entries,
                node_dirs=scan_result.node_dirs,
                translations=scan_result.translations,
            )
        )
        return errors

    @staticmethod
    def build_duplicate_uuid_errors(
        duplicate_uuids: tuple[tuple[str, str, str], ...],
    ) -> list[str]:
        """Create error messages for duplicate UUID folders.

        Args:
            duplicate_uuids: Duplicate UUID collisions found on disk.

        Returns:
            Duplicate-folder validation errors.
        """

        return [
            (f"Duplicate UUID folder detected for {entity_uuid}: {first_path} and {second_path}")
            for entity_uuid, first_path, second_path in duplicate_uuids
        ]

    @staticmethod
    def build_manifest_node_errors(
        manifest: dict[str, Any] | None,
        node_dirs: dict[str, str],
    ) -> list[str]:
        """Create error messages for manifest-to-disk UUID mismatches.

        Args:
            manifest: Parsed tree manifest, if available.
            node_dirs: Mapping from UUID to discovered node directory.

        Returns:
            Manifest mismatch validation errors.
        """

        if not manifest:
            return []

        expected_nodes = set(manifest.get("nodes", {}).keys())
        actual_nodes = set(node_dirs.keys())
        missing_nodes = sorted(expected_nodes - actual_nodes)[:50]
        unexpected_nodes = sorted(actual_nodes - expected_nodes)[:50]
        return [
            *(f"Missing UUID folder: {uuid}" for uuid in missing_nodes),
            *(f"Unexpected UUID folder: {uuid}" for uuid in unexpected_nodes),
        ]

    def build_missing_field_errors(
        self,
        po_entries: list[PoEntry],
        node_dirs: dict[str, str],
        translations: dict[tuple[str, str], str],
    ) -> list[str]:
        """Create error messages for missing translation fields.

        Args:
            po_entries: Flattened PO entries expected to exist in the tree.
            node_dirs: Mapping from UUID to discovered node directory.
            translations: Parsed translation mapping from the tree scan.

        Returns:
            Missing-field validation errors.
        """

        expected_fields_by_uuid: dict[str, set[str]] = {}
        for entry in po_entries:
            expected_fields_by_uuid.setdefault(entry.uuid, set()).add(entry.field)

        errors: list[str] = []
        for entity_uuid, fields in sorted(expected_fields_by_uuid.items()):
            folder_path = node_dirs.get(entity_uuid)
            if folder_path is None:
                continue
            for field in sorted(fields):
                if (entity_uuid, field) in translations:
                    continue
                translation_markdown_path = Path(folder_path) / TRANSLATION_FILENAME
                if translation_markdown_path.exists():
                    errors.append(
                        f"Missing translation block: {translation_markdown_path} -> {field}"
                    )
                    continue
                expected_path = Path(folder_path) / f"{field}.{self.target_lang}.txt"
                errors.append(f"Missing translation file: {expected_path}")
        return errors


class TranslationStatusCollector:
    """Build translation status reports from manifests and scan results."""

    def collect(
        self,
        manifest: dict[str, Any],
        scan_result: TreeScanResult,
    ) -> TranslationStatusReport:
        """Build a folder-by-folder translation status report.

        Args:
            manifest: Parsed tree manifest.
            scan_result: Parsed scan result for the tree.

        Returns:
            Folder-by-folder translation status report.
        """

        folders: list[TranslationStatusFolder] = []
        summary = TranslationStatusSummary(
            total_nodes=len(manifest.get("nodes", {})),
            translatable_nodes=0,
            complete_folders=0,
            pending_folders=0,
            total_fields=0,
            translated_fields=0,
            untranslated_fields=0,
        )

        mutable_summary = summary.to_dict()
        for entity_uuid, node in manifest.get("nodes", {}).items():
            folder_status = self.build_folder_status(
                entity_uuid=entity_uuid,
                node=node,
                translations=scan_result.translations,
                summary=mutable_summary,
            )
            if folder_status is not None:
                folders.append(folder_status)

        return TranslationStatusReport(
            summary=TranslationStatusSummary(
                total_nodes=mutable_summary["totalNodes"],
                translatable_nodes=mutable_summary["translatableNodes"],
                complete_folders=mutable_summary["completeFolders"],
                pending_folders=mutable_summary["pendingFolders"],
                total_fields=mutable_summary["totalFields"],
                translated_fields=mutable_summary["translatedFields"],
                untranslated_fields=mutable_summary["untranslatedFields"],
            ),
            folders=tuple(folders),
        )

    @staticmethod
    def build_folder_status(
        entity_uuid: str,
        node: dict[str, Any],
        translations: dict[tuple[str, str], str],
        summary: dict[str, int],
    ) -> TranslationStatusFolder | None:
        """Build one folder status entry and update summary counters.

        Args:
            entity_uuid: UUID of the folder being reported.
            node: Manifest node record for the folder.
            translations: Parsed translation mapping from the scan result.
            summary: Mutable summary counters in legacy camelCase form.

        Returns:
            Folder status entry, or `None` for non-translatable nodes.
        """

        fields = tuple(node["fields"])
        if not fields:
            return None

        summary["translatableNodes"] += 1
        untranslated_fields: list[str] = []
        translated_fields: list[str] = []

        for field in fields:
            summary["totalFields"] += 1
            target_text = translations.get((entity_uuid, field))
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

        return TranslationStatusFolder(
            uuid=entity_uuid,
            path=node["path"],
            event_type=node["eventType"],
            untranslated_fields=tuple(untranslated_fields),
            translated_fields=tuple(translated_fields),
        )
