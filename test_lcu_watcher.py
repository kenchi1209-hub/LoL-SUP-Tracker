import unittest

from lcu_client import LCUUnavailable
from lcu_watcher import LCUWatcher, SingleInstanceLock, queue_id_from_session, run_watcher


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


def session(queue_id=None):
    queue = {} if queue_id is None else {"id": queue_id}
    return {"gameData": {"queue": queue, "gameMode": "CLASSIC", "gameType": "MATCHED_GAME", "puuid": "hidden"}}


class FakeLock:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.released = False

    def acquire(self):
        return self.acquired

    def release(self):
        self.released = True


class LCUWatcherTest(unittest.TestCase):
    def watcher(self, client):
        self.logs = []
        return LCUWatcher(client=client, emit=self.logs.append, sleeper=lambda _: None)

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
        self.assertTrue(watcher.pending["in_progress"])
        watcher.tick()
        self.assertTrue(watcher.pending["capture_requested"])
        self.assertEqual(self.logs.count("[LP] WOULD_RUN_CAPTURE"), 1)

    def test_dry_run_never_uses_subprocess_or_checkpoint(self):
        watcher = self.watcher(FakeClient(phases=["InProgress", "EndOfGame"], sessions=[session(420), session(420)]))
        watcher.tick()
        watcher.tick()
        self.assertIn("[LP] WOULD_RUN_MATCH_UPDATE", self.logs)
        self.assertNotIn("CHECKPOINT_REQUIRED", self.logs)
        self.assertNotIn("checkpoint", " ".join(self.logs).lower())

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
