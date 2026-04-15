"""CI helpers for syncing translation artifacts and committing updates."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .constants import SHARED_BLOCKS_FILENAME, TRANSLATION_FILENAME
from .layout import DEFAULT_PO_PATH, DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG

DEFAULT_SYNC_COMMIT_MESSAGE = "chore(sync): refresh translation artifacts"
GITHUB_BOT_NAME = "github-actions[bot]"
GITHUB_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
RESTORABLE_SYNC_FILENAMES = frozenset({TRANSLATION_FILENAME, SHARED_BLOCKS_FILENAME})
SYNC_FILE_LINE_RE = re.compile(r"^File: (?P<path>.+)$", re.MULTILINE)


class CommandRunner(Protocol):
    """Protocol for subprocess execution used by the CI sync helper."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one command and return the completed-process result.

        Args:
            args: Command argument vector.
            cwd: Working directory for the command.
            env: Optional environment overrides.

        Returns:
            Completed process result.
        """


class CiSyncError(RuntimeError):
    """Raised when CI sync-and-commit automation cannot complete."""


@dataclass(frozen=True)
class CiSyncCommitConfig:
    """Describe one CI sync-and-commit operation.

    Args:
        host_repo_path: Repository whose translation tree should be updated.
        tooling_repo_path: Repository that contains the sync CLI and tests.
        translation_root: Relative path inside the host repository that contains
            `tree/`, `builds/`, and `reviews/`.
        target_ref: Branch/ref that should receive the push.
        mode: Trigger mode, either `schedule` or `pull_request`.
        source_lang: Source language code used by the sync CLI.
        target_lang: Target language code used by the sync CLI.
        commit_message: Commit message used when sync changes are detected.
    """

    host_repo_path: Path
    tooling_repo_path: Path
    translation_root: str
    target_ref: str
    mode: str
    source_lang: str = DEFAULT_SOURCE_LANG
    target_lang: str = DEFAULT_TARGET_LANG
    commit_message: str = DEFAULT_SYNC_COMMIT_MESSAGE

    @property
    def host_repo_dir(self) -> Path:
        """Return the absolute host repository path."""

        return self.host_repo_path.resolve()

    @property
    def tooling_repo_dir(self) -> Path:
        """Return the absolute tooling repository path."""

        return self.tooling_repo_path.resolve()

    @property
    def translation_root_path(self) -> Path:
        """Return the translation root as a relative path object."""

        return Path(self.translation_root)

    @property
    def translation_root_arg(self) -> str:
        """Return the normalized pathspec used by git commands."""

        normalized = self.translation_root_path.as_posix()
        return normalized or "."

    @property
    def translation_root_dir(self) -> Path:
        """Return the absolute translation root inside the host repository."""

        return (self.host_repo_dir / self.translation_root_path).resolve()

    @property
    def tree_dir(self) -> Path:
        """Return the absolute translation tree directory."""

        return self.translation_root_dir / "tree"

    @property
    def final_po_path(self) -> Path:
        """Return the generated PO output path."""

        return self.translation_root_dir / "builds" / "final_translated.po"

    @property
    def diff_path(self) -> Path:
        """Return the generated review diff path."""

        return self.translation_root_dir / "reviews" / "final_translated.diff"

    @property
    def outline_path(self) -> Path:
        """Return the generated outline markdown path."""

        return self.tree_dir / "outline.md"

    @property
    def shared_blocks_path(self) -> Path:
        """Return the canonical shared-block markdown path."""

        return self.tree_dir / "shared_blocks.md"

    @property
    def shared_blocks_outline_path(self) -> Path:
        """Return the compact shared-block outline markdown path."""

        return self.tree_dir / "shared_blocks_outline.md"

    @property
    def tooling_python_path(self) -> Path:
        """Return the tooling virtualenv Python path."""

        return self.tooling_repo_dir / ".venv" / "bin" / "python"

    @property
    def original_po_path(self) -> Path:
        """Return the canonical original PO path inside the tooling repository."""

        return self.tooling_repo_dir / DEFAULT_PO_PATH

    def validate(self) -> None:
        """Validate that the requested sync operation can run locally.

        Raises:
            CiSyncError: If the configuration points to missing or unsupported
                paths.
        """

        if self.mode not in {"schedule", "pull_request"}:
            raise CiSyncError(
                "Unsupported CI sync mode. Expected 'schedule' or "
                f"'pull_request', got {self.mode!r}."
            )
        if self.translation_root_path.is_absolute():
            raise CiSyncError("Translation root must be relative to the host repository.")
        if not self.host_repo_dir.is_dir():
            raise CiSyncError(f"Host repository does not exist: {self.host_repo_dir}")
        if not self.tooling_repo_dir.is_dir():
            raise CiSyncError(f"Tooling repository does not exist: {self.tooling_repo_dir}")
        if not self.translation_root_dir.is_dir():
            raise CiSyncError(
                "Translation root does not exist inside the host repository: "
                f"{self.translation_root_dir}"
            )
        if not self.tree_dir.is_dir():
            raise CiSyncError(f"Missing translation tree directory: {self.tree_dir}")
        if not self.tooling_python_path.exists():
            raise CiSyncError(
                "Missing tooling virtualenv Python. Run `make install-dev` first: "
                f"{self.tooling_python_path}"
            )
        if not self.original_po_path.exists():
            raise CiSyncError(f"Missing original PO file: {self.original_po_path}")


def default_command_runner(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess command for CI sync orchestration.

    Args:
        args: Command argument vector.
        cwd: Working directory for the command.
        env: Optional environment overrides.

    Returns:
        Completed process result.
    """

    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_ci_sync_commit(
    config: CiSyncCommitConfig,
    *,
    runner: CommandRunner = default_command_runner,
) -> bool:
    """Run sync, translation validation, and optional commit/push.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner used by tests and production code.

    Returns:
        `True` when a commit was created and pushed, otherwise `False`.

    Raises:
        CiSyncError: If sync, validation, commit, or push fails.
    """

    config.validate()
    print(f"[ci-sync] Mode: {config.mode}")
    print(f"[ci-sync] Host repo: {config.host_repo_dir}")
    print(f"[ci-sync] Translation root: {config.translation_root_arg}")

    _run_sync_with_origin_restore(config, runner)
    _run_checked(
        runner,
        _build_translation_test_command(config),
        cwd=config.tooling_repo_dir,
        env={"DSW_COLLAB_OUTPUT_ROOT": str(config.translation_root_dir)},
        description="run translation tests",
    )

    if not _translation_root_has_tracked_changes(config, runner):
        print("[ci-sync] No tracked translation changes detected after sync.")
        return False

    _configure_git_identity(config, runner)
    _run_checked(
        runner,
        ["git", "add", "--", config.translation_root_arg],
        cwd=config.host_repo_dir,
        description="stage translation changes",
    )
    _run_checked(
        runner,
        ["git", "commit", "-m", config.commit_message],
        cwd=config.host_repo_dir,
        description="create sync commit",
    )
    _run_checked(
        runner,
        ["git", "push", "origin", f"HEAD:{config.target_ref}"],
        cwd=config.host_repo_dir,
        description="push sync commit",
    )
    print(f"[ci-sync] Pushed sync commit to {config.target_ref}.")
    return True


