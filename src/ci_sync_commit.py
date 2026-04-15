#!/usr/bin/env python3
"""Run CI sync, translation validation, and optional auto-commit."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_translation_tool import DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG
from dsw_translation_tool.ci_sync import (
    DEFAULT_SYNC_COMMIT_MESSAGE,
    CiSyncCommitConfig,
    CiSyncError,
    run_ci_sync_commit,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for CI sync automation.

    Returns:
        Configured parser instance.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Run shared-string sync plus translation validation, then create "
            "and push a commit when tracked translation artifacts changed."
        ),
    )
    parser.add_argument("--host-repo", required=True, help="Host repository checkout path.")
    parser.add_argument(
        "--tooling-repo",
        required=True,
        help="Tooling repository checkout path that contains the sync CLI and tests.",
    )
    parser.add_argument(
        "--translation-root",
        required=True,
        help="Relative path inside the host repository that contains tree/, builds/, and reviews/.",
    )
    parser.add_argument(
        "--target-ref",
        required=True,
        help="Branch/ref that should receive the pushed sync commit.",
    )
    parser.add_argument(
        "--mode",
        choices=("schedule", "pull_request"),
        required=True,
        help="Trigger mode for the current CI run.",
    )
    parser.add_argument("--source-lang", default=DEFAULT_SOURCE_LANG)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument("--commit-message", default=DEFAULT_SYNC_COMMIT_MESSAGE)
    return parser


def main() -> None:
    """Run the CI sync-and-commit CLI."""

    args = build_argument_parser().parse_args()
    config = CiSyncCommitConfig(
        host_repo_path=Path(args.host_repo),
        tooling_repo_path=Path(args.tooling_repo),
        translation_root=args.translation_root,
        target_ref=args.target_ref,
        mode=args.mode,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        commit_message=args.commit_message,
    )
    try:
        committed = run_ci_sync_commit(config)
    except CiSyncError as error:
        raise SystemExit(str(error)) from error

    if committed:
        print("[ci-sync] Sync changes were committed and pushed.")
        return
    print("[ci-sync] Sync completed without tracked translation changes.")


if __name__ == "__main__":
    main()
