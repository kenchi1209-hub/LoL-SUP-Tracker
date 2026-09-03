import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from lcu_client import (
    LCUClient,
    LCUCredentials,
    LCUError,
    LCUUnavailable,
    find_client,
    find_lockfile,
    read_lockfile,
    session_diagnostic,
)


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class LCUClientTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.client_path = self.root / "LeagueClientUx.exe"
        self.client_path.touch()
        self.lockfile = self.root / "lockfile"
        self.lockfile.write_text("LeagueClient:123:54321:secret-token:https", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_client_not_found(self):
        self.assertIsNone(find_client([]))

    def test_lockfile_parse_and_redacted_repr(self):
        credentials = read_lockfile(self.lockfile)
        self.assertEqual((credentials.pid, credentials.port, credentials.protocol), (123, 54321, "https"))
        self.assertNotIn("secret-token", repr(credentials))

    def test_invalid_lockfile_does_not_echo_contents(self):
        self.lockfile.write_text("bad:secret-token", encoding="utf-8")
        with self.assertRaises(LCUUnavailable) as raised:
            read_lockfile(self.lockfile)
        self.assertNotIn("secret-token", str(raised.exception))

    def test_find_lockfile(self):
        self.assertEqual(find_lockfile(self.client_path), self.lockfile)

    def test_get_uses_loopback_and_never_logs_token(self):
        session = Mock()
        session.get.return_value = Response(200, "None")
        client = LCUClient(process_provider=lambda: [{"ExecutablePath": str(self.client_path)}], session=session)
        client.connect()
        self.assertEqual(client.get_gameflow_phase(), "None")
        url = session.get.call_args.args[0]
        self.assertTrue(url.startswith("https://127.0.0.1:54321/"))
        self.assertEqual(session.get.call_args.kwargs["verify"], False)
        self.assertNotIn("secret-token", repr(client.credentials))

    def test_session_404_is_safe(self):
        session = Mock()
        session.get.return_value = Response(404, None)
        client = LCUClient(process_provider=lambda: [{"ExecutablePath": str(self.client_path)}], session=session)
        client.connect()
        self.assertIsNone(client.get_gameflow_session())

    def test_unknown_path_is_rejected(self):
        client = LCUClient(session=Mock())
        client.credentials = LCUCredentials(1, 2, "secret-token", "https", self.lockfile)
        with self.assertRaises(LCUError):
            client.get("https://example.invalid")

    def test_rank_schema_parse_and_missing_field_safety(self):
        payload = {"queueMap": {"RANKED_SOLO_5x5": {"queueType": "RANKED_SOLO_5x5", "tier": "SILVER", "division": "IV", "leaguePoints": 23, "wins": 41, "losses": 56}}}
        session = Mock()
        session.get.return_value = Response(200, payload)
        client = LCUClient(process_provider=lambda: [{"ExecutablePath": str(self.client_path)}], session=session)
        client.connect()
        self.assertEqual(client.get_solo_rank()["leaguePoints"], 23)
        payload["queueMap"]["RANKED_SOLO_5x5"].pop("wins")
        self.assertIsNone(client.get_solo_rank())

    def test_current_puuid_is_returned_only_to_the_caller(self):
        session = Mock()
        session.get.return_value = Response(200, {"puuid": "runtime-only-puuid"})
        client = LCUClient(process_provider=lambda: [{"ExecutablePath": str(self.client_path)}], session=session)
        client.connect()
        self.assertEqual(client.get_current_puuid(), "runtime-only-puuid")
        session.get.return_value = Response(200, {})
        self.assertIsNone(client.get_current_puuid())

    def test_session_diagnostic_excludes_pii(self):
        session = {"puuid": "hidden", "gameData": {"queue": {"id": 420}, "gameMode": "CLASSIC", "gameType": "MATCHED_GAME", "summonerId": "hidden"}}
        diagnostic = session_diagnostic(session, "ChampSelect")
        self.assertEqual(diagnostic["queue_id"], 420)
        self.assertNotIn("puuid", str(diagnostic))
        self.assertNotIn("summonerId", str(diagnostic))
