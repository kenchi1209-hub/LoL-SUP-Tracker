import json
import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from lp_snapshot import (
    AmbiguousHistoryError,
    CheckpointNotRequiredError,
    LeagueUpdateTimeout,
    LPSnapshotError,
    build_rank_after,
    capture_one,
    create_checkpoint,
    create_baseline,
    history_path,
    rank_value,
    reconcile_previous_rank_after,
    rebuild_lp_history,
    wait_for_league_update,
)
from raw_paths import paths_for_match
from timezone_utils import JST
from verify_fight_raw_completeness import required_paths


def league_rank(tier="SILVER", division="IV", lp=20, wins=40, losses=55):
    return {
        "queueType": "RANKED_SOLO_5x5",
        "tier": tier,
        "rank": division,
        "leaguePoints": lp,
        "wins": wins,
        "losses": losses,
        "puuid": "must-not-be-copied",
        "summonerId": "must-not-be-copied",
    }


def match_detail(match_id, puuid="self", won=True, hour=1, queue_id=420):
    creation = int(datetime(2026, 8, 28, hour, 0, tzinfo=JST).timestamp() * 1000)
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "queueId": queue_id,
            "gameCreation": creation,
            "gameEndTimestamp": creation + 30 * 60 * 1000,
            "gameDuration": 1800,
            "gameVersion": "16.17.810.4348",
            "participants": [
                {"puuid": puuid, "championName": "Nami", "win": won}
            ],
        },
    }


