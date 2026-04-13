"""Regression tests for the typed `dsw-models` KM adapter."""

from __future__ import annotations

from pathlib import Path

from dsw_translation_tool.knowledge_model_service import KnowledgeModelService

MOVED_QUESTION_UUID = "ab4b3f39-dfab-45a5-9489-2d46ceacbb73"
MOVED_QUESTION_OLD_PARENT_UUID = "c4eda690-066f-495a-8c29-8e8a258ac487"
MOVED_QUESTION_NEW_PARENT_UUID = "b1df3c74-0b1f-4574-81c4-4cc2d780c1af"
MOVED_ENTITY_PARENT_EXPECTATIONS = {
    MOVED_QUESTION_UUID: MOVED_QUESTION_NEW_PARENT_UUID,
    "bb71dd81-e53a-4ee3-ab8e-bdd687329b91": "8c962e6f-17ee-4b22-8ebb-9f06f779e3b3",
    "a2b1fa38-792a-4628-9765-93476a38cffb": "761d20f2-d2ce-496b-8a91-a52ff0513e7b",
}


def assert_parent_uuid(
    latest_by_uuid: dict[str, dict[str, object]],
    entity_uuid: str,
    expected_parent_uuid: str,
) -> None:
    """Assert that one loaded entity has the expected final parent UUID.

    Args:
        latest_by_uuid: Loaded latest-entity mapping.
        entity_uuid: Entity UUID under verification.
        expected_parent_uuid: Expected final parent UUID.
    """

    assert latest_by_uuid[entity_uuid]["parentUuid"] == expected_parent_uuid


def test_model_loader_uses_move_event_target_uuid_for_moved_entities(
    model_path: Path,
) -> None:
    """Ensure move events update the final parent UUID to `targetUuid`.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = KnowledgeModelService.load_model(str(model_path))

    for entity_uuid, expected_parent_uuid in MOVED_ENTITY_PARENT_EXPECTATIONS.items():
        assert_parent_uuid(latest_by_uuid, entity_uuid, expected_parent_uuid)


def test_tree_builder_places_moved_question_under_the_new_parent(
    model_path: Path,
) -> None:
    """Ensure the built translation tree follows move-event target parents.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = KnowledgeModelService.load_model(str(model_path))

    relevant_uuids = KnowledgeModelService.build_ancestor_set(
        latest_by_uuid,
        {
            MOVED_QUESTION_UUID,
            MOVED_QUESTION_OLD_PARENT_UUID,
            MOVED_QUESTION_NEW_PARENT_UUID,
        },
    )
    _, nodes_map = KnowledgeModelService.build_tree(
        latest_by_uuid,
        relevant_uuids,
    )

    assert nodes_map[MOVED_QUESTION_UUID].parent_uuid == MOVED_QUESTION_NEW_PARENT_UUID
    assert any(
        child.entity_uuid == MOVED_QUESTION_UUID
        for child in nodes_map[MOVED_QUESTION_NEW_PARENT_UUID].children
    )
    assert all(
        child.entity_uuid != MOVED_QUESTION_UUID
        for child in nodes_map[MOVED_QUESTION_OLD_PARENT_UUID].children
    )
