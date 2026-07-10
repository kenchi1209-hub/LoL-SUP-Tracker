import csv
import json
import os
from glob import glob
from queue_map import is_allowed_queue_id

PARTICIPANTS_CSV_PATH = "data/csv/participants.csv"

PARTICIPANT_COLUMNS = [
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

def load_existing_keys(csv_path):
    if not os.path.exists(csv_path):
        return set()

    existing_keys = set()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["match_id"], row["riot_id"], row["tag_line"])
            existing_keys.add(key)

    return existing_keys

def participant_to_row(match_id, data, participant):
    return {
        "match_id": match_id,
        "riot_id": participant.get("riotIdGameName"),
        "tag_line": participant.get("riotIdTagline"),
        "team_id": participant.get("teamId"),
        "role": participant.get("teamPosition"),
        "champion": participant.get("championName"),
        "win": participant.get("win"),
        "kills": participant.get("kills"),
        "deaths": participant.get("deaths"),
        "assists": participant.get("assists"),
        "cs": participant.get("totalMinionsKilled", 0) + participant.get("neutralMinionsKilled", 0),
        "vision_score": participant.get("visionScore"),
        "wards_placed": participant.get("wardsPlaced"),
        "wards_killed": participant.get("wardsKilled"),
        "gold_earned": participant.get("goldEarned"),
        "total_damage_to_champions": participant.get("totalDamageDealtToChampions"),
        "game_duration_seconds": data["info"].get("gameDuration"),
    }

def export_participants_from_raw(raw_dir="data/raw", csv_path=PARTICIPANTS_CSV_PATH):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    existing_keys = load_existing_keys(csv_path)
    file_exists = os.path.exists(csv_path)

    json_paths = glob(f"{raw_dir}/*.json")
    added_count = 0
    skipped_count = 0

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PARTICIPANT_COLUMNS)

        if not file_exists:
            writer.writeheader()

        for json_path in json_paths:
            with open(json_path, "r", encoding="utf-8") as jf:
                data = json.load(jf)

            match_id = data["metadata"]["matchId"]
            queue_id = data["info"].get("queueId")
            if not is_allowed_queue_id(queue_id):
                skipped_count += 10
                continue

        for participant in data["info"]["participants"]:
                key = (
                    match_id,
                    participant.get("riotIdGameName"),
                    participant.get("riotIdTagline"),
                )

                if key in existing_keys:
                    skipped_count += 1
                    continue

                row = participant_to_row(match_id, data, participant)
                writer.writerow(row)
                existing_keys.add(key)
                added_count += 1

    print(f"participants.csv 出力完了: 追加 {added_count} 行 / スキップ {skipped_count} 行")