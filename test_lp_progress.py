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
        self.root = root
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
        self.assertEqual(match["match_url"], "history.html#match-JP1_EXACT")
        point = next(item for item in self.payload["points"] if item["kind"] == "exact")
        self.assertEqual(point["match_url"], "history.html#match-JP1_EXACT")

    def test_payload_excludes_private_identifiers(self):
        encoded = json.dumps(self.payload).lower()
        for forbidden in ("puuid", "summonerid", "participantid", "accountid", "credential", "token"):
            self.assertNotIn(forbidden, encoded)

    def test_payload_has_only_safe_queue_and_display_metadata(self):
        match = self.payload["matches"][0]
        self.assertEqual(match["queue"], "RANKED_SOLO_5x5")
        self.assertEqual(match["champion_name"], "モルガナ")
        self.assertEqual(self.payload["latest_rank"]["score"], 844)

    def test_missing_recovered_history_keeps_official_payload_compatible(self):
        self.assertIsNone(self.payload["historical"])

    def test_recovered_history_excludes_official_overlap_and_preserves_gaps(self):
        recovered_dir = self.root / "raw" / "lp_progress" / "recovered"
        recovered_dir.mkdir(parents=True)
        records = [
            {"match_id": "JP1_REC_ONE", "game_number": 1, "blitz_timestamp": 1768620000, "tier_after": "BRONZE", "division_after": "III", "lp_after": 10, "candidate_lp_delta": None},
            {"match_id": "JP1_EXACT", "game_number": 2, "blitz_timestamp": 1768623600, "tier_after": "BRONZE", "division_after": "III", "lp_after": 30, "candidate_lp_delta": 20},
            {"match_id": "JP1_REC_THREE", "game_number": 4, "blitz_timestamp": 1768630800, "tier_after": "BRONZE", "division_after": "III", "lp_after": 40, "candidate_lp_delta": None},
            {"match_id": "JP1_REC_FOUR", "game_number": 5, "blitz_timestamp": 1768634400, "tier_after": "BRONZE", "division_after": "III", "lp_after": 60, "candidate_lp_delta": 20},
        ]
        (recovered_dir / "blitz_2026-08-31_reconstructed.json").write_text(json.dumps({
            "source": "blitz", "confidence": "historical_reconstructed", "matches": records,
        }), encoding="utf-8")
        (recovered_dir / "blitz_2026-08-31_match_mapping.json").write_text(json.dumps({
            "mappings": [
                {"games": 1, "status": "exact_match"},
                {"games": 2, "status": "exact_match"},
                {"games": 3, "status": "ambiguous", "timestamp": 1768627200, "evidence": {"reason": "gap"}},
                {"games": 4, "status": "exact_match"},
                {"games": 5, "status": "exact_match"},
            ],
        }), encoding="utf-8")
        rows = self.rows + [
            row("JP1_REC_ONE", "2026-01-17 18:00:00", "Nami", True),
            row("JP1_REC_THREE", "2026-01-17 21:00:00", "Leona", False),
            row("JP1_REC_FOUR", "2026-01-17 22:00:00", "Morgana", True),
        ]
        payload = lp_progress.build_lp_payload(rows, "16.17.1")
        historical = payload["historical"]
        self.assertEqual([point["match_id"] for point in historical["points"]], ["JP1_REC_ONE", "JP1_REC_THREE", "JP1_REC_FOUR"])
        self.assertEqual(historical["overlap_excluded"], 1)
        self.assertEqual(len(historical["gaps"]), 1)
        self.assertEqual([point["segment_id"] for point in historical["points"]], ["historical-0", "historical-1", "historical-1"])
        self.assertEqual(sum(point["candidate_lp_delta"] is not None for point in historical["points"]), 1)
        self.assertTrue(all(point["match_url"].startswith("history.html#match-") for point in historical["points"]))
        official_ids = {point["match_id"] for point in payload["points"] if point["kind"] == "exact"}
        self.assertFalse(official_ids & {point["match_id"] for point in historical["points"]})
        serialized = json.dumps(historical).lower()
        for forbidden in ("puuid", "summonerid", "privateData".lower(), "/users/"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
