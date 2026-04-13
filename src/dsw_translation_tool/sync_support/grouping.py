"""Group-building helpers for shared-string synchronization."""

from __future__ import annotations

from collections import defaultdict

from ..data_models import PoBlock, PoReference


class SharedStringGroupBuilder:
    """Build shared-string groups from parsed PO blocks."""

    def build_groups(
        self,
        blocks: list[PoBlock],
        group_by: str,
    ) -> dict[tuple[object, ...], list[PoReference]]:
        """Build shared-string groups according to the selected strategy.

        Args:
            blocks: Parsed PO blocks used as the grouping source.
            group_by: Selected grouping strategy.

        Returns:
            Aggregated shared-string groups keyed by the derived group key.
        """

        groups: dict[tuple[object, ...], list[PoReference]] = defaultdict(list)
        for block in blocks:
            if not block.msgid:
                continue
            key = self.build_group_key(block, group_by=group_by)
            groups[key].extend(block.references)
        return groups

    @staticmethod
    def build_group_key(
        block: PoBlock,
        group_by: str,
    ) -> tuple[object, ...]:
        """Build the grouping key for one PO block.

        Args:
            block: PO block being grouped.
            group_by: Selected grouping strategy.

        Returns:
            Tuple key used for group aggregation.

        Raises:
            ValueError: If the grouping strategy is unsupported.
        """

        if group_by == "shared-block":
            return (
                "shared-block",
                tuple((reference.uuid, reference.field) for reference in block.references),
            )
        if group_by == "msgid":
            return ("msgid", block.msgid)
        if group_by == "msgid-field":
            fields = tuple(sorted({reference.field for reference in block.references}))
            return ("msgid-field", block.msgid, fields)
        raise ValueError(f"Unsupported grouping mode: {group_by}")

    @staticmethod
    def count_multi_reference_groups(
        groups: dict[tuple[object, ...], list[PoReference]],
    ) -> int:
        """Count groups that are large enough to participate in synchronization.

        Args:
            groups: Previously built shared-string groups.

        Returns:
            Number of groups containing at least two references.
        """

        return sum(1 for references in groups.values() if len(references) > 1)
