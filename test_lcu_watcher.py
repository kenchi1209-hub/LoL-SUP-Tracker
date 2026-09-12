import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lcu_client import LCUError, LCUUnavailable
from lcu_publish import PublishError
from lcu_watcher import (
    GAME_NAME,
    TAG_LINE,
    LCUWatcher,
    MATCH_UPDATE_MAX_ATTEMPTS,
    POLL_FAILURE_LOG_THRESHOLD,
    SESSION_FAILURE_RECONNECT_THRESHOLD,
    SingleInstanceLock,
    WATCHER_LOG_BACKUP_COUNT,
    WATCHER_LOG_MAX_BYTES,
    close_watcher_logger,
    configure_watcher_logger,
    main,
    parse_args,
    queue_id_from_session,
    run_watcher,
    session_id_from_session,
)


class FakeClient:
    def __init__(
        self, phases=None, sessions=None, ranks=None, unavailable=False,
        puuid="test-puuid", puuids=None, riot_id=None, riot_ids=None,
    ):
        self.connected = False
        self.phases = list(phases or [])
        self.sessions = list(sessions or [])
        self.ranks = list(ranks or [])
        self.unavailable = unavailable
        self.puuid = puuid
        self.puuids = list(puuids or [])
        self.riot_id = riot_id if riot_id is not None else (GAME_NAME, TAG_LINE)
        self.riot_ids = list(riot_ids or [])
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
        value = self.phases.pop(0) if self.phases else "None"
        if isinstance(value, BaseException):
            raise value
        return value

    def get_gameflow_session(self):
        value = self.sessions.pop(0) if self.sessions else None
        if isinstance(value, BaseException):
            raise value
        return value

    def get_solo_rank(self):
        return self.ranks.pop(0) if self.ranks else {"tier": "SILVER", "division": "IV", "leaguePoints": 23, "wins": 41, "losses": 56}

    def get_current_puuid(self):
        if self.puuids:
            value = self.puuids.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return self.puuid

    def get_current_riot_id(self):
        if self.riot_ids:
            value = self.riot_ids.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return self.riot_id


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


