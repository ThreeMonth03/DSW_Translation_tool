"""Markdown outline generation for collaboration trees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import MANIFEST_NAME, UUID_FILENAME
from .data_models import OutlineBuildResult, TreeFolderSnapshot
from .outline_support import OutlineNode, TranslationOutlineRenderer
from .tree import TranslationTreeRepository


class TranslationOutlineBuilder:
    """Build a markdown outline summarizing tree translation progress."""

    def __init__(self, tree_repository: TranslationTreeRepository):
        self.tree_repository = tree_repository
        self.renderer = TranslationOutlineRenderer()

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
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        scan_result = self.tree_repository.scan(tree_dir)
        nodes = self._build_outline_nodes(
            tree_dir=Path(tree_dir),
            manifest=manifest,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        markdown_text = self.renderer.render(
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
        manifest: dict[str, Any],
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> list[OutlineNode]:
        """Build the full outline-node tree from the manifest."""

        manifest_nodes = manifest.get("nodes", {})
        if not isinstance(manifest_nodes, dict):
            raise ValueError("Tree manifest nodes must be a dictionary")

        path_to_uuid = {
            str(node["path"]): entity_uuid for entity_uuid, node in manifest_nodes.items()
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

        built_nodes: dict[str, OutlineNode] = {}
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
            own_shared_fields = len(node.get("sharedFields", ()))
            built_nodes[entity_uuid] = OutlineNode(
                entity_uuid=entity_uuid,
                path=str(node["path"]),
                label=Path(str(node["path"])).name,
                event_type=node.get("eventType"),
                link_target=link_target,
                own_translated_fields=own_translated_fields,
                own_total_fields=own_total_fields,
                own_shared_fields=own_shared_fields,
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
        return sum(1 for state in snapshot.fields.values() if state.target_text.strip())

    def _accumulate_progress(self, node: OutlineNode) -> tuple[int, int]:
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
