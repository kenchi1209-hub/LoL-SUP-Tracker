import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyze_timeline import build_all_fight_context, build_review_context
from fight_detail_exporter import build_all_fight_details, compact_all_fight


def sample_fight(player_involved):
    return {
        "fight_id": 7,
        "start_timestamp": 1000,
        "end_timestamp": 2000,
        "duration_ms": 1000,
        "participant_count": 2,
        "participants": [],
        "center_position": {"x": 1, "y": 2},
        "my_kda": {"kills": 1, "deaths": 0, "assists": 2},
        "friendly_kills": 1,
        "enemy_kills": 0,
        "objective_events": [],
        "events": [],
        "my_relations": [],
        "result": "WIN",
        "player_involved": player_involved,
    }


class AllFightDetailsTest(unittest.TestCase):
    def test_review_context_keeps_self_fields(self):
        review = build_review_context([sample_fight(True)])
        self.assertNotIn("player_involved", review[0])
        self.assertEqual(review[0]["survival"], "SURVIVED")
        self.assertEqual(review[0]["my_kda"], {"kills": 1, "deaths": 0, "assists": 2})

    def test_non_self_fight_is_explicitly_not_involved(self):
        all_fight = build_all_fight_context([sample_fight(False)])[0]
        self.assertFalse(all_fight["player_involved"])
        self.assertEqual(all_fight["survival"], "NOT_INVOLVED")
        self.assertIsNone(all_fight["my_kda"])

    def test_all_export_uses_all_context_and_keeps_match_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory) / "raw"
            match_dir = raw_root / "JP1_TEST"
            match_dir.mkdir(parents=True)
            (match_dir / "combat_timeline.json").write_text(
                json.dumps({"match_id": "JP1_TEST", "participant": {"participant_id": 1}}),
                encoding="utf-8",
            )
            (match_dir / "match.json").write_text(
                json.dumps(
                    {
                        "info": {
                            "participants": [
                                {"participantId": 1, "teamPosition": "UTILITY"}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (match_dir / "timeline.json").write_text("{}", encoding="utf-8")
            with patch("fight_detail_exporter.find_player", return_value={"teamId": 100}), patch(
                "fight_detail_exporter.build_all_fight_context_from_timeline",
                return_value=[sample_fight(False)],
            ):
                details, failures = build_all_fight_details(raw_root=raw_root)

        self.assertEqual(failures, [])
        self.assertEqual(set(details), {"JP1_TEST"})
        self.assertFalse(details["JP1_TEST"][0]["player_involved"])
        self.assertEqual(details["JP1_TEST"][0]["survival"], "NOT_INVOLVED")
        self.assertIsNone(details["JP1_TEST"][0]["my_kda"])

    def test_compact_all_fight_does_not_turn_non_self_kda_into_zero(self):
        compact = compact_all_fight(sample_fight(False), player_team_id=100)
        self.assertIsNone(compact["my_kda"])
        self.assertEqual(compact["survival"], "NOT_INVOLVED")


if __name__ == "__main__":
    unittest.main()
