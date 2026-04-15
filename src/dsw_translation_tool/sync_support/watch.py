"""Watch-loop helpers for shared-string synchronization."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

WATCHDOG_EVENT_TYPES = frozenset({"created", "modified", "moved", "deleted"})
DEFAULT_DEBOUNCE_SECONDS = 0.75
DEFAULT_SELF_WRITE_SUPPRESSION_SECONDS = 1.5
DEFAULT_OBSERVER_HEALTHCHECK_SECONDS = 0.25


class SyncCycleRunner(Protocol):
    """Protocol for one sync-cycle callback used by watch mode."""

    def __call__(self) -> set[Path]:
        """Run one sync cycle and return the written paths."""


class ObserverLike(Protocol):
    """Minimal observer interface used by the watchdog watch service."""

    def start(self) -> None:
        """Start the observer."""

    def stop(self) -> None:
        """Stop the observer."""

    def join(self, timeout: float | None = None) -> None:
        """Wait for the observer thread to terminate."""

    def is_alive(self) -> bool:
        """Return whether the observer thread is still running."""


class WatchdogModeError(RuntimeError):
    """Base error raised when watchdog watch mode cannot continue."""


class WatchdogUnavailableError(WatchdogModeError):
    """Raised when watchdog is unavailable or cannot start."""


class WatchdogObserverStoppedError(WatchdogModeError):
    """Raised when a watchdog observer stops unexpectedly after startup."""


@dataclass(frozen=True)
class SyncWatchSettings:
    """Runtime settings for one `sync-watch` session.

    Args:
        tree_dir: Translation tree root monitored by watch mode.
        watch_shared_blocks: Whether `shared_blocks.md` should trigger sync.
        debounce_seconds: Debounce window for collapsing burst file events.
        self_write_suppression_seconds: Window used to ignore tool-written files.
        observer_healthcheck_seconds: Queue timeout used to re-check observer
            liveness while waiting for filesystem events.
    """

    tree_dir: Path
    watch_shared_blocks: bool = True
    debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS
    self_write_suppression_seconds: float = DEFAULT_SELF_WRITE_SUPPRESSION_SECONDS
    observer_healthcheck_seconds: float = DEFAULT_OBSERVER_HEALTHCHECK_SECONDS


@dataclass
class RecentWriteRegistry:
    """Track recently written files so watchdog can ignore self-triggered events.

    Args:
        suppression_seconds: Duration in seconds for suppressing self-written
            paths.
        time_source: Monotonic time source used for testability.
    """

    suppression_seconds: float
    time_source: Callable[[], float] = time.monotonic
    _expires_at: dict[Path, float] = field(default_factory=dict)

    def mark_paths(self, paths: Iterable[Path]) -> None:
        """Register one or more recently written filesystem paths.

        Args:
            paths: Paths written by the sync tool itself.
        """

        now = self.time_source()
        self._prune(now)
        for path in paths:
            self._expires_at[path.resolve()] = now + self.suppression_seconds

    def is_suppressed(self, path: Path) -> bool:
        """Return whether one path is still inside the suppression window.

        Args:
            path: Candidate filesystem path.

        Returns:
            `True` when the path should be ignored as a recent tool write.
        """

        now = self.time_source()
        self._prune(now)
        return self._expires_at.get(path.resolve(), 0.0) > now

    def _prune(self, now: float) -> None:
        """Drop expired suppression entries.

        Args:
            now: Current monotonic time.
        """

        expired = [path for path, expires_at in self._expires_at.items() if expires_at <= now]
        for path in expired:
            self._expires_at.pop(path, None)


class TranslationTreeWatchFilter:
    """Filter raw filesystem events down to user-editable sync inputs."""

    def __init__(self, tree_dir: Path, watch_shared_blocks: bool = True):
        self.tree_dir = tree_dir.resolve()
        self.watch_shared_blocks = watch_shared_blocks
        self.shared_blocks_path = (self.tree_dir / "shared_blocks.md").resolve()
        self.backups_root = (self.tree_dir.parent / "backups").resolve()

    def select_trigger_paths(
        self,
        paths: Iterable[Path],
        write_registry: RecentWriteRegistry,
    ) -> tuple[Path, ...]:
        """Return relevant paths from one raw event batch.

        Args:
            paths: Raw filesystem paths extracted from one watchdog event.
            write_registry: Recently-written path registry used for suppression.

        Returns:
            Tuple of normalized, relevant trigger paths.
        """

        trigger_paths: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            normalized = self._normalize(path)
            if normalized is None:
                continue
            if normalized in seen:
                continue
            if write_registry.is_suppressed(normalized):
                continue
            seen.add(normalized)
            trigger_paths.append(normalized)
        return tuple(trigger_paths)

    def _normalize(self, path: Path) -> Path | None:
        """Normalize one event path and decide whether it should trigger sync.

        Args:
            path: Raw filesystem path.

        Returns:
            Absolute normalized path when relevant, otherwise `None`.
        """

        normalized = path.resolve()
        try:
            relative_path = normalized.relative_to(self.tree_dir)
        except ValueError:
            return None

        if self._is_under_backups(relative_path):
            return None
        if normalized == self.shared_blocks_path:
            return normalized if self.watch_shared_blocks else None
        if relative_path.name == "translation.md":
            return normalized
        return None

    def _is_under_backups(self, relative_path: Path) -> bool:
        """Return whether one path points into the local backup area.

        Args:
            relative_path: Path relative to the watched tree root.

        Returns:
            `True` when the path should be ignored as a backup artifact.
        """

        return bool(relative_path.parts and relative_path.parts[0] == self.backups_root.name)


def create_watchdog_observer(
    tree_dir: Path,
    event_sink: Callable[[tuple[Path, ...]], None],
) -> ObserverLike:
    """Create a watchdog observer that forwards relevant file events.

    Args:
        tree_dir: Translation tree root directory to watch recursively.
        event_sink: Callback receiving normalized event paths.

    Returns:
        Started observer-compatible instance.

    Raises:
        WatchdogUnavailableError: If watchdog is unavailable or cannot be imported.
    """

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as error:
        raise WatchdogUnavailableError(
            "watchdog is not installed. Use `make install-dev` before running "
            "`make sync-watch`."
        ) from error

    class _EventHandler(FileSystemEventHandler):
        """Forward file create/modify/move/delete events to the queue sink."""

        def on_created(self, event) -> None:  # type: ignore[no-untyped-def]
            self._forward(event)

        def on_modified(self, event) -> None:  # type: ignore[no-untyped-def]
            self._forward(event)

        def on_deleted(self, event) -> None:  # type: ignore[no-untyped-def]
            self._forward(event)

        def on_moved(self, event) -> None:  # type: ignore[no-untyped-def]
            self._forward(event)

        def _forward(self, event) -> None:  # type: ignore[no-untyped-def]
            if getattr(event, "is_directory", False):
                return
            if getattr(event, "event_type", None) not in WATCHDOG_EVENT_TYPES:
                return
            event_paths = []
            src_path = getattr(event, "src_path", None)
            dest_path = getattr(event, "dest_path", None)
            if src_path:
                event_paths.append(Path(src_path).resolve())
            if dest_path:
                event_paths.append(Path(dest_path).resolve())
            if event_paths:
                event_sink(tuple(event_paths))

    observer = Observer()
    observer.schedule(_EventHandler(), str(tree_dir), recursive=True)
    return observer


@dataclass
class SyncWatchService:
    """Run `sync-watch` using watchdog event monitoring.

    Args:
        settings: Watch-mode runtime settings.
        run_cycle: Callback that runs one sync pass and returns written paths.
        observer_factory: Factory creating a watchdog observer for the tree.
        time_module: Module-like object providing `sleep`, `strftime`, and
            `monotonic`.
    """

    settings: SyncWatchSettings
    run_cycle: SyncCycleRunner
    observer_factory: Callable[[Path, Callable[[tuple[Path, ...]], None]], ObserverLike] = (
        create_watchdog_observer
    )
    time_module: object = time

    def __post_init__(self) -> None:
        """Initialize helper collaborators after dataclass construction."""

        monotonic = getattr(self.time_module, "monotonic", time.monotonic)
        self.write_registry = RecentWriteRegistry(
            suppression_seconds=self.settings.self_write_suppression_seconds,
            time_source=monotonic,
        )
        self.path_filter = TranslationTreeWatchFilter(
            tree_dir=self.settings.tree_dir,
            watch_shared_blocks=self.settings.watch_shared_blocks,
        )

    def run(self) -> None:
        """Run watchdog-backed watch mode.

        Raises:
            ValueError: If watchdog cannot be started.
        """

        self.run_logged_sync_cycle()
        try:
            self.run_watchdog_loop()
        except WatchdogModeError as error:
            raise ValueError(str(error)) from error

    def run_logged_sync_cycle(self) -> set[Path]:
        """Run one sync cycle with the standard watch-mode logging wrapper.

        Returns:
            Set of recently written paths produced by the cycle.
        """

        timestamp = self.time_module.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[sync] Running at {timestamp}")
        try:
            written_paths = {path.resolve() for path in self.run_cycle()}
        except ValueError as error:
            print(f"[sync] Error: {error}")
            print()
            return set()

        self.write_registry.mark_paths(written_paths)
        print()
        return written_paths

    def run_watchdog_loop(self) -> None:
        """Run event-driven watch mode until interrupted.

        Raises:
            WatchdogUnavailableError: If the observer cannot start.
        """

        while True:
            event_queue: queue.Queue[tuple[Path, ...]] = queue.Queue()
            observer = self.observer_factory(self.settings.tree_dir, event_queue.put_nowait)
            observer_started = False
            try:
                try:
                    observer.start()
                except Exception as error:  # pragma: no cover - defensive startup path
                    raise WatchdogUnavailableError(
                        f"watchdog observer could not start: {error}"
                    ) from error
                observer_started = True

                while True:
                    try:
                        self.wait_for_relevant_event(observer, event_queue)
                    except WatchdogObserverStoppedError as error:
                        print(f"[sync] Warning: {error}")
                        print("[sync] Restarting watchdog observer.")
                        print()
                        break
                    self.run_logged_sync_cycle()
            finally:
                if observer_started:
                    observer.stop()
                    observer.join(timeout=1.0)

    def wait_for_relevant_event(
        self,
        observer: ObserverLike,
        event_queue: queue.Queue[tuple[Path, ...]],
    ) -> None:
        """Block until one debounced, relevant filesystem change is observed.

        Args:
            observer: Active watchdog observer.
            event_queue: Queue receiving raw filesystem-event paths.

        Raises:
            WatchdogObserverStoppedError: If the observer stops unexpectedly.
        """

        deadline: float | None = None
        monotonic = getattr(self.time_module, "monotonic", time.monotonic)

        while True:
            self._assert_observer_running(observer)
            now = monotonic()
            if deadline is None:
                timeout = self.settings.observer_healthcheck_seconds
            else:
                timeout = max(
                    0.0,
                    min(deadline - now, self.settings.observer_healthcheck_seconds),
                )
            try:
                event_paths = event_queue.get(timeout=timeout)
            except queue.Empty:
                if deadline is not None and monotonic() >= deadline:
                    return
                continue

            relevant_paths = self.path_filter.select_trigger_paths(
                paths=event_paths,
                write_registry=self.write_registry,
            )
            if not relevant_paths:
                continue
            deadline = monotonic() + self.settings.debounce_seconds

    @staticmethod
    def _assert_observer_running(observer: ObserverLike) -> None:
        """Ensure the watchdog observer is still alive.

        Args:
            observer: Active watchdog observer.

        Raises:
            WatchdogObserverStoppedError: If the observer thread stopped.
        """

        if observer.is_alive():
            return
        raise WatchdogObserverStoppedError("watchdog observer stopped unexpectedly after startup.")
