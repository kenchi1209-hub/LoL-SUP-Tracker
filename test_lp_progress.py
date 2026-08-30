"""Regression tests for the public-safe LP Progress payload."""

import json
import tempfile
import unittest
from pathlib import Path

from site_builder import lp_progress


def row(match_id, date, champion, win):
    return {
        "match_id": match_id,
        "date": date,
        "champion": champion,
        "patch": "16.17.810.4348",
        "_win": win,
    }


class LPProgressPayloadTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "csv").mkdir()
        self.history_path = root / "csv" / "lp_history.json"
        self.history_path.write_text(json.dumps({
            "schema_version": 1,
            "queue_type": "RANKED_SOLO_5x5",
            "baseline": {
                "captured_at_jst": "2026-08-29T00:42:35+09:00", "tier": "SILVER",
                "division": "IV", "lp": 23, "wins": 40, "losses": 55,
                "confidence": "baseline", "segment_id": "segment-0",
            },
            "checkpoints": [{
                "snapshot_id": "checkpoint-1", "captured_at_jst": "2026-08-29T03:33:11+09:00",
                "tier": "SILVER", "division": "IV", "lp": 23, "wins": 41,
                "losses": 56, "confidence": "checkpoint", "segment_id": "segment-1",
                "gap": {"games": 2, "wins": 1, "losses": 1, "match_ids": ["JP1_GAP1", "JP1_GAP2"]},
            }],
            "matches": [
                {"match_id": "JP1_EXACT", "game_datetime_jst": "2026-08-30T22:36:56+09:00", "patch": "16.17", "champion": "Braum", "win": True, "queue": "RANKED_SOLO_5x5", "tier_before": "SILVER", "division_before": "IV", "lp_before": 23, "tier_after": "SILVER", "division_after": "IV", "lp_after": 44, "lp_delta": 21, "confidence": "exact", "segment_id": "segment-1"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        lp_progress.configure_data_root(root)
        self.rows = [
            row("JP1_GAP1", "2026-08-29 02:03:55", "Morgana", False),
            row("JP1_GAP2", "2026-08-29 02:28:36", "Braum", True),
            row("JP1_EXACT", "2026-08-30 22:36:56", "Braum", True),
        ]
        self.payload = lp_progress.build_lp_payload(self.rows, "16.17.1")

    def tearDown(self):
        lp_progress.configure_data_root(None)
        self.temporary.cleanup()

    def test_baseline_checkpoint_and_exact_points_keep_segments(self):
        self.assertEqual(self.payload["baseline"]["score"], 823)
        self.assertEqual(self.payload["checkpoints"][0]["segment_id"], "segment-1")
        self.assertEqual(self.payload["points"][-1]["score"], 844)
        self.assertEqual(self.payload["points"][-1]["segment_id"], "segment-1")

    def test_gap_is_preserved_without_a_fake_lp_delta(self):
        gap_matches = [item for item in self.payload["matches"] if item["source"] == "gap"]
        self.assertEqual(len(gap_matches), 2)
        self.assertTrue(all(item["lp_delta"] is None for item in gap_matches))
        self.assertEqual(self.payload["checkpoints"][0]["gap"]["wins"], 1)

    def test_ambiguous_matches_have_no_assignable_lp_delta(self):
        gap_matches = [item for item in self.payload["matches"] if item["source"] == "gap"]
        self.assertTrue(all(item["lp_delta"] is None for item in gap_matches))

    def test_overall_match_inputs_include_gap_matches(self):
        self.assertEqual(len(self.payload["matches"]), 3)
        self.assertEqual(sum(item["win"] for item in self.payload["matches"]), 2)

    def test_exact_match_has_before_after_and_continuous_scores(self):
        match = next(item for item in self.payload["matches"] if item["source"] == "exact")
        self.assertEqual(match["before"]["score"], 823)
        self.assertEqual(match["after"]["score"], 844)
        self.assertEqual(match["lp_delta"], 21)

    def test_payload_excludes_private_identifiers(self):
        encoded = json.dumps(self.payload).lower()
        for forbidden in ("puuid", "summonerid", "participantid", "accountid", "credential", "token"):
            self.assertNotIn(forbidden, encoded)

    def test_payload_has_only_safe_queue_and_display_metadata(self):
        match = self.payload["matches"][0]
        self.assertEqual(match["queue"], "RANKED_SOLO_5x5")
        self.assertEqual(match["champion_name"], "モルガナ")
        self.assertEqual(self.payload["latest_rank"]["score"], 844)


if __name__ == "__main__":
    unittest.main()
