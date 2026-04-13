"""Directory naming helpers for exported translation trees."""

from __future__ import annotations

import re
from typing import Any

from ..constants import MAX_SEGMENT_TEXT_LENGTH
from ..knowledge_model_service import KnowledgeModelService


class TreeDirectoryNamer:
    """Build stable, human-readable folder names for translation tree nodes."""

    @staticmethod
    def sanitize_path_text(value: str) -> str:
        """Remove path-unsafe characters from a directory name.

        Args:
            value: Raw display name candidate.

        Returns:
            Sanitized directory-name segment.
        """

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
    def truncate_path_text(
        value: str,
        max_length: int = MAX_SEGMENT_TEXT_LENGTH,
    ) -> str:
        """Truncate long directory names while keeping them readable.

        Args:
            value: Sanitized display text.
            max_length: Maximum path segment length.

        Returns:
            Truncated path segment.
        """

        if len(value) <= max_length:
            return value
        shortened = value[: max_length - 3].rstrip()
        if " " in shortened:
            shortened = shortened.rsplit(" ", 1)[0]
        shortened = shortened.rstrip(" .-_")
        fallback = shortened or value[: max_length - 3]
        return fallback.rstrip() + "..."

    def build_directory_name(
        self,
        order_index: int,
        entity_uuid: str,
        latest_by_uuid: dict[str, dict[str, Any]],
        model_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build the final folder name for one node.

        Args:
            order_index: 1-based child order among siblings.
            entity_uuid: UUID of the node being exported.
            latest_by_uuid: Latest merged KM entities keyed by UUID.
            model_name: Human-readable model name.

        Returns:
            Directory name and the resolved name-source metadata.
        """

        raw_name, name_source = KnowledgeModelService.resolve_node_display_name(
            entity_uuid,
            latest_by_uuid,
            model_name=model_name,
        )
        safe_name = self.truncate_path_text(self.sanitize_path_text(raw_name))
        return f"{order_index:04d} {safe_name} [{entity_uuid[:8]}]", name_source
