"""Regression tests for the public-safe LP Progress payload."""

import json
import tempfile
import unittest
from pathlib import Path

from site_builder import lp_progress


def row(match_id, date, champion, win, kills=1, deaths=2, assists=3, team_kills=10,
        vision_score=70, vision_score_per_min=2.33, game_duration_seconds=0):
    return {
        "match_id": match_id,
        "date": date,
        "champion": champion,
        "patch": "16.17.810.4348",
        "_win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "team_kills": team_kills,
        "vision_score": vision_score,
        "vision_score_per_min": vision_score_per_min,
        "game_duration_seconds": game_duration_seconds,
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
        self.assertEqual([item["match_id"] for item in self.payload["usable_matches"]], ["JP1_EXACT"])
        self.assertFalse({"JP1_GAP1", "JP1_GAP2"} & {item["match_id"] for item in self.payload["usable_matches"]})
        self.assertEqual(self.payload["usable_summary"]["net_lp"], 21)
        usable = self.payload["usable_matches"][0]
        self.assertEqual((usable["kills"], usable["deaths"], usable["assists"]), (1, 2, 3))
        self.assertEqual(usable["kp_pct"], 40.0)
        self.assertEqual(usable["vision_score"], 70.0)
        self.assertEqual(usable["vision_score_per_min"], 2.33)

    def test_latest_exact_rank_after_record_overrides_stale_history_record(self):
        snapshot = self.root / "raw" / "JP1_EXACT" / "rank_after.json"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(json.dumps({
            "after": {"tier": "SILVER", "division": "IV", "lp": 44, "wins": 41, "losses": 56},
        }), encoding="utf-8")

        payload = lp_progress.build_lp_payload(self.rows, "16.17.1")

        self.assertEqual(payload["latest_rank"], {"tier": "SILVER", "division": "IV", "lp": 44, "score": 844})
        self.assertEqual(payload["usable_summary"]["record"], {"wins": 41, "losses": 56, "known": 1})
        exact_point = next(item for item in payload["points"] if item.get("match_id") == "JP1_EXACT")
        self.assertEqual(exact_point["game_number"], 97)

    def test_exact_point_without_verified_sequence_remains_unresolved(self):
        exact_point = next(item for item in self.payload["points"] if item.get("match_id") == "JP1_EXACT")
        self.assertIsNone(exact_point["game_number"])

    def test_recovered_history_excludes_official_overlap_and_preserves_gaps(self):
        recovered_dir = self.root / "raw" / "lp_progress" / "recovered"
        recovered_dir.mkdir(parents=True)
        records = [
            {"match_id": "JP1_REC_ONE", "game_number": 1, "blitz_timestamp": 1768620000, "tier_after": "BRONZE", "division_after": "III", "lp_after": 10, "wins_after": 1, "losses_after": 0, "candidate_lp_delta": None},
            {"match_id": "JP1_EXACT", "game_number": 2, "blitz_timestamp": 1768623600, "tier_after": "BRONZE", "division_after": "III", "lp_after": 30, "wins_after": 2, "losses_after": 0, "candidate_lp_delta": 20},
            {"match_id": "JP1_REC_THREE", "game_number": 4, "blitz_timestamp": 1768630800, "tier_after": "BRONZE", "division_after": "III", "lp_after": 40, "wins_after": 2, "losses_after": 2, "candidate_lp_delta": None},
            {"match_id": "JP1_REC_FOUR", "game_number": 5, "blitz_timestamp": 1768634400, "tier_after": "BRONZE", "division_after": "III", "lp_after": 60, "wins_after": 3, "losses_after": 2, "candidate_lp_delta": 20},
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
            row("JP1_REC_ONE", "2026-01-17 18:00:00", "Nami", True, 2, 0, 4),
            row("JP1_REC_THREE", "2026-01-17 21:00:00", "Leona", False, 0, 3, 5),
            row("JP1_REC_FOUR", "2026-01-17 22:00:00", "Morgana", True, 1, 2, 8),
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
        usable = payload["usable_matches"]
        self.assertEqual([item["game_number"] for item in usable], [1, 2, 4, 5])
        self.assertEqual(len({item["match_id"] for item in usable}), 4)
        official = next(item for item in usable if item["match_id"] == "JP1_EXACT")
        self.assertEqual(official["source"], "exact")
        self.assertEqual(official["lp_delta"], 21)
        self.assertEqual(payload["usable_summary"]["record"], {"wins": 3, "losses": 2, "known": 4})
        self.assertEqual(payload["usable_summary"]["games_tracked"], 4)
        self.assertEqual(payload["usable_summary"]["games_total"], 5)
        self.assertEqual(payload["usable_summary"]["net_lp"], 41)
        self.assertEqual(payload["usable_summary"]["lp_available"], 2)
        self.assertEqual(payload["latest_rank"], official["after"])
        recovered_usable = next(item for item in usable if item["match_id"] == "JP1_REC_ONE")
        self.assertEqual((recovered_usable["kills"], recovered_usable["deaths"], recovered_usable["assists"]), (2, 0, 4))
        self.assertEqual(recovered_usable["kp_pct"], 60.0)
        serialized = json.dumps(historical).lower()
        for forbidden in ("puuid", "summonerid", "privateData".lower(), "/users/"):
            self.assertNotIn(forbidden, serialized)

    def test_verified_mobalytics_match_resolves_only_its_historical_gap(self):
        recovered_dir = self.root / "raw" / "lp_progress" / "recovered"
        recovered_dir.mkdir(parents=True)
        (recovered_dir / "blitz_2026-08-31_reconstructed.json").write_text(json.dumps({
            "source": "blitz", "confidence": "historical_reconstructed", "matches": [
                {"match_id": "JP1_LEFT", "game_number": 10, "blitz_timestamp": 1768620000, "tier_after": "BRONZE", "division_after": "II", "lp_after": 10, "wins_after": 4, "losses_after": 6},
                {"match_id": "JP1_RIGHT", "game_number": 12, "blitz_timestamp": 1768630800, "tier_after": "BRONZE", "division_after": "II", "lp_after": 29, "wins_after": 5, "losses_after": 7},
            ],
        }), encoding="utf-8")
        (recovered_dir / "blitz_2026-08-31_match_mapping.json").write_text(json.dumps({
            "mappings": [{"games": 11, "status": "ambiguous", "timestamp": 1768623600, "evidence": {"reason": "gap"}}],
        }), encoding="utf-8")
        (recovered_dir / "mobalytics_historical.json").write_text(json.dumps({
            "source": "mobalytics", "confidence": "mobalytics_historical_verified", "matches": [{
                "match_id": "JP1_MOBA", "game_number": 11, "game_datetime_jst": "2026-01-17T22:00:00+09:00",
                "tier_after": "BRONZE", "division_after": "II", "lp_after": 39,
                "wins_after": 5, "losses_after": 6, "lp_delta": 29,
                "source": "mobalytics_historical", "confidence": "mobalytics_historical_verified",
            }],
        }), encoding="utf-8")
        rows = self.rows + [
            row("JP1_LEFT", "2026-01-17 20:00:00", "Nami", True),
            row("JP1_MOBA", "2026-01-17 22:00:00", "Janna", True),
            row("JP1_RIGHT", "2026-01-18 00:00:00", "Morgana", False),
        ]

        payload = lp_progress.build_lp_payload(rows, "16.17.1")
        historical = payload["historical"]
        mobalytics = next(point for point in historical["points"] if point["match_id"] == "JP1_MOBA")

        self.assertEqual(mobalytics["game_number"], 11)
        self.assertEqual(mobalytics["rank"]["score"], 639)
        self.assertEqual(mobalytics["lp_delta"], 29)
        self.assertEqual(mobalytics["source"], "mobalytics_historical")
        self.assertEqual(mobalytics["confidence"], "mobalytics_historical_verified")
        self.assertFalse(any(gap["game_number"] == 11 for gap in historical["gaps"]))
        self.assertEqual([point["segment_id"] for point in historical["points"]], ["historical-0"] * 3)

    def test_historical_gap_keeps_missing_games_out_of_points_and_summary(self):
        recovered_dir = self.root / "raw" / "lp_progress" / "recovered"
        recovered_dir.mkdir(parents=True)
        (recovered_dir / "blitz_2026-08-31_reconstructed.json").write_text(json.dumps({
            "source": "blitz", "confidence": "historical_reconstructed", "matches": [
                {"match_id": "JP1_LEFT", "game_number": 6, "blitz_timestamp": 1768620000, "tier_after": "BRONZE", "division_after": "III", "lp_after": 86, "wins_after": 2, "losses_after": 4, "candidate_lp_delta": 26},
                {"match_id": "JP1_RIGHT", "game_number": 9, "blitz_timestamp": 1768630800, "tier_after": "BRONZE", "division_after": "III", "lp_after": 82, "wins_after": 3, "losses_after": 6},
            ],
        }), encoding="utf-8")
        (recovered_dir / "blitz_2026-08-31_match_mapping.json").write_text(json.dumps({
            "mappings": [{"games": 8, "status": "ambiguous", "timestamp": 1768623600, "evidence": {"reason": "gap"}}],
        }), encoding="utf-8")
        rows = self.rows + [
            row("JP1_LEFT", "2026-01-17 20:00:00", "Nami", True),
            row("JP1_RIGHT", "2026-01-18 00:00:00", "Janna", False),
        ]

        payload = lp_progress.build_lp_payload(rows, "16.17.1")
        historical = payload["historical"]

        self.assertEqual([point["game_number"] for point in historical["points"]], [6, 9])
        self.assertEqual([gap["game_number"] for gap in historical["gaps"]], [8])
        self.assertEqual(payload["usable_summary"]["games_tracked"], 2)
        self.assertEqual(payload["usable_summary"]["lp_available"], 2)

    def test_official_bridge_gets_game_numbers_only_when_record_sequence_matches(self):
        historical = [
            {"match_id": "LEFT", "game_number": 6, "wins_after": 3, "losses_after": 3},
            {"match_id": "RIGHT", "game_number": 8, "wins_after": 2, "losses_after": 6},
        ]
        exact = [
            {"match_id": "LEFT", "win": False},
            {"match_id": "MIDDLE", "win": True},
            {"match_id": "RIGHT", "win": False},
        ]
        lp_progress._assign_official_game_numbers(exact, historical)
        self.assertEqual([item.get("game_number") for item in exact], [6, None, 8])

        historical[-1]["game_number"] = 8
        historical[-1]["wins_after"] = 4
        historical[-1]["losses_after"] = 4
        exact = [
            {"match_id": "LEFT", "win": False},
            {"match_id": "MIDDLE", "win": True},
            {"match_id": "RIGHT", "win": False},
        ]
        lp_progress._assign_official_game_numbers(exact, historical)
        self.assertEqual([item.get("game_number") for item in exact], [6, 7, 8])

    def test_match_metadata_keeps_existing_match_statistics_and_handles_zero_team_kills(self):
        metadata = lp_progress._match_metadata(
            row("JP1_STATS", "2026-08-31 12:00:00", "Nami", True, 3, 0, 7, 0, 88, None, 600),
            "JP1_STATS",
        )
        self.assertEqual((metadata["kills"], metadata["deaths"], metadata["assists"]), (3, 0, 7))
        self.assertIsNone(metadata["kp_pct"])
        self.assertAlmostEqual(metadata["vision_score_per_min"], 8.8)


if __name__ == "__main__":
    unittest.main()
