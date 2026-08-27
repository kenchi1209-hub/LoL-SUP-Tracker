import csv
import json
import os
from queue_map import is_allowed_queue_id
from raw_paths import DEFAULT_RAW_ROOT, iter_match_detail_paths
from data_paths import CSV_ROOT

CSV_PATH = CSV_ROOT / "participants.csv"

FIELDNAMES = [
    "match_id",
    "queue_id",
    "game_mode",
    "game_type",
    "patch",
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


def load_existing_keys(csv_path=CSV_PATH):
    if not os.path.exists(csv_path):
        return set()

    existing_keys = set()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            key = (
                row.get("match_id"),
                row.get("riot_id"),
                row.get("tag_line"),
            )
            existing_keys.add(key)

    return existing_keys


def export_participants_from_raw(raw_root=DEFAULT_RAW_ROOT, csv_path=CSV_PATH):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    existing_keys = load_existing_keys(csv_path)

    file_exists = os.path.exists(csv_path)

    added_count = 0
    skipped_count = 0

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)

        if not file_exists:
            writer.writeheader()

        for json_path in iter_match_detail_paths(raw_root):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            match_id = data["metadata"]["matchId"]
            info = data["info"]

            queue_id = info.get("queueId")

            if not is_allowed_queue_id(queue_id):
                skipped_count += 10
                continue

            game_mode = info.get("gameMode")
            game_type = info.get("gameType")
            patch = info.get("gameVersion", "").split(".")[0:2]
            patch = ".".join(patch)
            game_duration_seconds = info.get("gameDuration")

            for participant in info["participants"]:
                riot_id = participant.get("riotIdGameName", "")
                tag_line = participant.get("riotIdTagline", "")

                key = (
                    match_id,
                    riot_id,
                    tag_line,
                )

                if key in existing_keys:
                    skipped_count += 1
                    continue

                cs = (
                    participant.get("totalMinionsKilled", 0)
                    + participant.get("neutralMinionsKilled", 0)
                )

                writer.writerow(
                    {
                        "match_id": match_id,
                        "queue_id": queue_id,
                        "game_mode": game_mode,
                        "game_type": game_type,
                        "patch": patch,
                        "riot_id": riot_id,
                        "tag_line": tag_line,
                        "team_id": participant.get("teamId"),
                        "role": participant.get("teamPosition"),
                        "champion": participant.get("championName"),
                        "win": participant.get("win"),
                        "kills": participant.get("kills"),
                        "deaths": participant.get("deaths"),
                        "assists": participant.get("assists"),
                        "cs": cs,
                        "vision_score": participant.get("visionScore"),
                        "wards_placed": participant.get("wardsPlaced"),
                        "wards_killed": participant.get("wardsKilled"),
                        "gold_earned": participant.get("goldEarned"),
                        "total_damage_to_champions": participant.get("totalDamageDealtToChampions"),
                        "game_duration_seconds": game_duration_seconds,
                    }
                )

                existing_keys.add(key)
                added_count += 1

    print(f"participants.csv 出力完了: 追加 {added_count} 行 / スキップ {skipped_count} 行")
