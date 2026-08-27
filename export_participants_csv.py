import json
import csv
import os
from raw_paths import paths_for_match
from data_paths import get_data_paths

MATCH_ID = "JP1_591434669"
RAW_PATH = paths_for_match(MATCH_ID).detail
CSV_PATH = get_data_paths().csv / "participants.csv"

with open(RAW_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

participants = data["info"]["participants"]

os.makedirs(CSV_PATH.parent, exist_ok=True)

columns = [
    "match_id",
    "riot_id",
    "tag_line",
    "team_id",
    "role",
    "champion",
    "win",
    "kills",
    "deaths",
    "assists",
    "cs",
    "vision_score",
    "wards_placed",
    "wards_killed",
    "gold_earned",
    "total_damage_to_champions",
    "game_duration_seconds",
]

file_exists = os.path.exists(CSV_PATH)

with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=columns)

    if not file_exists:
        writer.writeheader()

    for p in participants:
        row = {
            "match_id": MATCH_ID,
            "riot_id": p.get("riotIdGameName"),
            "tag_line": p.get("riotIdTagline"),
            "team_id": p.get("teamId"),
            "role": p.get("teamPosition"),
            "champion": p.get("championName"),
            "win": p.get("win"),
            "kills": p.get("kills"),
            "deaths": p.get("deaths"),
            "assists": p.get("assists"),
            "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
            "vision_score": p.get("visionScore"),
            "wards_placed": p.get("wardsPlaced"),
            "wards_killed": p.get("wardsKilled"),
            "gold_earned": p.get("goldEarned"),
            "total_damage_to_champions": p.get("totalDamageDealtToChampions"),
            "game_duration_seconds": data["info"].get("gameDuration"),
        }
        writer.writerow(row)

print(f"CSV出力完了: {CSV_PATH}")
