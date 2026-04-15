"""Tests for `sync-watch` mode selection and watchdog behavior."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import sync_shared_strings
from dsw_translation_tool.sync_support.watch import (
    RecentWriteRegistry,
    SyncWatchService,
    SyncWatchSettings,
    TranslationTreeWatchFilter,
    WatchdogUnavailableError,
)


class FakeTimeModule:
    """Provide deterministic time helpers for watch-mode tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        """Return the current fake monotonic time."""

        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance fake time when a test needs explicit sleeping."""

        self.now += seconds

    @staticmethod
    def strftime(_: str) -> str:
        """Return a stable timestamp string for sync logs."""

        return "2026-04-15 12:34:56"


class FakeObserver:
    """Simple observer stub used by watch-mode tests."""

    def __init__(
        self,
        *,
        on_start=None,
        alive_sequence: list[bool] | None = None,
    ) -> None:
        self.on_start = on_start
        self.alive_sequence = list(alive_sequence or [True])
        self.started = False
        self.stopped = False
        self.joined = False

    def start(self) -> None:
        """Start the fake observer and emit startup events when requested."""

        self.started = True
        if self.on_start is not None:
            self.on_start()

    def stop(self) -> None:
        """Stop the fake observer."""

        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        """Record that the fake observer was joined."""

        _ = timeout
        self.joined = True

    def is_alive(self) -> bool:
        """Return the next configured liveness state."""

        if len(self.alive_sequence) > 1:
            return self.alive_sequence.pop(0)
        return self.alive_sequence[0]


def build_watch_args() -> Namespace:
    """Build a minimal watch-mode CLI namespace for `sync_shared_strings.main`.

    Returns:
        Populated namespace compatible with the CLI main entrypoint.
    """

    return Namespace(
        tree_dir="unused-tree",
        original_po="unused.po",
        out_po="unused-final.po",
        diff_out="unused.diff",
        outline_out="unused-outline.md",
        shared_blocks_dir_out="unused-shared-dir",
        shared_blocks_outline_out="unused-shared-outline.md",
        source_lang="en",
        target_lang="zh_Hant",
        group_by="shared-block",
        watch=True,
    )


def test_sync_watch_main_uses_watch_service(monkeypatch) -> None:
    """Verify that the CLI forwards the selected watch mode to the service."""

    args = build_watch_args()
    service_calls: list[str] = []

    class _Parser:
        """Minimal parser stub for main-entrypoint testing."""

        def parse_args(self) -> Namespace:
            """Return the configured watch-mode namespace."""

            return args

    class _Service:
        """Minimal watch-service stub that records the selected mode."""

        def run(self) -> None:
            """Record the watch-service invocation and stop the CLI."""

            service_calls.append("run")
            raise KeyboardInterrupt

    monkeypatch.setattr(sync_shared_strings, "build_argument_parser", lambda: _Parser())
    monkeypatch.setattr(sync_shared_strings, "build_watch_service", lambda _: _Service())

    sync_shared_strings.main()

    assert service_calls == ["run"]


def test_sync_watch_main_exits_when_watchdog_cannot_start(monkeypatch) -> None:
    """Verify that watchdog startup errors exit with a clear message."""

    args = build_watch_args()

    class _Parser:
        """Minimal parser stub for watchdog error propagation."""

        def parse_args(self) -> Namespace:
            """Return the configured watchdog-mode namespace."""

            return args

    class _Service:
        """Service stub that simulates a watchdog startup failure."""

        def run(self) -> None:
            """Raise the expected watchdog startup error."""

            raise ValueError("watchdog observer could not start")

    monkeypatch.setattr(sync_shared_strings, "build_argument_parser", lambda: _Parser())
    monkeypatch.setattr(sync_shared_strings, "build_watch_service", lambda _: _Service())

    with pytest.raises(SystemExit, match="watchdog observer could not start"):
        sync_shared_strings.main()


def test_sync_watch_service_uses_watchdog_when_available(capsys) -> None:
    """Verify that watch mode uses watchdog when available."""

    fake_time = FakeTimeModule()
    sync_calls: list[int] = []

    def run_cycle() -> set[Path]:
        sync_calls.append(1)
        if len(sync_calls) == 2:
            raise KeyboardInterrupt
        return set()

    observer_holder: dict[str, FakeObserver] = {}
    translation_path = Path("/tmp/tree/node/translation.md")

    def observer_factory(tree_dir: Path, event_sink) -> FakeObserver:
        observer = FakeObserver(on_start=lambda: event_sink((translation_path,)))
        observer_holder["value"] = observer
        assert tree_dir == Path("/tmp/tree")
        return observer

    service = SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path("/tmp/tree"),
            debounce_seconds=0.0,
            observer_healthcheck_seconds=0.0,
        ),
        run_cycle=run_cycle,
        observer_factory=observer_factory,
        time_module=fake_time,
    )

    with pytest.raises(KeyboardInterrupt):
        service.run()

    captured = capsys.readouterr()
    assert sync_calls == [1, 1]
    assert "Restarting watchdog observer" not in captured.out
    assert observer_holder["value"].started is True
    assert observer_holder["value"].stopped is True
    assert observer_holder["value"].joined is True


def test_sync_watch_service_restarts_watchdog_after_observer_failure(capsys) -> None:
    """Verify that watch mode restarts after observer failure."""

    fake_time = FakeTimeModule()
    sync_calls: list[int] = []
    observers: list[FakeObserver] = []
    translation_path = Path("/tmp/tree/node/translation.md")

    def run_cycle() -> set[Path]:
        sync_calls.append(1)
        if len(sync_calls) == 2:
            raise KeyboardInterrupt
        return set()

    def observer_factory(_: Path, event_sink) -> FakeObserver:
        if not observers:
            observer = FakeObserver(alive_sequence=[False])
        else:
            observer = FakeObserver(on_start=lambda: event_sink((translation_path,)))
        observers.append(observer)
        return observer

    service = SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path("/tmp/tree"),
            debounce_seconds=0.0,
            observer_healthcheck_seconds=0.0,
        ),
        run_cycle=run_cycle,
        observer_factory=observer_factory,
        time_module=fake_time,
    )

    with pytest.raises(KeyboardInterrupt):
        service.run()

    captured = capsys.readouterr()
    assert sync_calls == [1, 1]
    assert "watchdog observer stopped unexpectedly after startup." in captured.out
    assert "Restarting watchdog observer." in captured.out
    assert len(observers) == 2
    assert observers[0].stopped is True
    assert observers[0].joined is True


def test_sync_watch_service_reports_sync_errors_without_exiting_watchdog_loop(
    capsys,
) -> None:
    """Verify that watch mode keeps running after sync errors.

    Args:
        capsys: Pytest output capture fixture.
    """

    fake_time = FakeTimeModule()
    sync_calls: list[int] = []
    translation_path = Path("/tmp/tree/node/translation.md")

    def run_cycle() -> set[Path]:
        sync_calls.append(1)
        if len(sync_calls) == 1:
            raise ValueError("broken translation.md was restored")
        raise KeyboardInterrupt

    def observer_factory(_: Path, event_sink) -> FakeObserver:
        return FakeObserver(
            on_start=lambda: (
                event_sink((translation_path,)),
                event_sink((translation_path,)),
            )
        )

    service = SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path("/tmp/tree"),
            debounce_seconds=0.0,
            observer_healthcheck_seconds=0.0,
        ),
        run_cycle=run_cycle,
        observer_factory=observer_factory,
        time_module=fake_time,
    )

    with pytest.raises(KeyboardInterrupt):
        service.run()

    captured = capsys.readouterr()
    assert sync_calls == [1, 1]
    assert "[sync] Error: broken translation.md was restored" in captured.out
    assert "Restarting watchdog observer" not in captured.out


def test_translation_tree_watch_filter_accepts_only_editable_inputs() -> None:
    """Verify that the path filter only triggers on editable sync inputs."""

    tree_dir = Path("/tmp/tree")
    filter_service = TranslationTreeWatchFilter(tree_dir=tree_dir, watch_shared_blocks=True)
    registry = RecentWriteRegistry(suppression_seconds=1.5, time_source=lambda: 0.0)

    translation_path = tree_dir / "chapter" / "translation.md"
    shared_blocks_context_path = tree_dir / "shared_blocks" / "abc123" / "context.md"
    trigger_paths = filter_service.select_trigger_paths(
        paths=(
            translation_path,
            shared_blocks_context_path,
            tree_dir / "outline.md",
            tree_dir / "shared_blocks_outline.md",
            tree_dir / "shared_blocks.md",
            tree_dir / "_translation_tree.json",
            tree_dir.parent / "builds" / "final_translated.po",
            tree_dir.parent / "reviews" / "final_translated.diff",
            tree_dir.parent / "backups" / tree_dir.name / "uuid.translation.md.bak",
        ),
        write_registry=registry,
    )

    assert trigger_paths == (
        translation_path.resolve(),
        shared_blocks_context_path.resolve(),
    )


def test_sync_watch_service_suppresses_tool_written_translation_events() -> None:
    """Verify that tool-written translation files do not retrigger sync."""

    fake_time = FakeTimeModule()
    sync_calls: list[int] = []
    translation_path = Path("/tmp/tree/chapter/translation.md")
    callback_holder: dict[str, object] = {}
    observer_creations: list[int] = []

    def run_cycle() -> set[Path]:
        sync_calls.append(1)
        if len(sync_calls) == 2:
            callback_holder["value"]((translation_path,))
            return {translation_path}
        return set()

    def observer_factory(_: Path, event_sink) -> FakeObserver:
        observer_creations.append(1)
        if len(observer_creations) > 1:
            raise KeyboardInterrupt
        callback_holder["value"] = event_sink
        return FakeObserver(
            on_start=lambda: event_sink((translation_path,)),
            alive_sequence=[True, True, True, False],
        )

    service = SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path("/tmp/tree"),
            debounce_seconds=0.0,
            observer_healthcheck_seconds=0.0,
        ),
        run_cycle=run_cycle,
        observer_factory=observer_factory,
        time_module=fake_time,
    )

    with pytest.raises(KeyboardInterrupt):
        service.run()

    assert sync_calls == [1, 1]


def test_sync_watch_service_coalesces_burst_events_into_one_rerun() -> None:
    """Verify that burst events during an active sync queue one rerun only."""

    fake_time = FakeTimeModule()
    sync_calls: list[int] = []
    translation_path = Path("/tmp/tree/chapter/translation.md")
    callback_holder: dict[str, object] = {}

    def run_cycle() -> set[Path]:
        sync_calls.append(1)
        if len(sync_calls) == 2:
            callback_holder["value"]((translation_path,))
            callback_holder["value"]((translation_path,))
            callback_holder["value"]((translation_path,))
            return set()
        if len(sync_calls) == 3:
            raise KeyboardInterrupt
        return set()

    def observer_factory(_: Path, event_sink) -> FakeObserver:
        callback_holder["value"] = event_sink
        return FakeObserver(on_start=lambda: event_sink((translation_path,)))

    service = SyncWatchService(
        settings=SyncWatchSettings(
            tree_dir=Path("/tmp/tree"),
            debounce_seconds=0.0,
            observer_healthcheck_seconds=0.0,
        ),
        run_cycle=run_cycle,
        observer_factory=observer_factory,
        time_module=fake_time,
    )

    with pytest.raises(KeyboardInterrupt):
        service.run()

    assert sync_calls == [1, 1, 1]


def test_sync_watch_service_surfaces_missing_dependency() -> None:
    """Verify that watch mode surfaces missing dependencies."""

    def observer_factory(_: Path, __) -> FakeObserver:
        raise WatchdogUnavailableError("watchdog is missing")

    service = SyncWatchService(
        settings=SyncWatchSettings(tree_dir=Path("/tmp/tree")),
        run_cycle=lambda: set(),
        observer_factory=observer_factory,
    )

    with pytest.raises(ValueError, match="watchdog is missing"):
        service.run()
