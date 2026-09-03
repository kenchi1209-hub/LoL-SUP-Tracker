"""Windows LCU watcher with an explicit, opt-in post-ranked live mode."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from data_paths import get_data_paths
from lcu_client import LCUError, LCUUnavailable, LCUClient, session_diagnostic
from lcu_publish import PrivateDataPublisher, PublishError
from lp_snapshot import discover_local_uncaptured_solo_matches, previous_state
from timezone_utils import now_jst


SOLO_QUEUE_ID = 420
START_PHASES = {"ChampSelect", "InProgress"}
FINISH_PHASES = {"WaitingForStats", "EndOfGame"}
KNOWN_PHASES = {
    "None", "Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "InProgress",
    "WaitingForStats", "PreEndOfGame", "EndOfGame",
}
MAIN_TIMEOUT_SECONDS = 300
CAPTURE_TIMEOUT_SECONDS = 180
MATCH_UPDATE_RETRY_SECONDS = 10
MATCH_UPDATE_MAX_ATTEMPTS = 13
MATCH_UPDATE_MAX_WAIT_SECONDS = 120


class LiveProcessError(RuntimeError):
    """A live update could not safely reach an exact LP capture."""


class SingleInstanceLock:
    """Windows named mutex; no file or credential is created."""

    def __init__(self, name="Local\\LoLAnalyticsLCUWatcher"):
        self.name = name
        self.handle = None

    def acquire(self):
        if os.name != "nt":
            return True
        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        return bool(self.handle) and kernel32.GetLastError() != 183

    def release(self):
        if self.handle and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(self.handle)
        self.handle = None


def queue_id_from_session(session):
    """Return an integer only from known candidate paths; otherwise safely skip."""
    if not isinstance(session, dict):
        return None
    candidates = [
        session.get("gameData", {}).get("queue", {}).get("id")
        if isinstance(session.get("gameData"), dict) else None,
        session.get("gameData", {}).get("queueId") if isinstance(session.get("gameData"), dict) else None,
        session.get("queue", {}).get("id") if isinstance(session.get("queue"), dict) else None,
        session.get("queueId"),
    ]
    for value in candidates:
        try:
            if isinstance(value, bool):
                continue
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def session_id_from_session(session):
    """Return a non-PII game session identifier from known LCU fields only."""
    if not isinstance(session, dict):
        return None
    game_data = session.get("gameData")
    candidates = [
        game_data.get("gameId") if isinstance(game_data, dict) else None,
        session.get("gameId"),
    ]
    for value in candidates:
        if value is None or isinstance(value, bool):
            continue
        value = str(value).strip()
        if value:
            return value
    return None


class LCUWatcher:
    def __init__(
        self, client=None, emit=print, sleeper=time.sleep, idle_interval=3,
        active_interval=1, live=False, data_root=None, process_runner=subprocess.run,
        repo_root=None, monotonic=time.monotonic, auto_publish=False, publisher=None,
    ):
        if idle_interval < 1 or active_interval < 1:
            raise ValueError("Polling intervals must be at least one second")
        self.client = client or LCUClient()
        self.emit = emit
        self.sleeper = sleeper
        self.idle_interval = idle_interval
        self.active_interval = active_interval
        self.last_phase = None
        self.pending = None
        self._waiting_logged = False
        self._diagnosed_session = False
        self.live = live
        self.data_root = Path(data_root).expanduser().resolve() if data_root else None
        self.process_runner = process_runner
        self.repo_root = Path(repo_root or __file__).resolve().parent
        self.monotonic = monotonic
        self.auto_publish = auto_publish
        self.publisher = publisher

    def _log(self, message):
        self.emit(message)

    def _start_pending(self, phase, queue_id, session_id):
        before = self._verified_lcu_before_rank(self.client.get_solo_rank())
        self.pending = {
            "detected_at_jst": now_jst().replace(microsecond=0).isoformat(),
            "start_phase": phase,
            "queue_id": queue_id,
            "session_id": session_id,
            "lcu_before_rank": before,
            "processing_started": False,
            "capture_attempted": False,
            "published": False,
            "completed": False,
            "failed": False,
            "terminal": False,
            "has_reached_in_progress": phase == "InProgress",
            "match_update_attempts": 0,
            "waiting_diagnostics_logged": False,
        }
        self._log("[LP] solo ranked detected")
        self._log("[LP] pending started")

    def _verified_lcu_before_rank(self, rank):
        """Return an in-memory pre-match rank only for the stored account.

        The LCU account identifier is never logged or persisted here.  If the
        local account cannot be checked against PrivateData, the next capture
        simply proceeds without attempting a retrospective LP correction.
        """
        if not self.live or self.data_root is None or not isinstance(rank, dict):
            return None
        get_puuid = getattr(self.client, "get_current_puuid", None)
        if not callable(get_puuid):
            self._log("[LP] pre-match LP recheck skipped: account verification unavailable")
            return None
        try:
            active_puuid = get_puuid()
            with (self.data_root / "csv" / "current_rank.json").open(
                "r", encoding="utf-8",
            ) as file:
                saved_rank = json.load(file)
        except (LCUError, OSError, json.JSONDecodeError):
            self._log("[LP] pre-match LP recheck skipped: account verification unavailable")
            return None
        saved_puuid = saved_rank.get("puuid") if isinstance(saved_rank, dict) else None
        if not active_puuid or active_puuid != saved_puuid:
            self._log("[LP] pre-match LP recheck skipped: account verification unavailable")
            return None
        return rank

    def _log_rank_diagnostic(self):
        """Show only non-identifying LCU rank fields; never treat them as canonical."""
        try:
            rank = self.client.get_solo_rank()
        except LCUError:
            self._log("[LCU] rank diagnostic unavailable")
            return
        if not rank:
            self._log("[LCU] rank diagnostic unavailable")
            return
        self._log(
            "[LCU] rank diagnostic: "
            f"{rank['tier']} {rank['division']} {rank['leaguePoints']}LP "
            f"{rank['wins']}W/{rank['losses']}L"
        )

    def _command(self, script, *arguments):
        return [sys.executable, str(self.repo_root / script), *arguments]

    def _run_process(self, command, timeout):
        """Run an existing CLI safely without exposing its output in watcher logs."""
        return self.process_runner(
            command,
            cwd=str(self.repo_root),
            shell=False,
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _uncaptured_solo_matches(self):
        if self.data_root is None:
            raise LiveProcessError("live data root is unavailable")
        paths = get_data_paths(self.data_root)
        _before, cutoff_jst, _events = previous_state(paths.raw)
        return discover_local_uncaptured_solo_matches(paths.raw, paths.csv, cutoff_jst)

    def _has_rank_after(self, match_id):
        return (self.data_root / "raw" / match_id / "rank_after.json").is_file()

    def _correction_match_id(self, match_id):
        """Read an optional, capture-produced correction relation safely."""
        path = self.data_root / "raw" / match_id / "rank_after.json"
        try:
            with path.open("r", encoding="utf-8") as file:
                snapshot = json.load(file)
        except (OSError, json.JSONDecodeError):
            return None
        previous = snapshot.get("reconciled_previous_match_id") if isinstance(snapshot, dict) else None
        return previous if isinstance(previous, str) and previous else None

    def _live_process(self):
        """Delegate all writes to the existing update and exact-capture CLIs."""
        pending = self.pending
        pending["processing_started"] = True
        try:
            if self.auto_publish:
                self._publisher().preflight()
            retry_deadline = self.monotonic() + MATCH_UPDATE_MAX_WAIT_SECONDS
            for attempt in range(1, MATCH_UPDATE_MAX_ATTEMPTS + 1):
                pending["match_update_attempts"] = attempt
                result = self._run_process(
                    self._command("main.py", "--data-root", str(self.data_root)),
                    MAIN_TIMEOUT_SECONDS,
                )
                if result.returncode != 0:
                    raise LiveProcessError(f"main.py exited with code {result.returncode}")

                matches = self._uncaptured_solo_matches()
                if len(matches) == 1:
                    match_id = matches[0]["match_id"]
                    self._log("[DATA] match update complete")
                    pending["capture_attempted"] = True
                    capture_command = self._command(
                        "lp_snapshot.py", "capture", "--data-root", str(self.data_root),
                    )
                    if isinstance(pending.get("lcu_before_rank"), dict):
                        capture_command.extend((
                            "--next-rank-before-json",
                            json.dumps(pending["lcu_before_rank"], separators=(",", ":")),
                        ))
                    capture = self._run_process(
                        capture_command,
                        CAPTURE_TIMEOUT_SECONDS,
                    )
                    if capture.returncode == 0:
                        if not self._has_rank_after(match_id):
                            raise LiveProcessError("capture completed without rank_after confirmation")
                        self._log("[LP] exact capture completed")
                        if self.auto_publish:
                            correction_match_id = self._correction_match_id(match_id)
                            if correction_match_id:
                                self._publisher().publish(
                                    match_id, correction_match_id=correction_match_id,
                                )
                            else:
                                self._publisher().publish(match_id)
                            pending["published"] = True
                            self._log("[DONE] automatic publish complete")
                        pending["completed"] = True
                        pending["terminal"] = True
                        return
                    if capture.returncode == 2:
                        pending["terminal"] = True
                        self._log("[LP] CHECKPOINT_REQUIRED")
                        return
                    raise LiveProcessError(f"lp_snapshot.py exited with code {capture.returncode}")

                if len(matches) > 1:
                    self._log("[LP] CHECKPOINT_REQUIRED")
                    return
                remaining = retry_deadline - self.monotonic()
                if remaining <= 0:
                    break
                if attempt < MATCH_UPDATE_MAX_ATTEMPTS and remaining > 0:
                    self._log("[LP] waiting for Match-V5 reflection")
                    self.sleeper(min(MATCH_UPDATE_RETRY_SECONDS, remaining))
            raise LiveProcessError("Match-V5 reflection timed out")
        except subprocess.TimeoutExpired:
            pending["failed"] = True
            pending["terminal"] = True
            self._log("[LP] LIVE PROCESS FAILED: subprocess timeout")
        except (LiveProcessError, PublishError, OSError, ValueError) as error:
            pending["failed"] = True
            pending["terminal"] = True
            self._log(f"[LP] LIVE PROCESS FAILED: {error}")

    def _publisher(self):
        if self.publisher is None:
            self.publisher = PrivateDataPublisher(
                private_root=self.data_root,
                public_repo="kenchi1209-hub/LoL-SUP-Tracker",
                emit=self._log,
            )
        return self.publisher

    def _finish_pending(self):
        pending = self.pending
        pending["processing_started"] = True
        self._log("[LP] ranked finished")
        if not self.live:
            self._log("[LP] WOULD_RUN_MATCH_UPDATE")
            self._log("[LP] WOULD_RUN_CAPTURE")
            pending["terminal"] = True
            return
        self._live_process()

    def _log_waiting_diagnostics(self, queue_id, session_id):
        """Log one non-PII trigger check for each pending ranked game."""
        pending = self.pending
        if pending["waiting_diagnostics_logged"]:
            return
        pending["waiting_diagnostics_logged"] = True
        pending_id_present = pending["session_id"] is not None
        current_id_present = session_id is not None
        id_match = pending_id_present and current_id_present and session_id == pending["session_id"]
        self._log(
            "[LP] trigger diagnostics: "
            f"queue={queue_id} in_progress={pending['has_reached_in_progress']} "
            f"processing={pending['processing_started']} completed={pending['completed']} "
            f"terminal={pending['terminal']} pending_id_present={pending_id_present} "
            f"current_id_present={current_id_present} id_match={id_match}"
        )
        if not id_match:
            self._log("[LP] session id unavailable/mismatch; continuing with phase-safe trigger")

    def _handle_phase(self, phase, session):
        previous = self.last_phase
        if phase != previous:
            self._log(f"[LCU] phase: {previous} -> {phase}")
        self.last_phase = phase
        if phase not in KNOWN_PHASES:
            self._log(f"[LCU] unknown phase: {phase}")
        if session is not None and not self._diagnosed_session:
            self._log(f"[LCU] session schema: {session_diagnostic(session, phase)}")
            self._diagnosed_session = True
        if session is None:
            self._diagnosed_session = False
        queue_id = queue_id_from_session(session)
        session_id = session_id_from_session(session)
        if queue_id is not None and phase != previous:
            self._log(f"[LCU] queue: {queue_id}")
        if queue_id == SOLO_QUEUE_ID and phase in START_PHASES:
            if self.pending is None:
                self._start_pending(phase, queue_id, session_id)
            elif self.pending["terminal"]:
                self._start_pending(phase, queue_id, session_id)
        if self.pending and phase == "InProgress":
            self.pending["has_reached_in_progress"] = True
        if self.pending and phase == "WaitingForStats":
            self._log_waiting_diagnostics(queue_id, session_id)
        if (
            self.pending
            and self.pending["queue_id"] == SOLO_QUEUE_ID
            and self.pending["has_reached_in_progress"]
            and phase in FINISH_PHASES
            and not self.pending["processing_started"]
            and not self.pending["completed"]
            and not self.pending["terminal"]
            and queue_id == SOLO_QUEUE_ID
        ):
            self._finish_pending()

    def tick(self):
        try:
            if not self.client.connected:
                self.client.connect()
                self._waiting_logged = False
                self._log("[LCU] client detected")
                self._log("[LCU] connected")
                self._log_rank_diagnostic()
            phase = self.client.get_gameflow_phase()
            session = self.client.get_gameflow_session()
            self._handle_phase(phase, session)
            return phase not in {None, "None"}
        except LCUUnavailable:
            self.client.disconnect()
            if not self._waiting_logged:
                self._log("[LCU] waiting for client")
                self._waiting_logged = True
            return False
        except LCUError:
            self._log("[LCU] read-only request failed; monitoring continues")
            return False

    def run(self, max_ticks=None):
        ticks = 0
        try:
            while max_ticks is None or ticks < max_ticks:
                active = self.tick()
                ticks += 1
                self.sleeper(self.active_interval if active else self.idle_interval)
        except KeyboardInterrupt:
            self._log("[LCU] watcher stopped")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", help="Absolute PrivateData root required for --live")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Observe only (default)")
    parser.add_argument("--live", action="store_true", help="Opt in to main.py then exact LP capture")
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="With --live only, commit one validated PrivateData update and trigger Pages",
    )
    return parser.parse_args(argv)


def run_watcher(watcher, lock):
    """Run one watcher instance, returning 2 when its named mutex is already held."""
    if not lock.acquire():
        watcher._log("[LCU] another watcher is already running")
        return 2
    try:
        watcher._log("[LP] mode: LIVE" if watcher.live else "[LP] mode: DRY-RUN")
        watcher.run()
    finally:
        lock.release()
    return 0


def main(argv=None):
    args = parse_args(argv)
    data_root = None
    if args.auto_publish and not args.live:
        print("[LP] LIVE PROCESS FAILED: --auto-publish requires --live")
        return 1
    if args.live:
        if not args.data_root:
            print("[LP] LIVE PROCESS FAILED: --data-root is required for --live")
            return 1
        data_root = Path(args.data_root).expanduser().resolve()
        required = (data_root, data_root / "raw" / "lp_progress" / "baseline.json", data_root / "csv")
        if not all(path.exists() for path in required):
            print("[LP] LIVE PROCESS FAILED: invalid PrivateData path")
            return 1
    return run_watcher(
        LCUWatcher(live=args.live, data_root=data_root, auto_publish=args.auto_publish),
        SingleInstanceLock(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
