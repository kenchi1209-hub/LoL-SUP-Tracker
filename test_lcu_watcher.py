import subprocess
import sys
import unittest

from lcu_client import LCUUnavailable
from lcu_watcher import (
    LCUWatcher,
    MATCH_UPDATE_MAX_ATTEMPTS,
    SingleInstanceLock,
    main,
    parse_args,
    queue_id_from_session,
    run_watcher,
    session_id_from_session,
)


class FakeClient:
    def __init__(self, phases=None, sessions=None, ranks=None, unavailable=False):
        self.connected = False
        self.phases = list(phases or [])
        self.sessions = list(sessions or [])
        self.ranks = list(ranks or [])
        self.unavailable = unavailable
        self.disconnects = 0

    def connect(self):
        if self.unavailable:
            raise LCUUnavailable("unavailable")
        self.connected = True

    def disconnect(self):
        self.connected = False
        self.disconnects += 1

    def get_gameflow_phase(self):
        if self.unavailable:
            raise LCUUnavailable("unavailable")
        return self.phases.pop(0) if self.phases else "None"

    def get_gameflow_session(self):
        return self.sessions.pop(0) if self.sessions else None

    def get_solo_rank(self):
        return self.ranks.pop(0) if self.ranks else {"tier": "SILVER", "division": "IV", "leaguePoints": 23, "wins": 41, "losses": 56}


def session(queue_id=None, game_id="test-game-1"):
    queue = {} if queue_id is None else {"id": queue_id}
    game_data = {"queue": queue, "gameMode": "CLASSIC", "gameType": "MATCHED_GAME", "puuid": "hidden"}
    if game_id is not None:
        game_data["gameId"] = game_id
    return {"gameData": game_data}


class FakeLock:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.released = False

    def acquire(self):
        return self.acquired

    def release(self):
        self.released = True


class FakeResult:
    def __init__(self, returncode=0):
        self.returncode = returncode


class RecordingRunner:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        result = self.results.pop(0) if self.results else FakeResult()
        if isinstance(result, BaseException):
            raise result
        return result


