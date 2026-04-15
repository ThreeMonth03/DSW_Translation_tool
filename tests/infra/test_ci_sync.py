"""Tests for CI sync-and-commit orchestration helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dsw_translation_tool.ci_sync import CiSyncCommitConfig, run_ci_sync_commit


class RecordingRunner:
    """Record CI helper subprocess calls and return deterministic results."""

    def __init__(self, *, git_status_stdout: str = "") -> None:
        """Initialize the fake runner.

        Args:
            git_status_stdout: Stdout returned by `git status`.
        """

        self.git_status_stdout = git_status_stdout
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        args,
        *,
        cwd: Path,
        env=None,
    ) -> subprocess.CompletedProcess[str]:
        """Record one subprocess call and return a fake success result.

        Args:
            args: Command argument vector.
            cwd: Working directory for the command.
            env: Optional environment overrides.

        Returns:
            Fake completed-process result.
        """

        command = list(args)
        self.calls.append(
            {
                "args": command,
                "cwd": cwd,
                "env": dict(env) if env is not None else None,
            }
        )
        stdout = ""
        if command[:3] == ["git", "status", "--porcelain"]:
            stdout = self.git_status_stdout
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class ScriptedRunner:
    """Return scripted subprocess results in call order for CI sync tests."""

    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        """Initialize the scripted runner.

        Args:
            results: Completed-process results returned in order.
        """

        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        args,
        *,
        cwd: Path,
        env=None,
    ) -> subprocess.CompletedProcess[str]:
        """Record one subprocess call and return the next scripted result.

        Args:
            args: Command argument vector.
            cwd: Working directory for the command.
            env: Optional environment overrides.

        Returns:
            Next scripted completed-process result.
        """

        command = list(args)
        self.calls.append(
            {
                "args": command,
                "cwd": cwd,
                "env": dict(env) if env is not None else None,
            }
        )
        assert self.results, f"Unexpected command with no scripted result left: {command}"
        result = self.results.pop(0)
        return subprocess.CompletedProcess(command, result.returncode, result.stdout, result.stderr)


def build_ci_sync_config(
    workspace: Path,
    *,
    translation_root: str = "translation/zh_Hant",
    target_ref: str = "master",
    mode: str = "schedule",
) -> CiSyncCommitConfig:
    """Build a CI sync config rooted in one pytest workspace.

    Args:
        workspace: Per-test temporary workspace.
        translation_root: Relative translation root inside the host repo.
        target_ref: Target branch/ref for the push command.
        mode: CI trigger mode.

    Returns:
        Populated CI sync config.
    """

    host_repo = workspace / "host-repo"
    tooling_repo = workspace / "tooling-repo"
    translation_root_dir = host_repo / translation_root
    tree_dir = translation_root_dir / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tooling_repo / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (tooling_repo / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (tooling_repo / "files").mkdir(parents=True, exist_ok=True)
    (tooling_repo / "files" / "knowledge-models-common-dsw-knowledge-model-zh_Hant.po").write_text(
        "", encoding="utf-8"
    )
    return CiSyncCommitConfig(
        host_repo_path=host_repo,
        tooling_repo_path=tooling_repo,
        translation_root=translation_root,
        target_ref=target_ref,
        mode=mode,
    )


def test_ci_sync_commit_skips_commit_when_no_tracked_translation_changes(workspace) -> None:
    """Verify that sync/test still run when git reports no tracked diff.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(workspace)
    runner = RecordingRunner(git_status_stdout="")

    committed = run_ci_sync_commit(config, runner=runner)

    assert committed is False
    commands = [call["args"] for call in runner.calls]
    assert commands[0][1] == "src/sync_shared_strings.py"
    assert commands[1][:4] == [str(config.tooling_python_path), "-m", "pytest", "tests/translation"]
    assert commands[2][:3] == ["git", "status", "--porcelain"]
    assert all(command[:2] != ["git", "commit"] for command in commands)
    assert all(command[:2] != ["git", "push"] for command in commands)


