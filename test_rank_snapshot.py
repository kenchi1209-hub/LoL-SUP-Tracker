import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from match_detail_exporter import build_match_details, compact_match
from rank_snapshot import (
    build_snapshot,
    capture_rank_snapshots,
    rank_short,
)
from raw_paths import paths_for_match
from verify_fight_raw_completeness import required_paths


def participant(participant_id, puuid):
    return {
        "participantId": participant_id,
        "puuid": puuid,
        "teamId": 100 if participant_id <= 5 else 200,
        "teamPosition": "UTILITY",
        "championName": "Leona",
    }


def entries(*queue_entries):
    return list(queue_entries)


class RankSnapshotTest(unittest.TestCase):
    def test_snapshot_uses_participant_id_and_run_local_cache(self):
        data = {
            "info": {
                "participants": [
                    participant(participant_id, f"player-{participant_id % 5}")
                    for participant_id in range(1, 11)
                ]
            }
        }
        calls = []

        def fetcher(puuid):
            calls.append(puuid)
            return entries({"queueType": "RANKED_SOLO_5x5", "tier": "SILVER", "rank": "IV"})

        snapshot = build_snapshot("JP1_TEST", data, fetcher, {}, captured_at="2026-08-28T00:00:00Z")

        self.assertEqual(calls, ["player-1", "player-2", "player-3", "player-4", "player-0"])
        self.assertEqual([entry["participantId"] for entry in snapshot["participants"]], list(range(1, 11)))
        self.assertEqual(len(snapshot["participants"]), 10)
        self.assertNotIn("puuid", json.dumps(snapshot))
        self.assertEqual(rank_short(snapshot, 1), "S4")

    def test_solo_flex_and_unavailable_values_are_distinguished(self):
        solo = {"participants": [{"participantId": 1, "fetch_status": "success", "solo": {"tier": "EMERALD", "rank": "II"}, "flex": None}]}
        flex_only = {"participants": [{"participantId": 1, "fetch_status": "success", "solo": None, "flex": {"tier": "GOLD", "rank": "I"}}]}
        failed = {"participants": [{"participantId": 1, "fetch_status": "error", "solo": None, "flex": None}]}
        self.assertEqual(rank_short(solo, 1), "E2")
        self.assertEqual(rank_short(flex_only, 1), "UR")
        self.assertEqual(rank_short(failed, 1), "-")
        self.assertEqual(rank_short(None, 1), "-")

    def test_apex_ranks_are_shortened(self):
        for tier, expected in (("MASTER", "M"), ("GRANDMASTER", "GM"), ("CHALLENGER", "C")):
            snapshot = {"participants": [{"participantId": 1, "fetch_status": "success", "solo": {"tier": tier}, "flex": None}]}
            self.assertEqual(rank_short(snapshot, 1), expected)

    def test_fetch_failure_is_saved_as_unavailable_not_unranked(self):
        data = {"info": {"participants": [participant(1, "bad")]}}
        snapshot = build_snapshot("JP1_TEST", data, lambda _puuid: (_ for _ in ()).throw(requests.ConnectionError()), {})
        self.assertEqual(snapshot["participants"][0]["fetch_status"], "error")
        self.assertEqual(rank_short(snapshot, 1), "-")

    def test_optional_snapshot_exports_public_rank_only(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory) / "raw"
            paths = paths_for_match("JP1_TEST", raw_root)
            paths.directory.mkdir(parents=True)
            paths.detail.write_text(json.dumps({
                "metadata": {"matchId": "JP1_TEST"},
                "info": {"gameDuration": 1800, "participants": [participant(1, "self"), participant(2, "ally")]},
            }), encoding="utf-8")
            paths.rank_snapshot.write_text(json.dumps({
                "match_id": "JP1_TEST", "captured_at": "2026-08-28T00:00:00Z",
                "participants": [
                    {"participantId": 1, "fetch_status": "success", "solo": {"tier": "SILVER", "rank": "IV"}, "flex": None},
                    {"participantId": 2, "fetch_status": "success", "solo": None, "flex": None},
                ],
            }), encoding="utf-8")
            details, failures = build_match_details("self", raw_root)

        self.assertEqual(failures, [])
        public = json.dumps(details)
        self.assertNotIn("puuid", public)
        self.assertNotIn("captured_at", public)
        self.assertEqual([item["rank"] for item in details["JP1_TEST"]["participants"]], ["S4", "UR"])

    def test_kp_and_damage_percentages_are_calculated_per_team(self):
        participants = [
            {**participant(1, "self"), "kills": 2, "assists": 3, "totalDamageDealtToChampions": 100},
            {**participant(2, "ally"), "kills": 8, "assists": 1, "totalDamageDealtToChampions": 300},
            {**participant(6, "enemy"), "kills": 0, "assists": 0, "totalDamageDealtToChampions": 0},
            {**participant(7, "enemy-two"), "kills": 0, "assists": 0, "totalDamageDealtToChampions": 0},
        ]
        compact = compact_match({"info": {"participants": participants}}, "self")
        self.assertEqual(compact["participants"][0]["kp_pct"], 50.0)
        self.assertEqual(compact["participants"][0]["dmg_pct"], 25.0)
        self.assertEqual(compact["participants"][1]["kp_pct"], 90.0)
        self.assertEqual(compact["participants"][1]["dmg_pct"], 75.0)
        self.assertIsNone(compact["participants"][2]["kp_pct"])
        self.assertIsNone(compact["participants"][2]["dmg_pct"])

    def test_capture_only_uses_explicit_new_match_ids_and_keeps_completeness_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory) / "raw"
            paths = paths_for_match("JP1_NEW", raw_root)
            paths.directory.mkdir(parents=True)
            paths.detail.write_text(json.dumps({"info": {"participants": [participant(1, "one")]}},), encoding="utf-8")
            for required in paths.required():
                if required != paths.detail:
                    required.write_text("{}", encoding="utf-8")
            written = capture_rank_snapshots(
                ["JP1_NEW"], raw_root,
                lambda _puuid: entries({"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "I"}),
                captured_at="2026-08-28T00:00:00Z",
            )

            self.assertEqual(written, [paths.rank_snapshot])
            self.assertTrue(paths.rank_snapshot.is_file())
            paths.rank_snapshot.unlink()
            self.assertNotIn(paths.rank_snapshot, required_paths(raw_root, "JP1_NEW"))

    def test_league_api_retries_retry_after(self):
        import riot_api

        response_429 = type("Response", (), {"status_code": 429, "headers": {"Retry-After": "2"}})()
        response_ok = type("Response", (), {"status_code": 200, "headers": {}, "json": lambda self: [], "raise_for_status": lambda self: None})()
        with patch.object(riot_api.requests, "get", side_effect=[response_429, response_ok]), patch.object(riot_api.time, "sleep") as sleep:
            self.assertEqual(riot_api.get_league_entries_by_puuid("puuid"), [])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 0.1])


if __name__ == "__main__":
    unittest.main()
