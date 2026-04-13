"""Markdown outline generation for collaboration trees."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import MANIFEST_NAME, UUID_FILENAME
from .models import OutlineBuildResult, TreeFolderSnapshot
from .tree import TranslationTreeRepository


@dataclass
class _OutlineNode:
    """Outline node with aggregated translation progress."""

    entity_uuid: str
    path: str
    label: str
    event_type: str | None
    link_target: Path
    own_translated_fields: int
    own_total_fields: int
    subtree_translated_fields: int = 0
    subtree_total_fields: int = 0
    children: list["_OutlineNode"] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Return whether the node subtree is fully translated."""

        return self.subtree_translated_fields == self.subtree_total_fields

    @property
    def is_self_complete(self) -> bool:
        """Return whether this node itself is complete or non-translatable."""

        if self.own_total_fields == 0:
            return True
        return self.own_translated_fields == self.own_total_fields

    @property
    def checkbox(self) -> str:
        """Return the markdown checkbox marker."""

        return "x" if self.is_self_complete else " "

    @property
    def display_label(self) -> str:
        """Return the human-friendly node label without the UUID suffix."""

        return re.sub(r" \[[0-9a-f]{8}\]$", "", self.label)


class TranslationOutlineBuilder:
    """Build a markdown outline summarizing tree translation progress."""

    def __init__(self, tree_repository: TranslationTreeRepository):
        self.tree_repository = tree_repository

    def build(
        self,
        tree_dir: str,
        output_outline_path: str,
    ) -> OutlineBuildResult:
        """Build and persist a markdown outline for the translation tree.

        Args:
            tree_dir: Translation tree directory.
            output_outline_path: Destination markdown path.

        Returns:
            Outline build result containing the markdown text and output path.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(
                f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}"
            )

        scan_result = self.tree_repository.scan(tree_dir)
        nodes = self._build_outline_nodes(
            tree_dir=Path(tree_dir),
            output_outline=Path(output_outline_path),
            manifest=manifest,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        markdown_text = self._render_markdown(
            model_name=str(manifest.get("modelName") or "Translation Outline"),
            roots=nodes,
            output_outline=Path(output_outline_path),
        )

        output_file = Path(output_outline_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(markdown_text, encoding="utf-8")
        return OutlineBuildResult(
            markdown_text=markdown_text,
            output_outline=output_file,
        )

    def _build_outline_nodes(
        self,
        tree_dir: Path,
        output_outline: Path,
        manifest: dict[str, Any],
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> list[_OutlineNode]:
        """Build the full outline-node tree from the manifest."""

        manifest_nodes = manifest.get("nodes", {})
        if not isinstance(manifest_nodes, dict):
            raise ValueError("Tree manifest nodes must be a dictionary")

        path_to_uuid = {
            str(node["path"]): entity_uuid
            for entity_uuid, node in manifest_nodes.items()
        }
        children_by_uuid: dict[str, list[str]] = {entity_uuid: [] for entity_uuid in manifest_nodes}
        root_uuids: list[str] = []

        for entity_uuid, node in manifest_nodes.items():
            current_path = Path(str(node["path"]))
            parent_path = str(current_path.parent)
            if parent_path == ".":
                root_uuids.append(entity_uuid)
                continue
            parent_uuid = path_to_uuid.get(parent_path)
            if parent_uuid is None:
                root_uuids.append(entity_uuid)
                continue
            children_by_uuid[parent_uuid].append(entity_uuid)

        for child_uuids in children_by_uuid.values():
            child_uuids.sort(key=lambda uuid: str(manifest_nodes[uuid]["path"]))
        root_uuids.sort(key=lambda uuid: str(manifest_nodes[uuid]["path"]))

        built_nodes: dict[str, _OutlineNode] = {}
        for entity_uuid in manifest_nodes:
            node = manifest_nodes[entity_uuid]
            path = tree_dir / str(node["path"])
            snapshot = folders_by_uuid.get(entity_uuid)
            link_target = (
                snapshot.translation_path
                if snapshot is not None and snapshot.translation_path is not None
                else path / UUID_FILENAME
            )
            own_translated_fields = self._count_translated_fields(snapshot)
            own_total_fields = len(node.get("fields", ()))
            built_nodes[entity_uuid] = _OutlineNode(
                entity_uuid=entity_uuid,
                path=str(node["path"]),
                label=Path(str(node["path"])).name,
                event_type=node.get("eventType"),
                link_target=link_target,
                own_translated_fields=own_translated_fields,
                own_total_fields=own_total_fields,
            )

        for entity_uuid, child_uuids in children_by_uuid.items():
            built_nodes[entity_uuid].children = [
                built_nodes[child_uuid] for child_uuid in child_uuids
            ]

        roots = [built_nodes[entity_uuid] for entity_uuid in root_uuids]
        for root in roots:
            self._accumulate_progress(root)
        return roots

    @staticmethod
    def _count_translated_fields(snapshot: TreeFolderSnapshot | None) -> int:
        """Count non-empty translated fields in one snapshot."""

        if snapshot is None:
            return 0
        return sum(
            1
            for state in snapshot.fields.values()
            if state.target_text.strip()
        )

    def _accumulate_progress(self, node: _OutlineNode) -> tuple[int, int]:
        """Populate subtree totals recursively."""

        translated = node.own_translated_fields
        total = node.own_total_fields
        for child in node.children:
            child_translated, child_total = self._accumulate_progress(child)
            translated += child_translated
            total += child_total
        node.subtree_translated_fields = translated
        node.subtree_total_fields = total
        return translated, total

    def _render_markdown(
        self,
        model_name: str,
        roots: list[_OutlineNode],
        output_outline: Path,
    ) -> str:
        """Render the outline tree into markdown text."""

        lines = [f"### {model_name}", ""]
        for root in roots:
            self._render_node(
                node=root,
                depth=0,
                output_outline=output_outline,
                lines=lines,
            )
        return "\n".join(lines).rstrip() + "\n"

    def _render_node(
        self,
        node: _OutlineNode,
        depth: int,
        output_outline: Path,
        lines: list[str],
    ) -> None:
        """Render one outline node and its children."""

        indent = "    " * depth
        link_indent = f"{indent}  "
        relative_link = os.path.relpath(node.link_target, output_outline.parent)
        link_label = self._link_label(node.link_target)
        formatted_link = self._format_link_destination(relative_link)
        badge = self._event_type_badge(node.event_type)
        layer_badge = f"[layer {depth + 1}]"
        lines.append(f"{indent}- [{node.checkbox}] {layer_badge} {node.display_label}")
        lines.append("")
        lines.append(f"{link_indent}{badge} [{link_label}]({formatted_link})")
        if node.children:
            lines.append("")
        for child in node.children:
            self._render_node(
                node=child,
                depth=depth + 1,
                output_outline=output_outline,
                lines=lines,
            )

    @staticmethod
    def _event_type_badge(event_type: str | None) -> str:
        """Return a short badge for one DSW event type."""

        if not event_type:
            return "[?]"
        entity_name = event_type.removeprefix("Add").removeprefix("Edit")
        entity_name = entity_name.removeprefix("Delete").removeprefix("Move")
        entity_name = entity_name.removesuffix("Event")
        return {
            "KnowledgeModel": "[KM]",
            "Chapter": "[Ch]",
            "Question": "[Q]",
            "Answer": "[A]",
            "Choice": "[C]",
            "Reference": "[R]",
            "Expert": "[E]",
            "Integration": "[I]",
            "Tag": "[T]",
            "Metric": "[M]",
            "Phase": "[P]",
            "ResourceCollection": "[RC]",
            "ResourcePage": "[RP]",
        }.get(entity_name, f"[{entity_name}]")

    @staticmethod
    def _link_label(link_target: Path) -> str:
        """Return a short link label based on the destination file type."""

        if link_target.name == UUID_FILENAME:
            return "uuid"
        return "translation"

    @staticmethod
    def _format_link_destination(destination: str) -> str:
        """Wrap a markdown link destination so spaces and parentheses are safe."""

        escaped = destination.replace(">", "\\>")
        return f"<{escaped}>"