class FakePublisher:
    def __init__(self, preflight_error=None, publish_error=None):
        self.preflight_error = preflight_error
        self.publish_error = publish_error
        self.calls = []

    def preflight(self):
        self.calls.append("preflight")
        if self.preflight_error:
            raise self.preflight_error

    def publish(self, match_id, correction_match_id=None):
        self.calls.append(
            ("publish", match_id)
            if correction_match_id is None else ("publish", match_id, correction_match_id)
        )
        if self.publish_error:
            raise self.publish_error
        return "commit-sha"

    def publish_unresolved_match_update(self, match_id):
        self.calls.append(("publish_unresolved", match_id))
        if self.publish_error:
            raise self.publish_error
        return "commit-sha"


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

    def test_phase_success_updates_heartbeat_timestamp(self):
        clock = [10]
        watcher = LCUWatcher(
            client=FakeClient(phases=["Lobby"], sessions=[None]),
            emit=lambda _message: None,
            sleeper=lambda _seconds: None,
            monotonic=lambda: clock[0],
        )
        watcher.tick()
        self.assertEqual(watcher.last_successful_phase_read, 10)
        self.assertEqual(watcher.consecutive_poll_failures, 0)

    def test_temporary_lcu_failure_reconnects_and_keeps_active_pending(self):
        client = FakeClient(
            phases=["ChampSelect", LCUUnavailable("temporary"), "InProgress"],
            sessions=[session(420), session(420), session(420)],
        )
        watcher = self.watcher(client)
        watcher.tick()
        original_pending = watcher.pending
        watcher.tick()
        watcher.tick()
        self.assertIs(watcher.pending, original_pending)
        self.assertTrue(watcher.pending["has_reached_in_progress"])
        self.assertGreaterEqual(client.disconnects, 1)
        self.assertIn("[LCU] reconnect succeeded", self.logs)

    def test_session_failure_is_logged_and_reconnects_without_losing_pending(self):
        client = FakeClient(
            phases=["ChampSelect", "InProgress", "InProgress"],
            sessions=[session(420), LCUUnavailable("temporary"), session(420)],
        )
        watcher = self.watcher(client)
        watcher.tick()
        original_pending = watcher.pending
        watcher.tick()
        watcher.tick()
        self.assertIs(watcher.pending, original_pending)
        self.assertIn("[LCU] session read failed: consecutive=1", self.logs)
        self.assertIn("[LCU] reconnect succeeded", self.logs)

    def test_repeated_session_failures_schedule_reconnect_without_losing_pending(self):
        client = FakeClient(
            phases=["ChampSelect"] + ["InProgress"] * (SESSION_FAILURE_RECONNECT_THRESHOLD + 1),
            sessions=[session(420)] + [LCUError("temporary")] * SESSION_FAILURE_RECONNECT_THRESHOLD + [session(420)],
        )
        watcher = self.watcher(client)
        watcher.tick()
        original_pending = watcher.pending
        for _ in range(SESSION_FAILURE_RECONNECT_THRESHOLD + 1):
            watcher.tick()
        self.assertIs(watcher.pending, original_pending)
        self.assertTrue(watcher.pending["has_reached_in_progress"])
        self.assertIn("[LCU] session failure recovery: reconnect scheduled", self.logs)

    def test_heartbeat_recovery_reconnects_after_phase_stalls(self):
        clock = [0]
        client = FakeClient(phases=["Lobby", LCUError("temporary"), "Lobby"], sessions=[None, None])
        self.logs = []
        watcher = LCUWatcher(
            client=client,
            emit=lambda message: self.logs.append(message),
            sleeper=lambda _seconds: None,
            monotonic=lambda: clock[0],
        )
        watcher.tick()
        clock[0] = 1
        watcher.tick()
        clock[0] = 16
        watcher.tick()
        self.assertGreaterEqual(client.disconnects, 1)
        self.assertEqual(watcher.last_successful_phase_read, 16)
        self.assertIn("[LCU] heartbeat recovery: no phase success for 16 seconds", self.logs)
        self.assertIn("[LCU] reconnect succeeded", self.logs)

    def test_poll_failures_log_only_at_meaningful_thresholds(self):
        watcher = self.watcher(FakeClient(phases=[LCUError("one")] * (POLL_FAILURE_LOG_THRESHOLD + 2)))
        for _ in range(POLL_FAILURE_LOG_THRESHOLD + 2):
            watcher.tick()
        failures = [message for message in self.logs if "phase read failed" in message]
        self.assertEqual(len(failures), 2)
        self.assertIn("consecutive=1", failures[0])
        self.assertIn(f"consecutive={POLL_FAILURE_LOG_THRESHOLD}", failures[1])

    def test_persistent_logger_uses_rotation_without_pii(self):
        with tempfile.TemporaryDirectory() as temporary:
            logger = configure_watcher_logger(temporary)
            try:
                handler = logger.handlers[0]
                self.assertEqual(handler.maxBytes, WATCHER_LOG_MAX_BYTES)
                self.assertEqual(handler.backupCount, WATCHER_LOG_BACKUP_COUNT)
                watcher = LCUWatcher(
                    client=FakeClient(phases=["ChampSelect"], sessions=[session(420)]),
                    emit=lambda _message: None,
                    sleeper=lambda _seconds: None,
                    event_logger=logger,
                )
                watcher.tick()
                for handler in logger.handlers:
                    handler.flush()
                log_path = Path(temporary) / "logs" / "lcu_watcher.log"
                contents = log_path.read_text(encoding="utf-8")
                self.assertIn("[LCU] connected", contents)
                self.assertNotIn("hidden", contents)
                self.assertNotIn("puuid", contents.lower())
            finally:
                close_watcher_logger(logger)
            self.assertEqual(logger.handlers, [])

    def test_watcher_logger_reuses_one_handler_and_run_closes_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            logger = configure_watcher_logger(temporary)
            self.assertIs(logger, configure_watcher_logger(temporary))
            self.assertEqual(len(logger.handlers), 1)
            watcher = LCUWatcher(client=FakeClient(), emit=lambda _message: None, event_logger=logger)
            watcher.run = lambda: None
            self.assertEqual(run_watcher(watcher, FakeLock()), 0)
            self.assertEqual(logger.handlers, [])

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

    def test_in_progress_keeps_pending_and_finish_recovery_creates_pending(self):
        watcher = self.watcher(FakeClient(phases=["EndOfGame"], sessions=[session(420)]))
        watcher.tick()
        self.assertTrue(watcher.pending["recovered_finish"])
        self.assertTrue(watcher.pending["terminal"])
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
        self.assertTrue(parse_args(["--live", "--auto-publish", "--data-root", "C:/PrivateData"]).auto_publish)
        self.assertEqual(main(["--live"]), 1)
        self.assertEqual(main(["--auto-publish"]), 1)

    def test_live_requires_pending_and_in_progress_before_waiting_for_stats(self):
        runner = RecordingRunner()
        watcher = self.live_watcher(
            FakeClient(phases=["ChampSelect", "WaitingForStats"], sessions=[session(420)] * 2),
            runner,
        )
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

    def test_live_pre_match_rank_is_used_only_when_lcu_riot_id_matches_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "stale-riot-puuid"}), encoding="utf-8",
            )
            matching = LCUWatcher(
                client=FakeClient(puuid="matching-puuid"), live=True,
                data_root=data_root, emit=lambda _message: None,
            )
            matching._start_pending("ChampSelect", 420, "game")
            self.assertEqual(matching.pending["lcu_before_rank"]["leaguePoints"], 23)

            logs = []
            mismatch = LCUWatcher(
                client=FakeClient(riot_id=("different-name", "different-tag")), live=True,
                data_root=data_root, emit=logs.append,
            )
            mismatch._start_pending("ChampSelect", 420, "game")
            self.assertIsNone(mismatch.pending["lcu_before_rank"])
            self.assertIn("identity verification unavailable: account mismatch", "\n".join(logs))

    def test_trimmed_lcu_riot_id_is_verified_without_using_current_rank_puuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "stale-riot-puuid"}), encoding="utf-8",
            )
            watcher = LCUWatcher(
                client=FakeClient(riot_id=(f" {GAME_NAME} ", f"\t{TAG_LINE}\n")),
                live=True,
                data_root=data_root,
                emit=lambda _message: None,
            )
            watcher._start_pending("ChampSelect", 420, "game")
            self.assertEqual(watcher.pending["lcu_before_rank"]["leaguePoints"], 23)

    def test_riot_id_mismatch_never_passes_a_recheck_snapshot_to_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "saved-puuid"}), encoding="utf-8",
            )
            runner = RecordingRunner([FakeResult(0), FakeResult(0)])
            watcher = LCUWatcher(
                client=FakeClient(
                    phases=["ChampSelect", "InProgress", "WaitingForStats"],
                    sessions=[session(420)] * 3,
                    riot_id=("other-name", "other-tag"),
                ),
                emit=lambda _message: None,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
                process_runner=runner,
                repo_root="C:/PublicRepo",
            )
            watcher._has_rank_after = lambda _match_id: True
            watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
            for _ in range(3):
                watcher.tick()
            capture_command = runner.calls[1][0]
            self.assertNotIn("--next-rank-before-json", capture_command)

    def test_queue_420_recheck_polls_after_cancel_and_adopts_the_latest_rank(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "matching-puuid"}), encoding="utf-8",
            )
            clock = [0]
            client = FakeClient(
                phases=["Matchmaking", "Lobby", "ChampSelect", "InProgress"],
                sessions=[session(420)] * 4,
                ranks=[
                    {"tier": "SILVER", "division": "IV", "leaguePoints": 50, "wins": 46, "losses": 60},
                    {"tier": "SILVER", "division": "IV", "leaguePoints": 69, "wins": 46, "losses": 60},
                ],
            )
            client.connected = True
            logs = []
            watcher = LCUWatcher(
                client=client,
                emit=logs.append,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
                monotonic=lambda: clock[0],
            )
            with patch(
                "lcu_watcher.reconcile_previous_rank_after",
                side_effect=[
                    {"status": "confirmed", "changed": False},
                    {"status": "corrected", "changed": False, "match_id": "JP1_PREVIOUS"},
                ],
            ) as preview, patch("lcu_watcher.HEARTBEAT_TIMEOUT_SECONDS", 999):
                watcher.tick()
                clock[0] = 31
                watcher.tick()
                watcher.tick()
                watcher.tick()
            self.assertEqual(preview.call_count, 2)
            self.assertEqual(watcher.pending["lcu_before_rank"]["leaguePoints"], 69)
            self.assertIsNone(watcher.recheck)
            joined = "\n".join(logs)
            self.assertIn("recheck session started", joined)
            self.assertIn("post-match correction candidate detected", joined)
            self.assertIn("recheck session ended: game_start", joined)

    def test_recheck_reuses_startup_verified_account_when_summoner_is_transiently_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "matching-puuid"}), encoding="utf-8",
            )
            logs = []
            client = FakeClient(
                phases=["Matchmaking"],
                sessions=[session(420)],
                riot_ids=[(GAME_NAME, TAG_LINE), None],
            )
            watcher = LCUWatcher(
                client=client,
                emit=logs.append,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
            )
            watcher.tick()
            self.assertEqual(watcher.recheck["latest_rank"]["leaguePoints"], 23)
            joined = "\n".join(logs)
            self.assertIn("recheck rank adopted: SILVER IV 23LP 41W/56L", joined)
            self.assertNotIn("recheck rank not adopted", joined)

    def test_identity_retries_on_each_safe_pre_game_phase(self):
        for phase in ("Lobby", "Matchmaking", "ReadyCheck", "ChampSelect"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                data_root = Path(temporary)
                (data_root / "csv").mkdir()
                (data_root / "csv" / "current_rank.json").write_text(
                    json.dumps({"puuid": "matching-puuid"}), encoding="utf-8",
                )
                logs = []
                client = FakeClient(
                    phases=[phase], sessions=[session(420)],
                )
                client.connected = True
                watcher = LCUWatcher(
                    client=client,
                    emit=logs.append,
                    sleeper=lambda _seconds: None,
                    live=True,
                    data_root=data_root,
                )
                watcher.tick()
                self.assertEqual(watcher._verified_account_riot_id, (GAME_NAME, TAG_LINE))
                self.assertIn("[LP] identity verified", logs)

    def test_identity_can_recover_during_queue_poll_and_adopts_latest_rank_before_game_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "matching-puuid"}), encoding="utf-8",
            )
            clock = [0]
            logs = []
            client = FakeClient(
                phases=["Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"],
                sessions=[session(420)] * 5,
                ranks=[
                    {"tier": "SILVER", "division": "IV", "leaguePoints": 19, "wins": 58, "losses": 75},
                    {"tier": "SILVER", "division": "IV", "leaguePoints": 19, "wins": 58, "losses": 75},
                    {"tier": "SILVER", "division": "IV", "leaguePoints": 19, "wins": 58, "losses": 75},
                ],
                riot_ids=[LCUUnavailable("startup"), LCUUnavailable("lobby"), LCUUnavailable("matchmaking"), LCUUnavailable("poll"), (GAME_NAME, TAG_LINE)],
            )
            watcher = LCUWatcher(
                client=client,
                emit=logs.append,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
                monotonic=lambda: clock[0],
            )
            with patch("lcu_watcher.reconcile_previous_rank_after", return_value={"status": "confirmed"}):
                for _ in range(5):
                    watcher.tick()
            self.assertEqual(watcher.pending["lcu_before_rank"]["leaguePoints"], 19)
            joined = "\n".join(logs)
            self.assertIn("[LP] identity verified", joined)
            self.assertIn("[LP] recheck rank adopted: SILVER IV 19LP 58W/75L", joined)

    def test_recheck_rejects_rank_when_current_account_does_not_match_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "saved-puuid"}), encoding="utf-8",
            )
            logs = []
            client = FakeClient(
                phases=["Matchmaking"], sessions=[session(420)], riot_id=("other-name", "other-tag"),
            )
            client.connected = True
            watcher = LCUWatcher(
                client=client,
                emit=logs.append,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
            )
            watcher.tick()
            self.assertIsNone(watcher.recheck["latest_rank"])
            self.assertIn(
                "[LP] recheck rank not adopted: account mismatch", logs,
            )

    def test_recheck_identity_failure_reasons_are_non_pii(self):
        cases = (
            (LCUUnavailable("endpoint"), "LCU endpoint"),
            (None, "empty identity"),
            (("", "tag"), "empty identity"),
            (("different-name", "different-tag"), "account mismatch"),
        )
        for active_riot_id, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                data_root = Path(temporary)
                (data_root / "csv").mkdir()
                (data_root / "csv" / "current_rank.json").write_text(
                    json.dumps({"puuid": "saved-puuid"}), encoding="utf-8",
                )
                logs = []
                client = FakeClient(
                    phases=["Matchmaking"], sessions=[session(420)],
                    riot_ids=[active_riot_id, active_riot_id],
                )
                client.connected = True
                watcher = LCUWatcher(
                    client=client,
                    emit=logs.append,
                    sleeper=lambda _seconds: None,
                    live=True,
                    data_root=data_root,
                )
                watcher.tick()
                joined = "\n".join(logs)
                self.assertIn(f"identity verification unavailable: {reason}", joined)
                self.assertIn(f"recheck rank not adopted: {reason}", joined)
                self.assertNotIn("saved-puuid", joined)
                self.assertNotIn("different-name", joined)

    def test_recheck_ignores_other_queues_does_not_duplicate_and_expires(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "csv").mkdir()
            (data_root / "csv" / "current_rank.json").write_text(
                json.dumps({"puuid": "matching-puuid"}), encoding="utf-8",
            )
            clock = [0]
            client = FakeClient(
                phases=["Matchmaking", "Matchmaking", "Matchmaking"],
                sessions=[session(400), session(420), session(420)],
                puuid="matching-puuid",
            )
            client.connected = True
            watcher = LCUWatcher(
                client=client,
                emit=lambda _message: None,
                sleeper=lambda _seconds: None,
                live=True,
                data_root=data_root,
                monotonic=lambda: clock[0],
            )
            with patch("lcu_watcher.reconcile_previous_rank_after", return_value={"status": "confirmed"}):
                watcher.tick()
                self.assertIsNone(watcher.recheck)
                watcher.tick()
                original = watcher.recheck
                watcher.tick()
                self.assertIs(watcher.recheck, original)
                clock[0] = 301
                watcher._poll_recheck()
            self.assertIsNone(watcher.recheck)

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

    def test_end_of_game_is_a_phase_safe_fallback_finish_trigger(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "PreEndOfGame", "EndOfGame"],
                sessions=[session(420)] * 4,
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(4):
            watcher.tick()
        self.assertTrue(watcher.pending["completed"])
        self.assertEqual(self.logs.count("[LP] ranked finished"), 1)
        self.assertEqual(len(runner.calls), 2)

    def test_waiting_for_stats_then_end_of_game_runs_once(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "PreEndOfGame", "WaitingForStats", "EndOfGame"],
                sessions=[session(420)] * 5,
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(5):
            watcher.tick()
        self.assertEqual(self.logs.count("[LP] ranked finished"), 1)
        self.assertEqual(len(runner.calls), 2)

    def test_finish_recovery_requires_queue_420_and_preend_never_triggers(self):
        cases = (
            (["PreEndOfGame"], [session(420)]),
            (["WaitingForStats"], [session(400)]),
            (["EndOfGame"], [session(None)]),
        )
        for phases, sessions in cases:
            watcher = self.watcher(FakeClient(phases=phases, sessions=sessions))
            for _ in phases:
                watcher.tick()
            self.assertNotIn("[LP] ranked finished", self.logs)

    def test_finish_recovery_safely_processes_one_candidate(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(phases=["WaitingForStats", "EndOfGame"], sessions=[session(420)] * 2),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher.tick()
        watcher.tick()
        self.assertTrue(watcher.pending["recovered_finish"])
        self.assertTrue(watcher.pending["completed"])
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(self.logs.count("[LP] ranked finished"), 1)

    def test_finish_recovery_requires_checkpoint_for_multiple_candidates(self):
        runner = RecordingRunner([FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(phases=["EndOfGame"], sessions=[session(420)]), runner,
        )
        watcher._uncaptured_solo_matches = lambda: [
            {"match_id": "JP1_FIRST"}, {"match_id": "JP1_SECOND"},
        ]
        watcher.tick()
        self.assertTrue(watcher.pending["checkpoint_required"])
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("[LP] CHECKPOINT_REQUIRED", self.logs)

    def test_repeated_end_of_game_and_lobby_none_never_retrigger(self):
        watcher = self.watcher(
            FakeClient(
                phases=["ChampSelect", "InProgress", "PreEndOfGame", "EndOfGame", "EndOfGame", "Lobby", "None"],
                sessions=[session(420)] * 6 + [None],
            )
        )
        for _ in range(7):
            watcher.tick()
        self.assertTrue(watcher.pending["terminal"])
        self.assertEqual(self.logs.count("[LP] ranked finished"), 1)
        self.assertEqual(self.logs.count("[LP] WOULD_RUN_CAPTURE"), 1)

    def test_auto_publish_runs_only_after_exact_capture(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        publisher = FakePublisher()
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2),
            runner,
            auto_publish=True,
            publisher=publisher,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher.tick()
        watcher.tick()
        self.assertEqual(publisher.calls, ["preflight", ("publish", "JP1_TEST")])
        self.assertTrue(watcher.pending["published"])
        self.assertIn("[DONE] automatic publish complete", self.logs)

    def test_auto_publish_allows_only_the_capture_declared_previous_correction(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(0)])
        publisher = FakePublisher()
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2),
            runner,
            auto_publish=True,
            publisher=publisher,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher._correction_match_id = lambda _match_id: "JP1_PREVIOUS"
        watcher.tick()
        watcher.tick()
        self.assertEqual(
            publisher.calls,
            ["preflight", ("publish", "JP1_TEST", "JP1_PREVIOUS")],
        )

    def test_auto_publish_checkpoint_publishes_only_unresolved_match_data(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(2)])
        publisher = FakePublisher()
        watcher = self.live_watcher(
            FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2),
            runner,
            auto_publish=True,
            publisher=publisher,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        watcher._has_rank_after = lambda _match_id: False
        watcher.tick()
        watcher.tick()
        self.assertEqual(
            publisher.calls,
            ["preflight", ("publish_unresolved", "JP1_TEST")],
        )
        self.assertTrue(watcher.pending["checkpoint_required"])
        self.assertTrue(watcher.pending["completed"])
        self.assertTrue(watcher.pending["published"])
        joined = "\n".join(self.logs)
        self.assertIn("checkpoint required; match data will be published without LP allocation", joined)
        self.assertIn("unresolved match data published", joined)

    def test_auto_publish_checkpoint_refuses_rank_after_or_lp_history_mutation(self):
        for rank_after, history in ((True, (None, None)), (False, (b"before", b"after"))):
            with self.subTest(rank_after=rank_after, history=history):
                runner = RecordingRunner([FakeResult(0), FakeResult(2)])
                publisher = FakePublisher()
                watcher = self.live_watcher(
                    FakeClient(phases=["InProgress", "WaitingForStats"], sessions=[session(420)] * 2),
                    runner,
                    auto_publish=True,
                    publisher=publisher,
                )
                watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
                watcher._has_rank_after = lambda _match_id, value=rank_after: value
                values = iter(history)
                watcher._lp_history_bytes = lambda: next(values)
                watcher.tick()
                watcher.tick()
                self.assertEqual(publisher.calls, ["preflight"])
                self.assertTrue(watcher.pending["failed"])

    def test_auto_publish_preflight_or_trigger_failure_stops_without_retrigger(self):
        for publisher in (FakePublisher(preflight_error=PublishError("remote main is ahead")), FakePublisher(publish_error=PublishError("trigger failed"))):
            runner = RecordingRunner([FakeResult(0), FakeResult(0)])
            watcher = self.live_watcher(
                FakeClient(phases=["InProgress", "WaitingForStats", "WaitingForStats"], sessions=[session(420)] * 3),
                runner,
                auto_publish=True,
                publisher=publisher,
            )
            watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
            for _ in range(3):
                watcher.tick()
            self.assertTrue(watcher.pending["failed"])
            self.assertEqual(publisher.calls.count(("publish", "JP1_TEST")), 1 if len(publisher.calls) > 1 else 0)

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
        clock = iter([0, 0, 0, 0, 121])
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

    def test_checkpoint_required_terminalizes_old_pending_and_next_ranked_finishes_once(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(2), FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=[
                    "ChampSelect", "InProgress", "WaitingForStats",
                    "ChampSelect", "InProgress", "WaitingForStats", "EndOfGame", "Lobby",
                ],
                sessions=[session(420)] * 8,
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(8):
            watcher.tick()
        self.assertEqual(self.logs.count("[LP] ranked finished"), 2)
        self.assertEqual(self.logs.count("[LP] CHECKPOINT_REQUIRED"), 1)
        self.assertTrue(watcher.checkpoint_pending["terminal"])
        self.assertTrue(watcher.checkpoint_pending["checkpoint_required"])
        self.assertIsNot(watcher.pending, watcher.checkpoint_pending)
        self.assertTrue(watcher.pending["completed"])
        self.assertEqual(len(runner.calls), 4)

    def test_checkpoint_required_next_ranked_uses_end_of_game_fallback_once(self):
        runner = RecordingRunner([FakeResult(0), FakeResult(2), FakeResult(0), FakeResult(0)])
        watcher = self.live_watcher(
            FakeClient(
                phases=[
                    "ChampSelect", "InProgress", "WaitingForStats",
                    "ChampSelect", "InProgress", "PreEndOfGame", "EndOfGame", "Lobby",
                ],
                sessions=[session(420)] * 8,
            ),
            runner,
        )
        watcher._uncaptured_solo_matches = lambda: [{"match_id": "JP1_TEST"}]
        for _ in range(8):
            watcher.tick()
        self.assertEqual(self.logs.count("[LP] ranked finished"), 2)
        self.assertEqual(len(runner.calls), 4)

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
            self.assertIn("[LP] finish trigger skipped:", "\n".join(self.logs))

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
