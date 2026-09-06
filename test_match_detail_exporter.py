import unittest

from match_detail_exporter import compact_match


def participant(participant_id, team_id, role, champion, win, **overrides):
    value = {
        "participantId": participant_id, "teamId": team_id, "teamPosition": role,
        "championName": champion, "puuid": "self" if participant_id == 1 else f"player-{participant_id}",
        "win": win, "kills": 2, "deaths": 3, "assists": 4,
        "totalMinionsKilled": 80, "neutralMinionsKilled": 20, "visionScore": 30,
        "totalDamageDealtToChampions": 10000, "goldEarned": 8000,
        "totalDamageTaken": 7000, "damageSelfMitigated": 6000,
        "largestKillingSpree": 2, "largestMultiKill": 2,
        "timeCCingOthers": 40, "totalTimeCCDealt": 40000,
        "totalHeal": 500, "totalHealsOnTeammates": 300,
        "totalDamageShieldedOnTeammates": 200, "wardsPlaced": 5,
        "wardsKilled": 2, "visionWardsBoughtInGame": 1,
        "challenges": {"soloKills": 1, "controlWardsPlaced": 2},
    }
    value.update(overrides)
    return value


def timeline_frame(timestamp, first_gold, second_gold):
    def frame(participant_id, gold):
        return {"participantId": participant_id, "totalGold": gold, "xp": gold * 2,
                "level": 6, "minionsKilled": gold // 100, "jungleMinionsKilled": 10}
    return {"timestamp": timestamp, "participantFrames": {"1": frame(1, first_gold), "6": frame(6, second_gold)}, "events": []}


class MatchDetailExporterTest(unittest.TestCase):
    def test_compact_match_keeps_public_detail_stats_and_timeline_deltas(self):
        data = {"info": {"gameDuration": 1200, "participants": [
            participant(1, 100, "TOP", "Aatrox", True),
            participant(6, 200, "TOP", "Garen", False, totalDamageDealtToChampions=9000),
        ]}}
        timeline = {"info": {"frames": [
            timeline_frame(600000, 5000, 4500),
            timeline_frame(900000, 8000, 7000),
            {"timestamp": 650000, "participantFrames": {}, "events": [{"type": "LEVEL_UP", "participantId": 1, "level": 6, "timestamp": 640000}]},
        ]}}
        detail = compact_match(data, "self", timeline=timeline)
        self.assertEqual(len(detail["participants"]), 2)
        own = next(item for item in detail["participants"] if item["is_self"])
        self.assertEqual(own["gold_earned"], 8000)
        self.assertEqual(own["damage_taken"], 7000)
        self.assertEqual(own["timeline"]["at_10"]["gold"], 5000)
        self.assertEqual(own["timeline"]["at_15"]["gold"], 8000)
        self.assertEqual(own["timeline"]["level_timestamps"]["6"], 640000)
        self.assertEqual(own["lane_opponent"]["at_10"]["gold"], 500)
        self.assertEqual(own["lane_opponent"]["at_15"]["gold"], 1000)
        self.assertNotIn("puuid", str(detail).lower())

    def test_missing_timeline_values_remain_missing_not_zero(self):
        data = {"info": {"gameDuration": 1200, "participants": [
            participant(1, 100, "TOP", "Aatrox", True, visionScore=0, wardsPlaced=0),
        ]}}
        detail = compact_match(data, "self", timeline={"info": {"frames": []}})
        own = detail["participants"][0]
        self.assertIsNone(own["timeline"]["at_10"])
        self.assertEqual(own["vision_score"], 0)
        self.assertEqual(own["wards_placed"], 0)
