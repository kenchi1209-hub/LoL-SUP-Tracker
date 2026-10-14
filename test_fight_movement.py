import unittest

from analyze_timeline import (
    engaged_reasons_for_event,
    fight_movement_snapshot,
)


class FightMovementTest(unittest.TestCase):
    def setUp(self):
        self.participants = {
            participant_id: {
                "participantId": participant_id,
                "championName": f"Champion{participant_id}",
                "teamId": 100 if participant_id <= 5 else 200,
                "teamPosition": "UTILITY" if participant_id == 5 else "BOTTOM" if participant_id in (4, 9) else "TOP",
            }
            for participant_id in range(1, 11)
        }
        self.frames = [
            {
                "timestamp": 900,
                "participantFrames": {
                    str(participant_id): {"position": {"x": participant_id * 10, "y": participant_id * 20}}
                    for participant_id in range(1, 11)
                },
            },
            {
                "timestamp": 1300,
                "participantFrames": {
                    str(participant_id): {"position": {"x": participant_id * 10 + 4, "y": participant_id * 20 + 8}}
                    for participant_id in range(1, 11)
                },
            },
        ]
        self.fight = {
            "start_timestamp": 1000,
            "end_timestamp": 1200,
            "events": [
                {
                    "timestamp": 1000,
                    "position": {"x": 100, "y": 200},
                    "killerId": 1,
                    "victimId": 6,
                    "assistingParticipantIds": [2, 0, 11],
                    "victimDamageReceived": [{"participantId": 3}, {"participantId": 0}],
                    "victimDamageDealt": [{"participantId": 7}, {"participantId": 11}],
                }
            ],
        }

    def test_engagement_includes_kill_assist_and_damage_but_ignores_invalid_ids(self):
        reasons = engaged_reasons_for_event(self.fight["events"][0])
        self.assertEqual(set(reasons), {1, 2, 3, 6, 7})
        self.assertEqual(reasons[3], {"damage_source"})
        self.assertEqual(reasons[7], {"damage_target"})

    def test_snapshot_uses_bounding_frames_without_interpolation(self):
        result = fight_movement_snapshot(self.fight, self.frames, self.participants, 100, 5)
        snapshot = result["movement_snapshot"]
        self.assertEqual(snapshot["pre_frame_timestamp"], 900)
        self.assertEqual(snapshot["post_frame_timestamp"], 1300)
        self.assertEqual(snapshot["pre_offset_seconds"], -0.1)
        self.assertEqual(snapshot["post_offset_seconds"], 0.1)
        self.assertEqual(len(snapshot["participants"]), 10)
        person = snapshot["participants"][0]
        self.assertEqual(person["start"], {"x": 10, "y": 20})
        self.assertEqual(person["end"], {"x": 14, "y": 28})
        self.assertEqual(person["distance"], (4 ** 2 + 8 ** 2) ** 0.5)
        self.assertTrue(snapshot["participants"][4]["is_self"])
        self.assertEqual(result["kill_event_positions"], [{"timestamp": 1000, "x": 100, "y": 200}])
        self.assertEqual((result["engaged_ally_count"], result["engaged_enemy_count"], result["engaged_total_count"]), (3, 2, 5))

    def test_missing_coordinate_remains_missing(self):
        self.frames[1]["participantFrames"]["10"] = {"position": None}
        result = fight_movement_snapshot(self.fight, self.frames, self.participants, 100, 5)
        person = result["movement_snapshot"]["participants"][-1]
        self.assertIsNone(person["end"])
        self.assertIsNone(person["distance"])


if __name__ == "__main__":
    unittest.main()