class Clock:
    def __init__(self):
        self.value = 0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class LPSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.csv = self.root / "csv"
        self.current_rank = self.csv / "current_rank.json"
        self.csv.mkdir(parents=True)
        self.current_rank.write_text(
            json.dumps(league_rank()), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def baseline(self):
        return create_baseline(
            self.current_rank,
            self.raw,
            self.csv,
            captured_at=datetime(2026, 8, 28, 0, 0, tzinfo=JST),
        )

    def capture(self, details, after, **kwargs):
        ids = list(details)
        captured_at = kwargs.pop(
            "captured_at", datetime(2026, 8, 28, 2, 0, tzinfo=JST)
        )
        return capture_one(
            "self",
            self.raw,
            self.csv,
            lambda _puuid, count=100: ids,
            lambda match_id: details[match_id],
            lambda: after,
            captured_at=captured_at,
            sleep=lambda _seconds: None,
            **kwargs,
        )

    def write_local_matches(self, rows):
        path = self.csv / "my_matches.csv"
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=("match_id", "date", "queue_id", "patch", "champion", "win")
            )
            writer.writeheader()
            writer.writerows(rows)

    def checkpoint_rows(self, first="JP1_GAP_ONE", second="JP1_GAP_TWO", start_hour=1):
        return [
            {"match_id": first, "date": f"2026-08-28 {start_hour:02d}:00:00", "queue_id": "420", "patch": "16.17", "champion": "Nami", "win": "True"},
            {"match_id": second, "date": f"2026-08-28 {start_hour + 1:02d}:00:00", "queue_id": "420", "patch": "16.17", "champion": "Leona", "win": "False"},
        ]

    def checkpoint(self, after=None, captured_at=None):
        return create_checkpoint(
            self.raw,
            self.csv,
            lambda: after or league_rank(lp=20, wins=41, losses=56),
            captured_at=captured_at or datetime(2026, 8, 28, 3, 0, tzinfo=JST),
        )

    def test_baseline_is_minimal_immutable_and_history_starts_empty(self):
        output = self.baseline()
        baseline = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(baseline["snapshot_type"], "baseline")
        self.assertEqual(baseline["confidence"], "baseline")
        self.assertEqual(baseline["queue_id"], 420)
        self.assertEqual((baseline["tier"], baseline["division"], baseline["lp"]), ("SILVER", "IV", 20))
        serialized = json.dumps(baseline)
        self.assertNotIn("puuid", serialized)
        self.assertNotIn("summonerId", serialized)
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(history["matches"], [])
        with self.assertRaises(Exception):
            self.baseline()

    def test_first_win_uses_baseline_as_before_and_writes_exact_snapshot(self):
        self.baseline()
        output = self.capture(
            {"JP1_NEW": match_detail("JP1_NEW", won=True)},
            league_rank(lp=42, wins=41, losses=55),
        )
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["before"]["lp"], 20)
        self.assertEqual(snapshot["before"]["wins"], 40)
        self.assertEqual(snapshot["after"]["wins"], 41)
        self.assertEqual(snapshot["lp_delta"], 22)
        self.assertEqual(snapshot["confidence"], "exact")
        self.assertEqual(snapshot["games_since_previous_snapshot"], 1)

    def test_first_loss_requires_losses_plus_one(self):
        self.baseline()
        output = self.capture(
            {"JP1_LOSS": match_detail("JP1_LOSS", won=False)},
            league_rank(lp=5, wins=40, losses=56),
        )
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(snapshot["win"])
        self.assertEqual(snapshot["after"]["losses"], 56)

    def test_loss_with_unchanged_lp_is_an_exact_zero_delta(self):
        self.baseline()
        output = self.capture(
            {"JP1_ZERO": match_detail("JP1_ZERO", won=False)},
            league_rank(lp=20, wins=40, losses=56),
        )
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["lp_delta"], 0)
        self.assertEqual(snapshot["confidence"], "exact")
        self.assertEqual(snapshot["lp_status"], "provisional")
        self.assertEqual(history["matches"][0]["lp_delta"], 0)

    def _write_observed_loss(self):
        self.current_rank.write_text(
            json.dumps(league_rank(lp=69, wins=46, losses=59)), encoding="utf-8"
        )
        self.baseline()
        previous = build_rank_after(
            {
                "match_id": "JP1_PREVIOUS", "game_datetime_jst": "2026-08-28T01:00:00+09:00",
                "patch": "16.17", "champion": "Nami", "win": False,
            },
            {"tier": "SILVER", "division": "IV", "lp": 69, "wins": 46, "losses": 59},
            {"tier": "SILVER", "division": "IV", "lp": 50, "wins": 46, "losses": 60},
            captured_at=datetime(2026, 8, 28, 1, 30, tzinfo=JST),
        )
        path = paths_for_match("JP1_PREVIOUS", self.raw).rank_after
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(previous), encoding="utf-8")
        rebuild_lp_history(self.raw, self.csv)
        return path

    def test_next_rank_before_corrects_previous_observed_loss_without_changing_record(self):
        path = self._write_observed_loss()
        result = reconcile_previous_rank_after(
            self.raw,
            self.csv,
            {"tier": "SILVER", "division": "IV", "leaguePoints": 69, "wins": 46, "losses": 60},
            "2026-08-28T02:00:00+09:00",
            captured_at=datetime(2026, 8, 28, 2, 0, tzinfo=JST),
        )
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(snapshot["observed_lp_delta"], -19)
        self.assertEqual(snapshot["lp_delta"], 0)
        self.assertEqual(snapshot["lp_delta_final"], 0)
        self.assertEqual(snapshot["lp_correction"], 19)
        self.assertEqual(snapshot["lp_status"], "corrected")
        self.assertEqual(snapshot["after"]["lp"], 69)
        self.assertEqual(snapshot["after"]["losses"], 60)
        self.assertEqual(history["matches"][0]["lp_delta"], 0)

    def test_recheck_preview_detects_correction_without_writing_private_data(self):
        path = self._write_observed_loss()
        history_before = history_path(self.csv).read_bytes()
        snapshot_before = path.read_bytes()
        result = reconcile_previous_rank_after(
            self.raw,
            self.csv,
            league_rank(lp=69, wins=46, losses=60),
            "2026-08-28T02:00:00+09:00",
            apply=False,
        )
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["lp_delta"], 0)
        self.assertEqual(result["observed_lp_delta"], -19)
        self.assertEqual(path.read_bytes(), snapshot_before)
        self.assertEqual(history_path(self.csv).read_bytes(), history_before)

    def test_matching_next_rank_before_confirms_observed_delta_without_rewriting_it(self):
        path = self._write_observed_loss()
        result = reconcile_previous_rank_after(
            self.raw,
            self.csv,
            {"tier": "SILVER", "division": "IV", "leaguePoints": 50, "wins": 46, "losses": 60},
            "2026-08-28T02:00:00+09:00",
        )
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(snapshot["lp_delta"], -19)
        self.assertEqual(snapshot["lp_status"], "confirmed")
        self.assertNotIn("observed_lp_delta", snapshot)

    def test_mismatched_wins_losses_needs_review_without_writing_a_correction(self):
        path = self._write_observed_loss()
        original = path.read_bytes()
        result = reconcile_previous_rank_after(
            self.raw,
            self.csv,
            {"tier": "SILVER", "division": "IV", "leaguePoints": 71, "wins": 47, "losses": 60},
            "2026-08-28T02:00:00+09:00",
        )
        self.assertEqual(result, {"status": "needs_review", "changed": False})
        self.assertEqual(path.read_bytes(), original)

    def test_non_solo_pre_match_rank_cannot_reconcile_the_previous_snapshot(self):
        path = self._write_observed_loss()
        original = path.read_bytes()
        non_solo = league_rank(lp=69, wins=46, losses=60)
        non_solo["queueType"] = "RANKED_FLEX_SR"
        with self.assertRaises(LPSnapshotError):
            reconcile_previous_rank_after(
                self.raw, self.csv, non_solo, "2026-08-28T02:00:00+09:00",
            )
        self.assertEqual(path.read_bytes(), original)

    def test_capture_uses_corrected_previous_rank_as_the_next_match_before(self):
        previous_path = self._write_observed_loss()
        output = self.capture(
            {"JP1_NEXT": match_detail("JP1_NEXT", won=True, hour=2)},
            league_rank(lp=90, wins=47, losses=60),
            next_rank_before={
                "tier": "SILVER", "division": "IV", "leaguePoints": 69,
                "wins": 46, "losses": 60,
            },
        )
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        current = json.loads(output.read_text(encoding="utf-8"))
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(previous["lp_delta"], 0)
        self.assertEqual(current["before"]["lp"], 69)
        self.assertEqual(current["reconciled_previous_match_id"], "JP1_PREVIOUS")
        self.assertEqual([item["lp_delta"] for item in history["matches"]], [0, 21])

    def test_unexpected_record_is_ambiguous_and_writes_nothing(self):
        self.baseline()
        with self.assertRaises(AmbiguousHistoryError):
            self.capture(
                {"JP1_BAD": match_detail("JP1_BAD", won=True)},
                league_rank(wins=42, losses=55),
            )
        self.assertFalse(paths_for_match("JP1_BAD", self.raw).rank_after.exists())
        self.assertEqual(json.loads(history_path(self.csv).read_text())["matches"], [])

    def test_wait_retries_unchanged_record_until_reflected(self):
        before = {"tier": "SILVER", "division": "IV", "lp": 20, "wins": 40, "losses": 55}
        fetch = Mock(side_effect=[league_rank(), league_rank(lp=42, wins=41)])
        clock = Clock()
        after = wait_for_league_update(
            before, True, fetch, timeout_seconds=10, poll_interval_seconds=2,
            monotonic=clock.monotonic, sleep=clock.sleep,
        )
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(after["lp"], 42)

    def test_timeout_writes_no_confirmed_snapshot(self):
        self.baseline()
        details = {"JP1_TIMEOUT": match_detail("JP1_TIMEOUT")}
        clock = Clock()
        with self.assertRaises(LeagueUpdateTimeout):
            capture_one(
                "self", self.raw, self.csv,
                lambda _puuid, count=100: list(details),
                lambda match_id: details[match_id],
                lambda: league_rank(),
                timeout_seconds=4, poll_interval_seconds=2,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(paths_for_match("JP1_TIMEOUT", self.raw).rank_after.exists())

    def test_two_uncaptured_matches_are_ambiguous_before_rank_api_call(self):
        self.baseline()
        details = {
            "JP1_ONE": match_detail("JP1_ONE", hour=1),
            "JP1_TWO": match_detail("JP1_TWO", hour=2),
        }
        rank_api = Mock()
        with self.assertRaises(AmbiguousHistoryError):
            capture_one(
                "self", self.raw, self.csv,
                lambda _puuid, count=100: list(details),
                lambda match_id: details[match_id], rank_api,
            )
        rank_api.assert_not_called()
        self.assertFalse(paths_for_match("JP1_ONE", self.raw).rank_after.exists())
        self.assertFalse(paths_for_match("JP1_TWO", self.raw).rank_after.exists())

    def test_noop_does_not_call_rank_api_or_change_history(self):
        self.baseline()
        before = history_path(self.csv).read_bytes()
        rank_api = Mock()
        result = capture_one(
            "self", self.raw, self.csv,
            lambda _puuid, count=100: [], Mock(), rank_api,
        )
        self.assertIsNone(result)
        rank_api.assert_not_called()
        self.assertEqual(history_path(self.csv).read_bytes(), before)

    def test_rank_math_across_divisions_tiers_and_master(self):
        self.assertEqual(
            rank_value({"tier": "SILVER", "division": "III", "lp": 18})
            - rank_value({"tier": "SILVER", "division": "IV", "lp": 95}),
            23,
        )
        self.assertEqual(
            rank_value({"tier": "SILVER", "division": "IV", "lp": 92})
            - rank_value({"tier": "SILVER", "division": "III", "lp": 10}),
            -18,
        )
        self.assertEqual(
            rank_value({"tier": "GOLD", "division": "IV", "lp": 10})
            - rank_value({"tier": "SILVER", "division": "I", "lp": 90}),
            20,
        )
        self.assertEqual(rank_value({"tier": "MASTER", "division": None, "lp": 135}), 2935)
        self.assertEqual(rank_value({"tier": "GRANDMASTER", "division": None, "lp": 500}), 3300)

    def test_history_is_rebuilt_from_exact_snapshots_only(self):
        self.baseline()
        exact = build_rank_after(
            {
                "match_id": "JP1_EXACT", "game_datetime_jst": "2026-08-28T01:00:00+09:00",
                "patch": "16.17", "champion": "Nami", "win": True,
            },
            {"tier": "SILVER", "division": "IV", "lp": 20, "wins": 40, "losses": 55},
            {"tier": "SILVER", "division": "IV", "lp": 42, "wins": 41, "losses": 55},
            datetime(2026, 8, 28, 2, 0, tzinfo=JST),
        )
        exact_path = paths_for_match("JP1_EXACT", self.raw).rank_after
        exact_path.parent.mkdir(parents=True)
        exact_path.write_text(json.dumps(exact), encoding="utf-8")
        old_ids = [f"JP1_OLD_{index:03d}" for index in range(97)]
        for old_id in old_ids:
            old_detail = paths_for_match(old_id, self.raw).detail
            old_detail.parent.mkdir(parents=True)
            old_detail.write_text(
                json.dumps(match_detail(old_id, hour=0)), encoding="utf-8"
            )
        ambiguous_path = paths_for_match("JP1_AMBIGUOUS", self.raw).rank_after
        ambiguous_path.parent.mkdir(parents=True)
        ambiguous_path.write_text(json.dumps({**exact, "match_id": "JP1_AMBIGUOUS", "confidence": "ambiguous"}), encoding="utf-8")

        history = rebuild_lp_history(self.raw, self.csv)
        self.assertEqual([item["match_id"] for item in history["matches"]], ["JP1_EXACT"])
        self.assertEqual(history["matches"][0]["lp_delta"], 22)
        self.assertTrue(all(old_id not in json.dumps(history) for old_id in old_ids))
        serialized = json.dumps(history)
        self.assertNotIn("puuid", serialized)
        self.assertNotIn("summonerId", serialized)

    def test_rank_after_is_optional_for_raw_completeness(self):
        paths = paths_for_match("JP1_OPTIONAL", self.raw)
        paths.directory.mkdir(parents=True)
        for path in paths.required():
            path.write_text("{}", encoding="utf-8")
        self.assertNotIn(paths.rank_after, required_paths(self.raw, "JP1_OPTIONAL"))

    def test_rebuild_rejects_discontinuous_exact_snapshot(self):
        self.baseline()
        snapshot = build_rank_after(
            {
                "match_id": "JP1_GAP", "game_datetime_jst": "2026-08-28T01:00:00+09:00",
                "patch": "16.17", "champion": "Nami", "win": True,
            },
            {"tier": "SILVER", "division": "IV", "lp": 99, "wins": 40, "losses": 55},
            {"tier": "SILVER", "division": "III", "lp": 21, "wins": 41, "losses": 55},
        )
        path = paths_for_match("JP1_GAP", self.raw).rank_after
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "Discontinuous"):
            rebuild_lp_history(self.raw, self.csv)

    def test_season_configuration_is_versioned_and_open_ended(self):
        config = json.loads(
            (Path(__file__).resolve().parent / "lp_seasons.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["seasons"][0]["id"], "2026")
        self.assertEqual(config["seasons"][0]["start_jst"], "2026-01-01")
        self.assertIsNone(config["seasons"][0]["end_jst"])

    def test_capture_remains_ambiguous_for_two_uncaptured_matches(self):
        self.baseline()
        details = {
            "JP1_ONE": match_detail("JP1_ONE", hour=1),
            "JP1_TWO": match_detail("JP1_TWO", hour=2),
        }
        with self.assertRaises(AmbiguousHistoryError):
            self.capture(details, league_rank(wins=41, losses=56))
        self.assertFalse(paths_for_match("JP1_ONE", self.raw).rank_after.exists())
        self.assertFalse(paths_for_match("JP1_TWO", self.raw).rank_after.exists())

    def test_checkpoint_records_gap_without_assigning_match_lp(self):
        baseline_bytes = self.baseline().read_bytes()
        self.write_local_matches(self.checkpoint_rows())
        output = self.checkpoint()
        checkpoint = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["snapshot_type"], "checkpoint")
        self.assertNotIn("match_id", checkpoint)
        self.assertNotIn("lp_delta", checkpoint)
        self.assertEqual(checkpoint["games_since_previous_snapshot"], 2)
        self.assertEqual(checkpoint["gap"]["match_ids"], ["JP1_GAP_ONE", "JP1_GAP_TWO"])
        self.assertEqual(checkpoint["gap"]["wins"], 1)
        self.assertEqual(checkpoint["gap"]["losses"], 1)
        self.assertNotIn("puuid", json.dumps(checkpoint))
        self.assertNotIn("summonerId", json.dumps(checkpoint))
        self.assertNotIn("participantId", json.dumps(checkpoint))
        self.assertEqual(
            (self.raw / "lp_progress" / "baseline.json").read_bytes(), baseline_bytes
        )
        self.assertFalse(paths_for_match("JP1_GAP_ONE", self.raw).rank_after.exists())
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(len(history["checkpoints"]), 1)
        self.assertTrue(history["checkpoints"][0]["gap_before"])
        self.assertEqual(history["matches"], [])

    def test_checkpoint_then_capture_uses_checkpoint_as_before(self):
        self.baseline()
        self.write_local_matches(self.checkpoint_rows())
        self.checkpoint(captured_at=datetime(2026, 8, 28, 3, 0, tzinfo=JST))
        output = self.capture(
            {"JP1_AFTER": match_detail("JP1_AFTER", won=True, hour=4)},
            league_rank(lp=42, wins=42, losses=56),
            captured_at=datetime(2026, 8, 28, 5, 0, tzinfo=JST),
        )
        snapshot = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["before"]["wins"], 41)
        self.assertEqual(snapshot["before"]["losses"], 56)
        self.assertEqual(snapshot["before"]["lp"], 20)
        self.assertEqual(snapshot["lp_delta"], 22)
        self.assertEqual(snapshot["games_since_previous_snapshot"], 1)
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(history["matches"][0]["segment_id"], "segment-1")

    def test_checkpoint_rejects_zero_or_one_match_without_writing(self):
        self.baseline()
        original = history_path(self.csv).read_bytes()
        rank_api = Mock()
        with self.assertRaises(CheckpointNotRequiredError):
            create_checkpoint(self.raw, self.csv, rank_api)
        rank_api.assert_not_called()
        self.assertEqual(history_path(self.csv).read_bytes(), original)
        self.write_local_matches(self.checkpoint_rows()[:1])
        with self.assertRaisesRegex(CheckpointNotRequiredError, "use capture"):
            create_checkpoint(self.raw, self.csv, rank_api)
        rank_api.assert_not_called()
        self.assertEqual(history_path(self.csv).read_bytes(), original)

    def test_checkpoint_uses_existing_raw_without_match_v5_or_csv_export(self):
        self.baseline()
        for match_id, hour, won in (("JP1_RAW_ONE", 1, True), ("JP1_RAW_TWO", 2, False)):
            path = paths_for_match(match_id, self.raw).detail
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(match_detail(match_id, won=won, hour=hour)), encoding="utf-8")
        output = create_checkpoint(
            self.raw,
            self.csv,
            lambda: league_rank(wins=41, losses=56),
            puuid="self",
            captured_at=datetime(2026, 8, 28, 3, 0, tzinfo=JST),
        )
        checkpoint = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["gap"]["match_ids"], ["JP1_RAW_ONE", "JP1_RAW_TWO"])

    def test_multiple_checkpoints_keep_separate_gap_segments(self):
        self.baseline()
        self.write_local_matches(self.checkpoint_rows())
        self.checkpoint(captured_at=datetime(2026, 8, 28, 3, 0, tzinfo=JST))
        self.write_local_matches(
            self.checkpoint_rows("JP1_GAP_THREE", "JP1_GAP_FOUR", start_hour=4)
        )
        self.checkpoint(
            after=league_rank(lp=20, wins=42, losses=57),
            captured_at=datetime(2026, 8, 28, 6, 0, tzinfo=JST),
        )
        history = json.loads(history_path(self.csv).read_text(encoding="utf-8"))
        self.assertEqual(len(history["checkpoints"]), 2)
        self.assertEqual(history["checkpoints"][1]["previous_snapshot_type"], "checkpoint")
        self.assertEqual(history["checkpoints"][1]["segment_id"], "segment-2")


if __name__ == "__main__":
    unittest.main()
