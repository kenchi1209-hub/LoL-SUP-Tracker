"""Windows LCU watcher MVP. It only observes; it never captures or writes LP data."""

import argparse
import ctypes
import os
import time

from lcu_client import LCUError, LCUUnavailable, LCUClient, session_diagnostic
from timezone_utils import now_jst


SOLO_QUEUE_ID = 420
START_PHASES = {"ChampSelect", "InProgress"}
FINISH_PHASES = {"WaitingForStats", "PreEndOfGame", "EndOfGame"}
KNOWN_PHASES = {
    "None", "Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "InProgress",
    "WaitingForStats", "PreEndOfGame", "EndOfGame",
}


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


class LCUWatcher:
    def __init__(self, client=None, emit=print, sleeper=time.sleep, idle_interval=3, active_interval=1):
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

    def _log(self, message):
        self.emit(message)

    def _start_pending(self, phase, queue_id):
        before = self.client.get_solo_rank()
        self.pending = {
            "detected_at_jst": now_jst().replace(microsecond=0).isoformat(),
            "start_phase": phase,
            "queue_id": queue_id,
            "lcu_before_rank": before,
            "capture_requested": False,
            "in_progress": phase == "InProgress",
        }
        self._log("[LP] solo ranked detected")
        self._log("[LP] pending started")

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
        if queue_id is not None and phase != previous:
            self._log(f"[LCU] queue: {queue_id}")
        if queue_id == SOLO_QUEUE_ID and phase in START_PHASES and self.pending is None:
            self._start_pending(phase, queue_id)
        if self.pending and phase == "InProgress":
            self.pending["in_progress"] = True
        if (
            self.pending
            and self.pending["in_progress"]
            and phase in FINISH_PHASES
            and not self.pending["capture_requested"]
        ):
            self.pending["capture_requested"] = True
            self._log("[LP] ranked finished")
            self._log("[LP] WOULD_RUN_MATCH_UPDATE")
            self._log("[LP] WOULD_RUN_CAPTURE")

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
    parser.add_argument("--data-root", help="Reserved for future live-mode integration")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Observe only (default)")
    return parser.parse_args(argv)


def run_watcher(watcher, lock):
    """Run one watcher instance, returning 2 when its named mutex is already held."""
    if not lock.acquire():
        watcher._log("[LCU] another watcher is already running")
        return 2
    try:
        watcher.run()
    finally:
        lock.release()
    return 0


def main(argv=None):
    parse_args(argv)  # The MVP intentionally never launches update or capture subprocesses.
    return run_watcher(LCUWatcher(), SingleInstanceLock())


if __name__ == "__main__":
    raise SystemExit(main())
