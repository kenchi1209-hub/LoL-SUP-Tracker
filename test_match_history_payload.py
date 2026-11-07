"""Regression coverage for lightweight Match History initial payloads."""

import json
import tempfile
import unittest
from pathlib import Path

from site_builder import data, render
from site_builder.render import match_history_data


class MatchHistoryPayloadTest(unittest.TestCase):
    def test_initial_history_payload_excludes_lazy_detail_data(self):
        payload = json.loads(match_history_data([{
            "match_id": "JP1_TEST", "date": "2026-09-06 12:00:00",
            "champion": "Leona", "role": "SUP", "_win": True,
            "_k": 1, "_d": 2, "_a": 3, "_cs": 10, "_vs": 20,
            "_dmg": 3000, "queue_id": 420,
        }]))

        self.assertEqual(payload[0]["match_id"], "JP1_TEST")
        self.assertNotIn("detail", payload[0])
        self.assertNotIn("fights", payload[0])
        self.assertNotIn("all_fights", payload[0])

    def test_payload_joins_saved_ranked_lp_delta_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "csv").mkdir()
            (root / "csv" / "lp_history.json").write_text(json.dumps({
                "matches": [
                    {"match_id": "JP1_RANKED", "lp_delta": 18},
                    {"match_id": "JP1_LOSS", "lp_delta": -60},
                    {"match_id": "JP1_ZERO", "lp_delta": 0},
                    {"match_id": "JP1_REMAKE", "lp_delta": -19},
                ],
            }), encoding="utf-8")
            render.configure_data_root(root)
            payload = json.loads(match_history_data([
                {"match_id": "JP1_RANKED", "queue_id": 420, "game_duration_seconds": 600},
                {"match_id": "JP1_LOSS", "queue_id": 420, "game_duration_seconds": 600},
                {"match_id": "JP1_ZERO", "queue_id": 420, "game_duration_seconds": 600},
                {"match_id": "JP1_REMAKE", "queue_id": 420, "game_duration_seconds": 77},
                {"match_id": "JP1_NORMAL", "queue_id": 400},
            ]))
            self.assertEqual([item["lp_delta"] for item in payload], [18, -60, 0, -19, None])
            render.configure_data_root(None)

    def test_short_matches_are_available_only_to_history_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "csv").mkdir()
            (root / "csv" / "my_matches.csv").write_text(
                "match_id,date,game_duration_seconds,win\n"
                "JP1_REMAKE,2026-11-08 01:00:00,66,False\n"
                "JP1_NORMAL,2026-11-08 02:00:00,1004,True\n",
                encoding="utf-8",
            )
            try:
                data.configure_data_root(root)
                self.assertEqual([row["match_id"] for row in data.load_matches()], ["JP1_NORMAL"])
                self.assertEqual(
                    [row["match_id"] for row in data.load_matches(include_short=True)],
                    ["JP1_NORMAL", "JP1_REMAKE"],
                )
            finally:
                data.configure_data_root(None)
