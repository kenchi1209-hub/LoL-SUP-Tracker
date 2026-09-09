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
from lp_snapshot import (
    LPSnapshotError,
    discover_local_uncaptured_solo_matches,
    previous_state,
    reconcile_previous_rank_after,
)
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
RANK_RECHECK_INTERVAL_SECONDS = 30
RANK_RECHECK_MAX_SECONDS = 300
IDENTITY_RETRY_INTERVAL_SECONDS = 5
IDENTITY_RETRY_PHASES = {"Lobby", "Matchmaking", "ReadyCheck", "ChampSelect"}


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
        self.recheck = None
        # Kept only for the current LCU connection.  It is never logged or
        # written to disk, and is cleared on reconnect/disconnect.
        self._verified_account_puuid = None
        self._identity_verification_reason = None
        self._next_identity_retry_at = 0
        self.checkpoint_pending = None

    def _log(self, message):
        self.emit(message)

    def _start_pending(self, phase, queue_id, session_id):
        before = self._latest_recheck_rank()
        if before is None:
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

    def _require_checkpoint(self):
        """Terminally stop one game without blocking the next ranked game."""
        pending = self.pending
        pending["checkpoint_required"] = True
        pending["terminal"] = True
        # Preserve the stopped game's in-memory state for diagnostics while a
        # following Queue 420 game receives a fresh pending record.
        self.checkpoint_pending = pending
        self._log("[LP] CHECKPOINT_REQUIRED")

    def _latest_recheck_rank(self):
        if not isinstance(self.recheck, dict):
            return None
        rank = self.recheck.get("latest_rank")
        return dict(rank) if isinstance(rank, dict) else None

    def _format_rank(self, rank):
        return (
            f"{rank['tier']} {rank['division']} {rank['leaguePoints']}LP "
            f"{rank['wins']}W/{rank['losses']}L"
        )

    def _start_recheck(self):
        """Start one read-only Queue 420 rank recheck session."""
        if not self.live or self.data_root is None or self.recheck is not None:
            return
        started = self.monotonic()
        self.recheck = {
            "started_at_jst": now_jst().replace(microsecond=0).isoformat(),
            "deadline": started + RANK_RECHECK_MAX_SECONDS,
            "next_poll_at": started,
            "latest_rank": None,
            "correction_candidate": None,
        }
        self._log("[LP] recheck session started")
        self._poll_recheck(force=True)

    def _end_recheck(self, reason):
        if self.recheck is None:
            return
        latest_rank = self._latest_recheck_rank()
        if reason == "game_start" and self.pending and latest_rank is not None:
            self.pending["lcu_before_rank"] = latest_rank
        self._log(f"[LP] recheck session ended: {reason}")
        self.recheck = None

    def _poll_recheck(self, force=False):
        """Read the current rank at a bounded cadence without writing data."""
        if self.recheck is None:
            return
        now = self.monotonic()
        if now >= self.recheck["deadline"]:
            self._end_recheck("timeout")
            return
        if not force and now < self.recheck["next_poll_at"]:
            return
        self.recheck["next_poll_at"] = now + RANK_RECHECK_INTERVAL_SECONDS
        try:
            observed_rank = self.client.get_solo_rank()
        except LCUError:
            self._log("[LP] recheck rank unavailable")
            return
        if not isinstance(observed_rank, dict):
            self._log("[LP] recheck rank unavailable")
            return
        self._log(f"[LP] recheck rank fetched: {self._format_rank(observed_rank)}")
        rank = self._verified_lcu_before_rank(observed_rank)
        if rank is None:
            reason = self._identity_verification_reason or "LCU endpoint"
            self._log(f"[LP] recheck rank not adopted: {reason}")
            return
        self.recheck["latest_rank"] = rank
        self._log(f"[LP] recheck rank adopted: {self._format_rank(rank)}")
        try:
            paths = get_data_paths(self.data_root)
            result = reconcile_previous_rank_after(
                paths.raw,
                paths.csv,
                rank,
                now_jst().replace(microsecond=0).isoformat(),
                apply=False,
            )
        except (LPSnapshotError, OSError, ValueError):
            return
        if result.get("status") == "corrected":
            self.recheck["correction_candidate"] = result.get("match_id")
            self._log("[LP] post-match correction candidate detected")

    def _verified_lcu_before_rank(self, rank):
        """Return an in-memory pre-match rank only for the stored account.

        The LCU account identifier is never logged or persisted here.  If the
        local account cannot be checked against PrivateData, the next capture
        simply proceeds without attempting a retrospective LP correction.
        """
        if not self.live or self.data_root is None or not isinstance(rank, dict):
            return None
        if self._verified_account_puuid is not None:
            # Revalidate when the endpoint is available; retain only the
            # already verified identity during a transient gameflow failure.
            try:
                active_puuid = self.client.get_current_puuid()
            except LCUError:
                return rank
            if not isinstance(active_puuid, str) or not active_puuid:
                return rank
            if active_puuid == self._verified_account_puuid:
                return rank
            self._verified_account_puuid = None
        if not self._verify_active_account():
            reason = self._identity_verification_reason or "LCU endpoint"
            self._log(f"[LP] identity verification unavailable: {reason}")
            return None
        return rank

    def _verify_active_account(self):
        """Cache a verified LCU account for this connection only.

        The current-summoner endpoint can be transiently unavailable during
        gameflow transitions.  A PUUID already verified after this same LCU
        connection was established remains safe to reuse in memory; reconnect
        clears it before another rank can be adopted.
        """
        if not self.live or self.data_root is None:
            self._identity_verification_reason = "LCU endpoint"
            return False
        get_puuid = getattr(self.client, "get_current_puuid", None)
        if not callable(get_puuid):
            self._identity_verification_reason = "LCU endpoint"
            return False
        try:
            active_puuid = get_puuid()
        except LCUError:
            self._identity_verification_reason = "LCU endpoint"
            return False
        if not isinstance(active_puuid, str) or not active_puuid:
            self._identity_verification_reason = "empty identity"
            return False
        try:
            with (self.data_root / "csv" / "current_rank.json").open(
                "r", encoding="utf-8",
            ) as file:
                saved_rank = json.load(file)
        except (OSError, json.JSONDecodeError):
            self._identity_verification_reason = "LCU endpoint"
            return False
        saved_puuid = saved_rank.get("puuid") if isinstance(saved_rank, dict) else None
        if active_puuid != saved_puuid:
            self._identity_verification_reason = "account mismatch"
            return False
        self._verified_account_puuid = active_puuid
        self._identity_verification_reason = None
        return True

    def _retry_identity_verification(self, phase, force=False):
        """Retry the canonical LCU identity endpoint without adopting Rank yet."""
        if (
            not self.live
            or self.data_root is None
            or self._verified_account_puuid is not None
            or phase not in IDENTITY_RETRY_PHASES
        ):
            return False
        if not force:
            now = self.monotonic()
            if now < self._next_identity_retry_at:
                return False
            self._next_identity_retry_at = now + IDENTITY_RETRY_INTERVAL_SECONDS
        if not self._verify_active_account():
            return False
        self._log("[LP] identity verified")
        return True

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
                        self._require_checkpoint()
                        return
                    raise LiveProcessError(f"lp_snapshot.py exited with code {capture.returncode}")

                if len(matches) > 1:
                    self._require_checkpoint()
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

    def _log_finish_skip(self, phase, queue_id):
        """Emit one non-PII explanation when a finish phase cannot trigger."""
        pending = self.pending
        if pending is None or pending.get("finish_skip_diagnostics_logged"):
            return
        pending["finish_skip_diagnostics_logged"] = True
        self._log(
            "[LP] finish trigger skipped: "
            f"phase={phase} queue={queue_id} in_progress={pending['has_reached_in_progress']} "
            f"processing={pending['processing_started']} completed={pending['completed']} "
            f"terminal={pending['terminal']}"
        )

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
        identity_just_verified = self._retry_identity_verification(phase, force=phase != previous)
        if identity_just_verified and self.recheck is not None:
            # Adopt a newly verified pre-game rank immediately instead of
            # waiting for the normal 30-second recheck cadence.
            self._poll_recheck(force=True)
        if queue_id == SOLO_QUEUE_ID and phase in START_PHASES:
            if self.pending is None:
                self._start_pending(phase, queue_id, session_id)
            elif self.pending["terminal"]:
                self._start_pending(phase, queue_id, session_id)
        if queue_id == SOLO_QUEUE_ID and phase == "Matchmaking":
            self._start_recheck()
        if self.pending and phase == "InProgress":
            self.pending["has_reached_in_progress"] = True
            self._end_recheck("game_start")
        if self.pending and phase == "WaitingForStats":
            self._log_waiting_diagnostics(queue_id, session_id)
        if self.pending and phase in FINISH_PHASES:
            can_finish = (
                self.pending["queue_id"] == SOLO_QUEUE_ID
                and self.pending["has_reached_in_progress"]
                and not self.pending["processing_started"]
                and not self.pending["completed"]
                and not self.pending["terminal"]
                and queue_id == SOLO_QUEUE_ID
            )
            if not can_finish:
                self._log_finish_skip(phase, queue_id)
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
                self._verified_account_puuid = None
                self._identity_verification_reason = None
                self._next_identity_retry_at = 0
                self._waiting_logged = False
                self._log("[LCU] client detected")
                self._log("[LCU] connected")
                self._log_rank_diagnostic()
                self._retry_identity_verification("Lobby", force=True)
            phase = self.client.get_gameflow_phase()
            session = self.client.get_gameflow_session()
            self._handle_phase(phase, session)
            self._poll_recheck()
            return phase not in {None, "None"}
        except LCUUnavailable:
            self.client.disconnect()
            self._verified_account_puuid = None
            self._identity_verification_reason = None
            self._next_identity_retry_at = 0
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
