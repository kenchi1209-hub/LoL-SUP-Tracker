import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import requests

import main


class MainNoopTest(unittest.TestCase):
    EXPORT_FUNCTIONS = (
        "export_timeline_summary",
        "export_fight_details",
        "export_all_fight_details",
        "export_match_details",
        "export_participants_from_raw",
        "export_my_matches_from_raw",
        "export_result_report",
        "create_review_template",
        "export_final_report",
        "export_summary",
        "export_monthly_csvs",
        "export_yearly_summary",
        "export_excel_report",
        "write_last_updated",
        "write_current_rank",
    )

    def run_in_temp(self, match_ids, details=None):
        details = details or {}
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                sentinel = Path("data/csv/my_matches.csv")
                sentinel.parent.mkdir(parents=True)
                sentinel.write_text("match_id\n", encoding="utf-8")
                before = sentinel.read_bytes()

                stack.enter_context(patch.object(main, "get_puuid", return_value="test-puuid"))
                stack.enter_context(
                    patch.object(main, "get_match_ids_by_date_range", return_value=match_ids)
                )
                detail_mock = stack.enter_context(
                    patch.object(main, "get_match_detail", side_effect=lambda match_id: details[match_id])
                )
                exporter = stack.enter_context(patch.object(main, "export_timeline_summary"))
                result = main.run(Path(directory) / "data")

                self.assertEqual(result, 0)
                self.assertEqual(sentinel.read_bytes(), before)
                exporter.assert_not_called()
                return detail_mock
            finally:
                os.chdir(previous)

    def test_no_new_match_ids_is_successful_noop(self):
        with patch.object(main, "get_league_entries_by_puuid") as rank_fetcher:
            detail_mock = self.run_in_temp([])
        detail_mock.assert_not_called()
        rank_fetcher.assert_not_called()

    def test_only_ineligible_new_matches_is_successful_noop(self):
        detail_mock = self.run_in_temp(
            ["JP1_INELIGIBLE"],
            {"JP1_INELIGIBLE": {"info": {"queueId": 450}}},
        )
        detail_mock.assert_called_once_with("JP1_INELIGIBLE")

    def test_published_matches_do_not_trigger_detail_fetch(self):
        with patch.object(main, "get_match_detail") as detail_mock:
            eligible, ineligible = main.discover_new_eligible_matches(
                ["JP1_PUBLISHED"], published_ids={"JP1_PUBLISHED"}
            )
        detail_mock.assert_not_called()
        self.assertEqual(eligible, {})
        self.assertEqual(ineligible, [])

    def test_eligible_queue_uses_existing_queue_map(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                with patch.object(
                    main,
                    "get_match_detail",
                    return_value={"info": {"queueId": 420}},
                ):
                    eligible, ineligible = main.discover_new_eligible_matches(
                        ["JP1_NEW"], published_ids=set()
                    )
            finally:
                os.chdir(previous)
        self.assertEqual(list(eligible), ["JP1_NEW"])
        self.assertEqual(ineligible, [])

    def test_target_selector_ignores_older_unpublished_normal_match(self):
        matches = {
            "JP1_NORMAL": {"info": {"queueId": 400, "gameStartTimestamp": 1793114644000}},
            "JP1_OLD_RANKED": {"info": {"queueId": 420, "gameStartTimestamp": 1793114644000}},
            "JP1_RANKED": {"info": {"queueId": 420, "gameStartTimestamp": 1793117701000}},
        }
        selected = main.select_single_target_match(
            matches, 420, "2026-10-28T01:12:46+09:00",
        )
        self.assertEqual(list(selected), ["JP1_RANKED"])

    def test_regular_discovery_keeps_multiple_backfill_matches_for_daily_update(self):
        details = {
            "JP1_NORMAL": {"info": {"queueId": 400}},
            "JP1_RANKED": {"info": {"queueId": 420}},
        }
        with patch.object(main, "get_match_detail", side_effect=lambda match_id: details[match_id]):
            eligible, ineligible = main.discover_new_eligible_matches(
                ["JP1_NORMAL", "JP1_RANKED"], published_ids=set(),
            )
        self.assertEqual(list(eligible), ["JP1_NORMAL", "JP1_RANKED"])
        self.assertEqual(ineligible, [])

    def test_target_selector_rejects_ambiguous_matches(self):
        matches = {
            "JP1_ONE": {"info": {"queueId": 420, "gameStartTimestamp": 1793117701000}},
            "JP1_TWO": {"info": {"queueId": 420, "gameStartTimestamp": 1793117820000}},
        }
        with self.assertRaisesRegex(RuntimeError, "multiple Match-V5 candidates"):
            main.select_single_target_match(
                matches, 420, "2026-10-28T01:12:46+09:00",
            )

    def test_target_selector_returns_no_candidate_before_match_v5_reflection(self):
        selected = main.select_single_target_match(
            {"JP1_OLD": {"info": {"queueId": 420, "gameStartTimestamp": 1793113200000}}},
            420,
            "2026-10-28T01:12:46+09:00",
        )
        self.assertEqual(selected, {})

    def test_target_selector_rejects_timestamp_without_timezone(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            main.select_single_target_match({}, 420, "2026-10-28T01:12:46")

    def test_exact_target_selector_selects_only_the_requested_match(self):
        matches = {
            "JP1_TARGET": {"info": {"queueId": 400, "gameStartTimestamp": 1793117701000}},
            "JP1_OTHER": {"info": {"queueId": 400, "gameStartTimestamp": 1793117820000}},
        }
        selected = main.select_exact_target_match(
            matches,
            "JP1_TARGET",
            target_queue_id=400,
            target_not_before_jst="2026-10-28T01:12:46+09:00",
        )
        self.assertEqual(list(selected), ["JP1_TARGET"])

    def test_exact_target_selector_returns_no_match_when_target_is_absent(self):
        selected = main.select_exact_target_match(
            {"JP1_OTHER": {"info": {"queueId": 400, "gameStartTimestamp": 1793117701000}}},
            "JP1_TARGET",
            target_queue_id=400,
        )
        self.assertEqual(selected, {})

    def test_exact_target_selector_rejects_queue_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, "queue does not match"):
            main.select_exact_target_match(
                {"JP1_TARGET": {"info": {"queueId": 400, "gameStartTimestamp": 1793117701000}}},
                "JP1_TARGET",
                target_queue_id=420,
            )

    def test_exact_target_selector_rejects_match_before_boundary(self):
        with self.assertRaisesRegex(RuntimeError, "predates"):
            main.select_exact_target_match(
                {"JP1_TARGET": {"info": {"queueId": 400, "gameStartTimestamp": 1793114644000}}},
                "JP1_TARGET",
                target_queue_id=400,
                target_not_before_jst="2026-10-28T01:12:46+09:00",
            )

    def test_exact_target_discovery_uses_match_v5_membership_not_dirty_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory) / "raw"
            detail_path = raw_root / "JP1_TARGET" / "match.json"
            detail_path.parent.mkdir(parents=True)
            detail_path.write_text(json.dumps({
                "metadata": {"matchId": "JP1_TARGET"},
                "info": {"queueId": 400},
            }), encoding="utf-8")
            selected = main.discover_exact_target_match(
                ["JP1_TARGET"], "JP1_TARGET", raw_root,
            )
        self.assertEqual(list(selected), ["JP1_TARGET"])

    def test_exact_target_discovery_rejects_id_outside_account_match_history(self):
        selected = main.discover_exact_target_match(
            ["JP1_OTHER"], "JP1_TARGET",
        )
        self.assertEqual(selected, {})

    def test_exact_target_discovery_rejects_mismatched_detail_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory) / "raw"
            detail_path = raw_root / "JP1_TARGET" / "match.json"
            detail_path.parent.mkdir(parents=True)
            detail_path.write_text(json.dumps({
                "metadata": {"matchId": "JP1_OTHER"},
                "info": {"queueId": 400},
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                main.discover_exact_target_match(["JP1_TARGET"], "JP1_TARGET", raw_root)

    def test_targeted_run_generates_only_the_watched_match(self):
        details = {
            "JP1_NORMAL": {"info": {"queueId": 400, "gameStartTimestamp": 1793114644000}},
            "JP1_RANKED": {"info": {"queueId": 420, "gameStartTimestamp": 1793117701000}},
        }
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            data_root = Path(directory) / "data"
            (data_root / "csv").mkdir(parents=True)
            (data_root / "csv" / "my_matches.csv").write_text("match_id\n", encoding="utf-8")
            stack.enter_context(patch.object(main, "get_puuid", return_value="puuid"))
            stack.enter_context(patch.object(
                main, "get_match_ids_by_date_range", return_value=["JP1_NORMAL", "JP1_RANKED"],
            ))
            stack.enter_context(patch.object(
                main, "get_match_detail", side_effect=lambda match_id: details[match_id],
            ))
            save_detail = stack.enter_context(patch.object(main, "save_match_json"))
            stack.enter_context(patch.object(main, "get_match_timeline", return_value={}))
            stack.enter_context(patch.object(main, "save_match_timeline_json"))
            stack.enter_context(patch.object(main, "analyze_match_timeline", return_value={
                "champion": "Test", "kills": 0, "deaths": 0, "assists": 0, "my_fights": 0,
            }))
            stack.enter_context(patch.object(main, "capture_rank_snapshots", return_value=[]))
            for name in self.EXPORT_FUNCTIONS:
                stack.enter_context(patch.object(main, name))
            self.assertEqual(main.run(
                data_root,
                target_queue_id=420,
                target_not_before_jst="2026-10-28T01:12:46+09:00",
            ), 0)
            self.assertEqual(save_detail.call_args.args[0], "JP1_RANKED")
            self.assertEqual(save_detail.call_count, 1)

    def test_private_raw_not_yet_published_is_still_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                detail_path = Path("data/raw/JP1_PENDING/match.json")
                detail_path.parent.mkdir(parents=True)
                detail_path.write_text(
                    json.dumps({"info": {"queueId": 400}}), encoding="utf-8"
                )
                with patch.object(main, "get_match_detail") as detail_mock:
                    eligible, _ = main.discover_new_eligible_matches(
                        ["JP1_PENDING"],
                        published_ids=set(),
                        raw_root=Path("data/raw"),
                    )
                detail_mock.assert_not_called()
            finally:
                os.chdir(previous)
        self.assertEqual(list(eligible), ["JP1_PENDING"])

    def test_new_eligible_match_runs_normal_update_flow(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path("data/csv").mkdir(parents=True)
                Path("data/csv/my_matches.csv").write_text(
                    "match_id\n", encoding="utf-8"
                )
                stack.enter_context(patch.object(main, "get_puuid", return_value="puuid"))
                stack.enter_context(
                    patch.object(
                        main, "get_match_ids_by_date_range", return_value=["JP1_NEW"]
                    )
                )
                stack.enter_context(
                    patch.object(
                        main,
                        "get_match_detail",
                        return_value={"info": {"queueId": 420}},
                    )
                )
                save_detail = stack.enter_context(
                    patch.object(main, "save_match_json", return_value="match.json")
                )
                stack.enter_context(
                    patch.object(main, "get_match_timeline", return_value={})
                )
                save_timeline = stack.enter_context(
                    patch.object(main, "save_match_timeline_json", return_value="timeline.json")
                )
                analyze = stack.enter_context(
                    patch.object(
                        main,
                        "analyze_match_timeline",
                        return_value={
                            "champion": "Test",
                            "kills": 1,
                            "deaths": 2,
                            "assists": 3,
                            "my_fights": 1,
                        },
                    )
                )
                rank_snapshots = stack.enter_context(
                    patch.object(main, "capture_rank_snapshots", return_value=[Path("rank_snapshot.json")])
                )
                exporters = {
                    name: stack.enter_context(patch.object(main, name))
                    for name in self.EXPORT_FUNCTIONS
                }

                data_root = Path(directory) / "data"
                self.assertEqual(main.run(data_root), 0)
                save_detail.assert_called_once()
                save_timeline.assert_called_once()
                analyze.assert_called_once_with(
                    "JP1_NEW", puuid="puuid", raw_root=data_root.resolve() / "raw"
                )
                rank_snapshots.assert_called_once_with(
                    ["JP1_NEW"], data_root.resolve() / "raw", main.get_league_entries_by_puuid
                )
                for exporter in exporters.values():
                    exporter.assert_called_once()
                resolved = data_root.resolve()
                exporters["export_timeline_summary"].assert_called_once_with(
                    resolved / "raw", resolved / "csv/timeline_summary.csv"
                )
                exporters["export_fight_details"].assert_called_once_with(
                    output_path=resolved / "csv/fight_details.json",
                    raw_root=resolved / "raw",
                )
                exporters["export_all_fight_details"].assert_called_once_with(
                    output_path=resolved / "csv/all_fight_details.json",
                    raw_root=resolved / "raw",
                )
                exporters["export_match_details"].assert_called_once_with(
                    "puuid", resolved / "raw", resolved / "csv/match_details.json"
                )
                exporters["export_monthly_csvs"].assert_called_once_with(
                    resolved / "csv"
                )
                exporters["export_excel_report"].assert_called_once_with(
                    resolved / "csv/my_matches.csv",
                    resolved / "csv/review.csv",
                    resolved / "excel/lol_report.xlsx",
                )
            finally:
                os.chdir(previous)

    def test_timeline_analysis_failure_remains_fatal(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path("data/csv").mkdir(parents=True)
                Path("data/csv/my_matches.csv").write_text("match_id\n", encoding="utf-8")
                stack.enter_context(patch.object(main, "get_puuid", return_value="puuid"))
                stack.enter_context(
                    patch.object(main, "get_match_ids_by_date_range", return_value=["JP1_BAD"])
                )
                stack.enter_context(
                    patch.object(
                        main,
                        "get_match_detail",
                        return_value={"info": {"queueId": 400}},
                    )
                )
                stack.enter_context(patch.object(main, "save_match_json"))
                stack.enter_context(patch.object(main, "get_match_timeline", return_value={}))
                stack.enter_context(patch.object(main, "save_match_timeline_json"))
                stack.enter_context(
                    patch.object(main, "analyze_match_timeline", side_effect=ValueError("bad raw"))
                )
                exporter = stack.enter_context(patch.object(main, "export_timeline_summary"))
                with self.assertRaises(RuntimeError):
                    main.run(Path(directory) / "data")
                exporter.assert_not_called()
            finally:
                os.chdir(previous)

    def test_riot_api_error_is_not_treated_as_noop(self):
        with patch.object(main, "get_puuid", side_effect=requests.HTTPError("401")):
            with self.assertRaises(requests.HTTPError):
                main.run()

if __name__ == "__main__":
    unittest.main()
