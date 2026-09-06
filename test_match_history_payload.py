"""Regression coverage for lightweight Match History initial payloads."""

import json
import unittest

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
