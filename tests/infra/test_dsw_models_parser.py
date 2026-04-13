"""Regression tests for the typed `dsw-models` KM adapter."""

from __future__ import annotations

from pathlib import Path

from dsw_translation_tool.model import DswModelService


def test_model_loader_uses_move_event_target_uuid_for_moved_entities(
    model_path: Path,
) -> None:
    """Ensure move events update the final parent UUID to `targetUuid`.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = DswModelService.load_model(str(model_path))

    assert latest_by_uuid["ab4b3f39-dfab-45a5-9489-2d46ceacbb73"]["parentUuid"] == (
        "b1df3c74-0b1f-4574-81c4-4cc2d780c1af"
    )
    assert latest_by_uuid["bb71dd81-e53a-4ee3-ab8e-bdd687329b91"]["parentUuid"] == (
        "8c962e6f-17ee-4b22-8ebb-9f06f779e3b3"
    )
    assert latest_by_uuid["a2b1fa38-792a-4628-9765-93476a38cffb"]["parentUuid"] == (
        "761d20f2-d2ce-496b-8a91-a52ff0513e7b"
    )


def test_tree_builder_places_moved_question_under_the_new_parent(
    model_path: Path,
) -> None:
    """Ensure the built translation tree follows move-event target parents.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = DswModelService.load_model(str(model_path))
    moved_question_uuid = "ab4b3f39-dfab-45a5-9489-2d46ceacbb73"
    old_parent_uuid = "c4eda690-066f-495a-8c29-8e8a258ac487"
    new_parent_uuid = "b1df3c74-0b1f-4574-81c4-4cc2d780c1af"

    relevant_uuids = DswModelService.build_ancestor_set(
        latest_by_uuid,
        {
            moved_question_uuid,
            old_parent_uuid,
            new_parent_uuid,
        },
    )
    _, nodes_map = DswModelService.build_tree(latest_by_uuid, relevant_uuids)

    assert nodes_map[moved_question_uuid].parent_uuid == new_parent_uuid
    assert any(
        child.entity_uuid == moved_question_uuid
        for child in nodes_map[new_parent_uuid].children
    )
    assert all(
        child.entity_uuid != moved_question_uuid
        for child in nodes_map[old_parent_uuid].children
    )