def test_ci_sync_commit_stages_commits_and_pushes_tracked_translation_changes(
    workspace,
) -> None:
    """Verify that tracked sync changes become a commit pushed to the target ref.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(
        workspace,
        target_ref="feature/shared-sync",
        mode="pull_request",
    )
    runner = RecordingRunner(git_status_stdout=" M translation/zh_Hant/tree/shared_blocks.md\n")

    committed = run_ci_sync_commit(config, runner=runner)

    assert committed is True
    commands = [call["args"] for call in runner.calls]
    assert ["git", "config", "user.name", "github-actions[bot]"] in commands
    assert [
        "git",
        "config",
        "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com",
    ] in commands
    assert ["git", "add", "--", "translation/zh_Hant"] in commands
    assert ["git", "commit", "-m", "chore(sync): refresh translation artifacts"] in commands
    assert ["git", "push", "origin", "HEAD:feature/shared-sync"] in commands


def test_ci_sync_commit_uses_repo_root_layout_for_external_translation_repo(
    workspace,
) -> None:
    """Verify that `translation_root=.` targets tree/builds/reviews at repo root.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(workspace, translation_root=".")
    runner = RecordingRunner()

    committed = run_ci_sync_commit(config, runner=runner)

    assert committed is False
    sync_command = runner.calls[0]["args"]
    assert sync_command[:2] == [str(config.tooling_python_path), "src/sync_shared_strings.py"]
    assert "--tree-dir" in sync_command
    assert str(config.host_repo_dir / "tree") in sync_command
    assert str(config.host_repo_dir / "builds" / "final_translated.po") in sync_command
    assert str(config.host_repo_dir / "reviews" / "final_translated.diff") in sync_command
    assert str(config.host_repo_dir / "tree" / "shared_blocks.md") in sync_command
    assert str(config.original_po_path) in sync_command
    translation_test_env = runner.calls[1]["env"]
    assert translation_test_env is not None
    assert translation_test_env["DSW_COLLAB_OUTPUT_ROOT"] == str(config.host_repo_dir)


def test_ci_sync_commit_restores_broken_translation_markdown_from_origin_master(
    workspace,
) -> None:
    """Verify that CI restore retries sync after a broken `translation.md`.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(workspace)
    broken_file = config.tree_dir / "chapter" / "translation.md"
    runner = ScriptedRunner(
        [
            subprocess.CompletedProcess(
                ["sync"],
                1,
                stdout="",
                stderr=(
                    "Invalid translation file and no valid backup was available.\n"
                    f"File: {broken_file}\n"
                    "Reason: broken fence"
                ),
            ),
            subprocess.CompletedProcess(["restore"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["sync"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["pytest"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["git", "status"],
                0,
                stdout=" M translation/zh_Hant/tree/chapter/translation.md\n",
                stderr="",
            ),
            subprocess.CompletedProcess(["git", "config"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "config"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "add"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "commit"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "push"], 0, stdout="", stderr=""),
        ]
    )

    committed = run_ci_sync_commit(config, runner=runner)

    assert committed is True
    commands = [call["args"] for call in runner.calls]
    assert commands[1] == [
        "git",
        "restore",
        "--source",
        "origin/master",
        "--worktree",
        "--",
        "translation/zh_Hant/tree/chapter/translation.md",
    ]
    assert commands[2][1] == "src/sync_shared_strings.py"


def test_ci_sync_commit_restores_broken_shared_blocks_markdown_from_origin_master(
    workspace,
) -> None:
    """Verify that CI restore retries sync after a broken `shared_blocks.md`.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(workspace)
    broken_file = config.tree_dir / "shared_blocks.md"
    runner = ScriptedRunner(
        [
            subprocess.CompletedProcess(
                ["sync"],
                1,
                stdout="",
                stderr=(
                    "Invalid shared-block markdown and no valid backup was available.\n"
                    f"File: {broken_file}\n"
                    "Reason: malformed group"
                ),
            ),
            subprocess.CompletedProcess(["restore"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["sync"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["pytest"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "status"], 0, stdout="", stderr=""),
        ]
    )

    committed = run_ci_sync_commit(config, runner=runner)

    assert committed is False
    commands = [call["args"] for call in runner.calls]
    assert commands[1] == [
        "git",
        "restore",
        "--source",
        "origin/master",
        "--worktree",
        "--",
        "translation/zh_Hant/tree/shared_blocks.md",
    ]
    assert commands[2][1] == "src/sync_shared_strings.py"


def test_ci_sync_commit_does_not_commit_when_translation_tests_fail_after_restore(
    workspace,
) -> None:
    """Verify that CI still fails fast when validation fails after restore.

    Args:
        workspace: Per-test temporary workspace fixture.
    """

    config = build_ci_sync_config(workspace)
    broken_file = config.tree_dir / "chapter" / "translation.md"
    runner = ScriptedRunner(
        [
            subprocess.CompletedProcess(
                ["sync"],
                1,
                stdout="",
                stderr=(
                    "Invalid translation file and no valid backup was available.\n"
                    f"File: {broken_file}\n"
                    "Reason: broken fence"
                ),
            ),
            subprocess.CompletedProcess(["restore"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["sync"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["pytest"],
                1,
                stdout="",
                stderr="translation tests still failed",
            ),
        ]
    )

    try:
        run_ci_sync_commit(config, runner=runner)
    except RuntimeError as error:
        assert "translation tests still failed" in str(error)
    else:
        raise AssertionError("CI sync unexpectedly succeeded after translation test failure.")

    commands = [call["args"] for call in runner.calls]
    assert all(command[:2] != ["git", "add"] for command in commands)
    assert all(command[:2] != ["git", "commit"] for command in commands)
    assert all(command[:2] != ["git", "push"] for command in commands)
