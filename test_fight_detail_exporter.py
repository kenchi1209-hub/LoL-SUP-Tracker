import unittest

from fight_detail_exporter import compact_review_fight


def sample_fight(position):
    return {
        "fight_id": 1,
        "events": [
            {
                "type": "CHAMPION_KILL",
                "timestamp": 12345,
                "position": position,
                "killer": {"champion": "Leona"},
                "victim": {"champion": "Nami"},
                "assists": [],
            }
        ],
    }


class FightDetailExporterTest(unittest.TestCase):
    def test_compact_review_fight_keeps_structured_kill_position(self):
        fight = compact_review_fight(sample_fight({"x": 8421, "y": 6724}))

        self.assertEqual(fight["events"][0]["position"], {"x": 8421, "y": 6724})

    def test_compact_review_fight_keeps_missing_or_invalid_position_null(self):
        for position in (None, {}, {"x": 0}, {"x": "8421", "y": 6724}):
            with self.subTest(position=position):
                fight = compact_review_fight(sample_fight(position))
                self.assertIsNone(fight["events"][0]["position"])


if __name__ == "__main__":
    unittest.main()
