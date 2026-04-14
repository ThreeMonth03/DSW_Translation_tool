"""Markdown rendering helpers for collaboration-tree outlines."""

from __future__ import annotations

import os
from pathlib import Path

from ..constants import UUID_FILENAME
from .models import OutlineNode


class TranslationOutlineRenderer:
    """Render outline nodes into markdown text."""

    def render(
        self,
        model_name: str,
        roots: list[OutlineNode],
        output_outline: Path,
    ) -> str:
        """Render the outline tree into markdown text.

        Args:
            model_name: Display name shown at the top of the outline.
            roots: Root outline nodes to render.
            output_outline: Output markdown path used to compute relative links.

        Returns:
            Rendered outline markdown.
        """

        lines = [f"### {model_name}", ""]
        for root in roots:
            self.render_node(
                node=root,
                depth=0,
                output_outline=output_outline,
                lines=lines,
            )
        return "\n".join(lines).rstrip() + "\n"

    def render_node(
        self,
        node: OutlineNode,
        depth: int,
        output_outline: Path,
        lines: list[str],
    ) -> None:
        """Render one outline node and its children.

        Args:
            node: Outline node being rendered.
            depth: Current tree depth used for indentation.
            output_outline: Output markdown path used to compute relative links.
            lines: Mutable markdown line buffer.
        """

        indent = "    " * depth
        link_indent = f"{indent}  "
        relative_link = os.path.relpath(node.link_target, output_outline.parent)
        link_label = self.link_label(node.link_target)
        formatted_link = self.format_link_destination(relative_link)
        badge = self.event_type_badge(node.event_type)
        layer_badge = f"[layer {depth + 1}]"
        shared_badge = " [shared]" if node.is_shared else ""
        lines.append(
            f"{indent}- [{node.checkbox}] {layer_badge}{shared_badge} {node.display_label}"
        )
        lines.append("")
        lines.append(f"{link_indent}{badge} [{link_label}]({formatted_link})")
        if node.children:
            lines.append("")
        for child in node.children:
            self.render_node(
                node=child,
                depth=depth + 1,
                output_outline=output_outline,
                lines=lines,
            )

    @staticmethod
    def event_type_badge(event_type: str | None) -> str:
        """Return a short badge for one DSW event type.

        Args:
            event_type: DSW event type associated with one node.

        Returns:
            Short badge used by the outline markdown.
        """

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
    def link_label(link_target: Path) -> str:
        """Return a short link label based on the destination file type.

        Args:
            link_target: Destination file linked from the outline.

        Returns:
            Short markdown link label.
        """

        if link_target.name == UUID_FILENAME:
            return "uuid"
        return "translation"

    @staticmethod
    def format_link_destination(destination: str) -> str:
        """Wrap a markdown destination so spaces and parentheses are safe.

        Args:
            destination: Relative link destination to format.

        Returns:
            Markdown-safe destination string.
        """

        escaped = destination.replace(">", "\\>")
        return f"<{escaped}>"