class LCUWatcherTest(unittest.TestCase):
    def watcher(self, client):
        self.logs = []
        return LCUWatcher(client=client, emit=self.logs.append, sleeper=lambda _: None)

    def live_watcher(self, client, runner, **kwargs):
        self.logs = []
        watcher = LCUWatcher(
            client=client,
            emit=self.logs.append,
            sleeper=lambda _: None,
            live=True,
            data_root="C:/PrivateData",
            process_runner=runner,
            repo_root="C:/PublicRepo",
            **kwargs,
        )
        watcher._has_rank_after = lambda _match_id: True
        return watcher

    def test_client_unavailable_waits_once_and_discards_credentials(self):
        watcher = self.watcher(FakeClient(unavailable=True))
        watcher.tick()
        watcher.tick()
        self.assertEqual(self.logs.count("[LCU] waiting for client"), 1)
        self.assertFalse(watcher.client.connected)

    def test_none_unknown_and_session_404_are_safe(self):
        watcher = self.watcher(FakeClient(phases=["None", "FuturePhase"], sessions=[None, None]))
        watcher.tick()
        watcher.tick()
        self.assertIn("[LCU] unknown phase: FuturePhase", self.logs)
        self.assertIsNone(watcher.pending)

    def test_queue_parser_safe_skip_and_non_solo_queues(self):
        self.assertIsNone(queue_id_from_session(None))
        self.assertIsNone(session_id_from_session(None))
        self.assertIsNone(session_id_from_session(session(420, game_id=None)))
        self.assertEqual(session_id_from_session(session(420, game_id=123)), "123")
        self.assertIsNone(queue_id_from_session({"gameData": {"queue": {"id": "bad"}}}))
        self.assertEqual(queue_id_from_session(session(400)), 400)
        self.assertEqual(queue_id_from_session(session(440)), 440)

    def test_queue_420_champ_select_starts_pending_once(self):
        watcher = self.watcher(FakeClient(phases=["ChampSelect", "ChampSelect"], sessions=[session(420), session(420)]))
        watcher.tick()
        first = watcher.pending
        watcher.tick()
        self.assertIs(watcher.pending, first)
        self.assertEqual(watcher.pending["queue_id"], 420)
        self.assertEqual(self.logs.count("[LP] pending started"), 1)

    def test_connection_logs_only_safe_rank_diagnostic(self):
        watcher = self.watcher(FakeClient(phases=["None"], sessions=[None]))
        watcher.tick()
        joined = "\n".join(self.logs)
        self.assertIn("[LCU] rank diagnostic: SILVER IV 23LP 41W/56L", joined)
        self.assertNotIn("puuid", joined.lower())

    def test_in_progress_keeps_pending_and_finish_requires_pending(self):
        watcher = self.watcher(FakeClient(phases=["EndOfGame", "InProgress", "WaitingForStats"], sessions=[session(420), session(420), session(420)]))
        watcher.tick()
        self.assertIsNone(watcher.pending)
        watcher.tick()
        self.assertTrue(watcher.pending["has_reached_in_progress"])
        watcher.tick()
        self.assertTrue(watcher.pending["processing_started"])
        self.assertEqual(self.logs.count("[LP] WOULD_RUN_CAPTURE"), 1)

    def test_dry_run_never_uses_subprocess_or_checkpoint(self):
        watcher = self.watcher(FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420), session(420)]))
        watcher.tick()
        watcher.tick()
        self.assertIn("[LP] WOULD_RUN_MATCH_UPDATE", self.logs)
        self.assertNotIn("CHECKPOINT_REQUIRED", self.logs)
        self.assertNotIn("checkpoint", " ".join(self.logs).lower())

    def test_default_cli_is_dry_run_and_live_is_explicit(self):
        self.assertFalse(parse_args([]).live)
        self.assertTrue(parse_args(["--live", "--data-root", "C:/PrivateData"]).live)
        self.assertEqual(main(["--live"]), 1)

    def test_live_requires_pending_and_in_progress_before_waiting_for_stats(self):
        runner = RecordingRunner()
        watcher = self.live_watcher(
            FakeClient(phases=["WaitingForStats", "ChampSelect", "WaitingForStats"], sessions=[session(420)] * 3),
            runner,
        )
        watcher.tick()
        watcher.tick()
        watcher.tick()
        self.assertEqual(runner.calls, [])

    def test_live_session_id_missing_or_mismatch_does_not_block_phase_safe_trigger(self):
        for waiting_game_id in (None, "game-b"):
            runner = RecordingRunner([FakeResult(0), FakeResult(0)])
            watcher = self.live_watcher(
                FakeClient(
                    phases=["ChampSelect", "InProgress", "WaitingForStats"],
                    sessions=[session(420, "game-a"), session(420, "game-a"), session(420, waiting_game_id)],
                ),
                runner,
            )
            watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
            for _ in range(3):
                watcher.tick()
            joined = "\n".join(self.logs)
            self.assertTrue(watcher.pending["completed"])
            self.assertIn("[LP] session id unavailable/mismatch; continuing with phase-safe trigger", joined)
            self.assertNotIn("game-a", joined)
            self.assertNotIn("game-b", joined)

    def test_live_no_session_id_still_triggers_with_phase_continuity(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "WaitingForStats"],
                sessions=[session(420, None), session(420, None), session(420, None)],
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(3):
            watcher.tick()
        self.assertTrue(watcher.pending["completed"])
        self.assertIn("pending_id_present=False", "\n".join(self.logs))

    def test_live_requires_current_queue_420(self):
        runner = RecordingRunner()
        watcher = self.live_watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "WaitingForStats"],
                sessions=[session(420), session(420), session(None)],
            ),
            runner,
        )
        for _ in range(3):
            watcher.tick()
        self.assertEqual(runner.calls, [])

    def test_live_runs_main_then_exact_capture_once_at_waiting_for_stats(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "WaitingForStats", "PreEndOfGame", "EndOfGame", "Lobby"],
                sessions=[session(420)] * 6,
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(6):
            watcher.tick()
        self.assertTrue(watcher.pending["completed"])
        self.assertEqual(len(runner.calls), 2)
        self.assertTrue(runner.calls[0][0][1].endswith("main.py"))
        self.assertTrue(runner.calls[1][0][1].endswith("lp_snapshot.py"))
        self.assertEqual(runner.calls[0][0][0], sys.executable)
        self.assertEqual(runner.calls[1][0][0], sys.executable)
        self.assertFalse(runner.calls[0][1]["shell"])
        self.assertEqual(self.logs.count("[LP] exact capture completed"), 1)

    def test_live_retries_main_when_match_is_not_reflected_then_captures(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2), runner,
        )
        candidates = iter([[], [{"match_id": "JP1_TEST"}]])
        watcher._uncaptured_solo_matches = lambda: next(candidates)
        watcher.tick()
        watcher.tick()
        self.assertEqual(len(runner.calls), 3)
        self.assertIn("[LP] waiting for Match-V5 reflection", self.logs)
        self.assertTrue(watcher.pending["completed"])

    def test_live_match_reflection_retry_is_bounded(self):
        runner = RecordingRunner([FakeResult(0)] * MATCH_UPDATE_MAX_ATTEMPTS)
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2), runner,
        )
        watcher._uncaptured_solo_matches = lambda: []
        watcher.tick()
        watcher.tick()
        self.assertEqual(len(runner.calls), MATCH_UPDATE_MAX_ATTEMPTS)
        self.assertTrue(watcher.pending["failed"])
        self.assertIn("[LP] LIVE PROCESS FAILED: Match-V5 reflection timed out", self.logs)

    def test_live_match_reflection_stops_at_time_limit(self):
        runner = RecordingRunner([FakeResult(0)])
        clock = iter([0, 121])
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2),
            runner,
            monotonic=lambda: next(clock),
        )
        watcher._uncaptured_solo_matches = lambda: []
        watcher.tick()
        watcher.tick()
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(watcher.pending["failed"])

    def test_live_main_failure_or_timeout_never_runs_capture(self):
        for result in (FakeResult(1), subprocess.TimeoutExpired(["python", "main.py"], 300)):
            runner = RecordingRunner([result])
            watcher = self.live_watcher(
                FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2), runner,
            )
            watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
            watcher.tick()
            watcher.tick()
            self.assertEqual(len(runner.calls), 1)
            self.assertTrue(watcher.pending["failed"])
            self.assertFalse(watcher.pending["capture_attempted"])

    def test_live_capture_ambiguous_or_error_never_creates_checkpoint(self):
        for capture_result, expected in ((FakeResult(2), "[LP] CHECKPOINT_REQUIRED"), (FakeResult(1), "[LP] LIVE PROCESS FAILED")):
            runner = RecordingRunner([FakeResult(0), capture_result])
            watcher = self.live_watcher(
                FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2), runner,
            )
            watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
            watcher.tick()
            watcher.tick()
            joined = "\n".join(self.logs)
            self.assertIn(expected, joined)
            self.assertTrue(all("checkpoint" not in " ".join(call[0]).lower() for call in runner.calls))

    def test_live_capture_zero_requires_rank_after_confirmation(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2), runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher._has_rank_after = lambda _match_id: False
        watcher.tick()
        watcher.tick()
        self.assertTrue(watcher.pending["failed"])
        self.assertFalse(watcher.pending["completed"])

    def test_live_unknown_or_non_solo_queue_never_runs_processes(self):
        runner = RecordingRunner()
        watcher = self.live_watcher(
            FakeClient(phases=["ChampSelect", "InProgress", "WaitingForStats"], sessions=[session(440)] * 3), runner,
        )
        for _ in range(3):
            watcher.tick()
        self.assertEqual(runner.calls, [])

    def test_live_backend_continues_after_lcu_disconnect(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(FakeClient(unavailable=True), runner)
        watcher.pending = {
            "processing_started": False,
            "capture_attempted": False,
            "completed": False,
            "failed": False,
            "terminal": False,
            "has_reached_in_progress": True,
            "match_update_attempts": 0,
        }
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher._finish_pending()
        self.assertTrue(watcher.pending["completed"])
        self.assertEqual(len(runner.calls), 2)

    def test_processing_completed_or_terminal_pending_never_retriggers(self):
        for field in ("processing_started", "completed", "terminal"):
            runner = RecordingRunner()
            watcher = self.live_watcher(
                FakeClient(
                    phases=["ChampSelect", "InProgress", "WaitingForStats", "PreEndOfGame", "EndOfGame", "Lobby"],
                    sessions=[session(420)] * 6,
                ),
                runner,
            )
            watcher.tick()
            watcher.tick()
            watcher.pending[field] = True
            for _ in range(4):
                watcher.tick()
            self.assertEqual(runner.calls, [])

    def test_terminal_pending_accepts_next_champ_select_without_session_id_dependency(self):
        watcher = self.watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "WaitingForStats", "ChampSelect"],
                sessions=[session(420, "game-a"), session(420, "game-a"), session(420, "game-a"), session(420, "game-a")],
            )
        )
        for _ in range(4):
            watcher.tick()
        self.assertFalse(watcher.pending["processing_started"])

    def test_run_watcher_announces_mode_once(self):
        watcher = self.watcher(FakeClient())
        watcher.run = lambda: None
        self.assertEqual(run_watcher(watcher, FakeLock()), 0)
        self.assertEqual(self.logs.count("[LP] mode: DRY-RUN"), 1)

    def test_session_diagnostic_is_pii_free(self):
        watcher = self.watcher(FakeClient(phases=["ChampSelect"], sessions=[session(420)]))
        watcher.tick()
        self.assertIn("[LCU] session schema:", "\n".join(self.logs))
        self.assertNotIn("hidden", "\n".join(self.logs))

    def test_intervals_and_keyboard_interrupt_structure(self):
        with self.assertRaises(ValueError):
            LCUWatcher(client=FakeClient(), idle_interval=0)
        calls = []
        watcher = LCUWatcher(client=FakeClient(), emit=calls.append, sleeper=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        watcher.run(max_ticks=1)
        self.assertIn("[LCU] watcher stopped", calls)

    def test_single_instance_lock_has_no_file_state(self):
        lock = SingleInstanceLock()
        self.assertTrue(hasattr(lock, "acquire"))
        self.assertTrue(hasattr(lock, "release"))

    def test_second_watcher_is_rejected_before_monitoring(self):
        watcher = self.watcher(FakeClient())
        lock = FakeLock(acquired=False)
        self.assertEqual(run_watcher(watcher, lock), 2)
        self.assertIn("[LCU] another watcher is already running", self.logs)
        self.assertFalse(lock.released)
