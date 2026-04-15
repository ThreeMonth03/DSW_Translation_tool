"""Shared pytest fixtures for translation workflow tests."""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

COLLAB_OUTPUT_ROOT_ENV = "DSW_COLLAB_OUTPUT_ROOT"


def sanitize_test_name(name: str) -> str:
    """Convert a pytest node name into a safe directory name.

    Args:
        name: Raw pytest node name.

    Returns:
        A filesystem-safe directory segment.
    """

    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return sanitized or "test-workspace"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root directory.

    Returns:
        Repository root path.
    """

    return REPO_ROOT


@pytest.fixture(scope="session")
def po_path(repo_root: Path) -> Path:
    """Return the fixture PO file path.

    Args:
        repo_root: Repository root fixture.

    Returns:
        Absolute PO file path used by tests.
    """

    return repo_root / "files" / "knowledge-models-common-dsw-knowledge-model-zh_Hant.po"


@pytest.fixture(scope="session")
def model_path(repo_root: Path) -> Path:
    """Return the fixture KM file path.

    Args:
        repo_root: Repository root fixture.

    Returns:
        Absolute KM file path used by tests.
    """

    return repo_root / "files" / "dsw_root_2.7.0.km"


@pytest.fixture(scope="session")
def collaboration_output_root(repo_root: Path) -> Path:
    """Return the collaboration output root used by translation tests.

    Args:
        repo_root: Repository root fixture.

    Returns:
        Absolute collaboration output root containing `tree/`, `builds/`, and
        `reviews/`.
    """

    from dsw_translation_tool import DEFAULT_LAYOUT

    configured_root = os.environ.get(COLLAB_OUTPUT_ROOT_ENV)
    if configured_root:
        output_root = Path(configured_root)
        if not output_root.is_absolute():
            output_root = (repo_root / output_root).resolve()
        return output_root

    return repo_root / DEFAULT_LAYOUT.output_root


@pytest.fixture(scope="session")
def collaboration_tree_dir(collaboration_output_root: Path) -> Path:
    """Return the collaboration tree directory used by translation tests.

    Args:
        collaboration_output_root: Collaboration output root fixture.

    Returns:
        Absolute collaboration tree path.
    """

    return collaboration_output_root / "tree"


@pytest.fixture(scope="session")
def collaboration_final_po_path(collaboration_output_root: Path) -> Path:
    """Return the checked-in generated PO path for collaboration output.

    Args:
        collaboration_output_root: Collaboration output root fixture.

    Returns:
        Absolute generated PO path to validate.
    """

    return collaboration_output_root / "builds" / "final_translated.po"


@pytest.fixture(scope="session")
def collaboration_diff_path(collaboration_output_root: Path) -> Path:
    """Return the checked-in generated diff path for collaboration output.

    Args:
        collaboration_output_root: Collaboration output root fixture.

    Returns:
        Absolute generated diff path to validate.
    """

    return collaboration_output_root / "reviews" / "final_translated.diff"


@pytest.fixture(scope="session")
def collaboration_outline_path(collaboration_tree_dir: Path) -> Path:
    """Return the checked-in outline markdown path for collaboration output.

    Args:
        collaboration_tree_dir: Collaboration tree directory fixture.

    Returns:
        Absolute outline markdown path to validate.
    """

    return collaboration_tree_dir / "outline.md"


@pytest.fixture(scope="session")
def collaboration_shared_blocks_dir(collaboration_tree_dir: Path) -> Path:
    """Return the checked-in canonical shared-block directory path.

    Args:
        collaboration_tree_dir: Collaboration tree directory fixture.

    Returns:
        Absolute shared-block directory path to validate.
    """

    return collaboration_tree_dir / "shared_blocks"


@pytest.fixture(scope="session")
def collaboration_shared_blocks_outline_path(collaboration_tree_dir: Path) -> Path:
    """Return the checked-in shared-block outline markdown path.

    Args:
        collaboration_tree_dir: Collaboration tree directory fixture.

    Returns:
        Absolute shared-block outline markdown path to validate.
    """

    return collaboration_tree_dir / "shared_blocks_outline.md"


@pytest.fixture(scope="session")
def workflow() -> Any:
    """Return the workflow service under test.

    Returns:
        Configured workflow service instance.
    """

    from dsw_translation_tool import TranslationWorkflowService

    return TranslationWorkflowService(source_lang="en", target_lang="zh_Hant")


@pytest.fixture(scope="session")
def po_parser(po_path: Path) -> Any:
    """Return a parser for the fixture PO file.

    Args:
        po_path: Fixture PO file path.

    Returns:
        PO catalog parser for the fixture file.
    """

    from dsw_translation_tool.po import PoCatalogParser

    return PoCatalogParser(str(po_path))


@pytest.fixture(scope="session")
def po_blocks(po_parser: Any):
    """Return parsed PO blocks for the fixture PO file.

    Args:
        po_parser: Fixture PO parser.

    Returns:
        Parsed PO blocks grouped by message block.
    """

    return po_parser.parse_blocks()


@pytest.fixture(scope="session")
def po_entries(po_parser: Any):
    """Return flattened PO entries for the fixture PO file.

    Args:
        po_parser: Fixture PO parser.

    Returns:
        Flattened `(uuid, field)` PO entries.
    """

    return po_parser.parse_entries()


@pytest.fixture(scope="session", autouse=True)
def managed_tmp_root(repo_root: Path) -> Iterator[Path]:
    """Create and clean the repository-local `.tmp` test workspace.

    Args:
        repo_root: Repository root fixture.

    Yields:
        Root path for repository-local test workspaces.
    """

    temp_root = repo_root / ".tmp"
    shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    yield temp_root
    shutil.rmtree(temp_root, ignore_errors=True)


@pytest.fixture()
def workspace(managed_tmp_root: Path, request: pytest.FixtureRequest) -> Iterator[Path]:
    """Create one per-test workspace under the managed `.tmp` directory.

    Args:
        managed_tmp_root: Shared temporary workspace root.
        request: Pytest request object for the current test.

    Yields:
        Fresh per-test workspace path.
    """

    workspace_dir = managed_tmp_root / sanitize_test_name(request.node.name)
    shutil.rmtree(workspace_dir, ignore_errors=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    yield workspace_dir
    shutil.rmtree(workspace_dir, ignore_errors=True)