def _run_sync_with_origin_restore(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> None:
    """Run sync once, optionally restoring one broken source file from master.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.

    Raises:
        CiSyncError: If sync still fails after the restore attempt or if the
            failure is not eligible for aggressive restore.
    """

    try:
        _run_checked(
            runner,
            _build_sync_command(config),
            cwd=config.tooling_repo_dir,
            description="sync translation artifacts",
        )
        return
    except CiSyncError as error:
        restore_path = _extract_origin_restore_candidate(str(error), config)
        if restore_path is None:
            raise

    print(
        "[ci-sync] WARNING: restoring malformed translation source from "
        f"origin/master: {restore_path}"
    )
    _restore_file_from_origin_master(config, runner, restore_path)
    _run_checked(
        runner,
        _build_sync_command(config),
        cwd=config.tooling_repo_dir,
        description="re-run sync translation artifacts after origin/master restore",
    )


def _build_sync_command(config: CiSyncCommitConfig) -> list[str]:
    """Build the explicit sync CLI command for one CI operation.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command argument vector.
    """

    return [
        str(config.tooling_python_path),
        "src/sync_shared_strings.py",
        "--tree-dir",
        str(config.tree_dir),
        "--original-po",
        str(config.original_po_path),
        "--out-po",
        str(config.final_po_path),
        "--diff-out",
        str(config.diff_path),
        "--outline-out",
        str(config.outline_path),
        "--shared-blocks-out",
        str(config.shared_blocks_path),
        "--shared-blocks-outline-out",
        str(config.shared_blocks_outline_path),
        "--source-lang",
        config.source_lang,
        "--target-lang",
        config.target_lang,
        "--group-by",
        "shared-block",
    ]


def _build_translation_test_command(config: CiSyncCommitConfig) -> list[str]:
    """Build the explicit translation-test command for one CI operation.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command argument vector.
    """

    return [
        str(config.tooling_python_path),
        "-m",
        "pytest",
        "tests/translation",
    ]


def _translation_root_has_tracked_changes(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> bool:
    """Return whether tracked files changed under the translation root.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.

    Returns:
        `True` when tracked files changed under the translation root.

    Raises:
        CiSyncError: If git status fails.
    """

    result = _run_checked(
        runner,
        ["git", "status", "--porcelain", "--untracked-files=no", "--", config.translation_root_arg],
        cwd=config.host_repo_dir,
        description="inspect tracked translation changes",
    )
    return bool(result.stdout.strip())


def _configure_git_identity(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> None:
    """Configure the GitHub Actions bot identity inside the host repository.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.

    Raises:
        CiSyncError: If git config fails.
    """

    _run_checked(
        runner,
        ["git", "config", "user.name", GITHUB_BOT_NAME],
        cwd=config.host_repo_dir,
        description="configure git bot name",
    )
    _run_checked(
        runner,
        ["git", "config", "user.email", GITHUB_BOT_EMAIL],
        cwd=config.host_repo_dir,
        description="configure git bot email",
    )


def _extract_origin_restore_candidate(
    error_message: str,
    config: CiSyncCommitConfig,
) -> Path | None:
    """Return a restorable source file path from one sync failure message.

    Args:
        error_message: Raised sync failure message.
        config: Sync-and-commit configuration.

    Returns:
        Absolute path to a restorable source file, or `None` when the failure
        should not trigger aggressive restore.
    """

    for match in SYNC_FILE_LINE_RE.finditer(error_message):
        candidate_path = Path(match.group("path").strip()).resolve()
        if candidate_path.name not in RESTORABLE_SYNC_FILENAMES:
            continue
        if not _is_relative_to(candidate_path, config.host_repo_dir):
            continue
        if not _is_relative_to(candidate_path, config.translation_root_dir):
            continue
        return candidate_path
    return None


def _restore_file_from_origin_master(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
    file_path: Path,
) -> None:
    """Restore one tracked translation source file from `origin/master`.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.
        file_path: Absolute host-repository file path to restore.

    Raises:
        CiSyncError: If the git restore command fails.
    """

    relative_path = file_path.relative_to(config.host_repo_dir).as_posix()
    _run_checked(
        runner,
        ["git", "restore", "--source", "origin/master", "--worktree", "--", relative_path],
        cwd=config.host_repo_dir,
        description=f"restore {relative_path} from origin/master",
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    """Return whether one path is located under the given root.

    Args:
        path: Candidate absolute path.
        root: Candidate absolute root.

    Returns:
        `True` when `path` is inside `root`, otherwise `False`.
    """

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _run_checked(
    runner: CommandRunner,
    args: Sequence[str],
    *,
    cwd: Path,
    description: str,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one command and raise a readable error on failure.

    Args:
        runner: Injectable subprocess runner.
        args: Command argument vector.
        cwd: Working directory for the command.
        description: Human-readable operation description.
        env: Optional environment overrides.

    Returns:
        Completed process result.

    Raises:
        CiSyncError: If the command exits with a non-zero status.
    """

    result = runner(args, cwd=cwd, env=env)
    if result.returncode == 0:
        return result

    output = (result.stderr or result.stdout or "").strip()
    command = " ".join(str(part) for part in args)
    if output:
        raise CiSyncError(f"Failed to {description}: {command}\n{output}")
    raise CiSyncError(f"Failed to {description}: {command}")
