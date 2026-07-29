import csv
import json
import os
from glob import glob
from datetime import datetime
from queue_map import is_allowed_queue_id
from config import GAME_NAME, TAG_LINE

MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"

MY_MATCH_COLUMNS = [
    "match_id",
    "date",
    "queue_id",
    "game_mode",
    "game_type",
    "patch",
    "role",
    "champion",
    "win",
    "kills",
    "deaths",
    "assists",
    "team_kills",
    "team_deaths",
    "team_assists",
    "cs",
    "cs_per_min",
    "vision_score",
    "vision_score_per_min",
    "wards_placed",
    "wards_killed",
    "control_wards_bought",
    "gold_earned",
    "total_damage_to_champions",
    "game_duration_seconds",
    "game_duration_min",
]

def format_game_date(game_creation_ms):
    dt = datetime.fromtimestamp(game_creation_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def get_team_totals(participants, team_id):
    team_players = [p for p in participants if p.get("teamId") == team_id]

    return {
        "team_kills": sum(p.get("kills", 0) for p in team_players),
        "team_deaths": sum(p.get("deaths", 0) for p in team_players),
        "team_assists": sum(p.get("assists", 0) for p in team_players),
    }

def is_me(participant, my_puuid):
    participant_puuid = participant.get("puuid")
    riot_game_name = participant.get("riotIdGameName", "")
    riot_tag_line = participant.get("riotIdTagline", "")

    if participant_puuid == my_puuid:
        return True

    if (
        riot_game_name.lower() == GAME_NAME.lower()
        and riot_tag_line.lower() == TAG_LINE.lower()
    ):
        return True

    return False

def my_participant_to_row(data, my_puuid):
    match_id = data["metadata"]["matchId"]
    info = data["info"]
    participants = info["participants"]

    me = None
    for p in participants:
        if is_me(p, my_puuid):
            me = p
            break

    if me is None:
        return None

    game_duration_seconds = info.get("gameDuration", 0)
    game_duration_min = game_duration_seconds / 60 if game_duration_seconds else 0

    cs = me.get("totalMinionsKilled", 0) + me.get("neutralMinionsKilled", 0)
    vision_score = me.get("visionScore", 0)

    team_totals = get_team_totals(participants, me.get("teamId"))

    return {
        "match_id": match_id,
        "date": format_game_date(info.get("gameCreation")),
        "queue_id": info.get("queueId"),
        "game_mode": info.get("gameMode"),
        "game_type": info.get("gameType"),
        "patch": info.get("gameVersion"),
        "role": me.get("teamPosition"),
        "champion": me.get("championName"),
        "win": me.get("win"),
        "kills": me.get("kills"),
        "deaths": me.get("deaths"),
        "assists": me.get("assists"),
        "team_kills": team_totals["team_kills"],
        "team_deaths": team_totals["team_deaths"],
        "team_assists": team_totals["team_assists"],
        "cs": cs,
        "cs_per_min": round(cs / game_duration_min, 2) if game_duration_min else 0,
        "vision_score": vision_score,
        "vision_score_per_min": round(vision_score / game_duration_min, 2) if game_duration_min else 0,
        "wards_placed": me.get("wardsPlaced", 0),
        "wards_killed": me.get("wardsKilled", 0),
        "control_wards_bought": me.get("visionWardsBoughtInGame", 0),
        "gold_earned": me.get("goldEarned"),
        "total_damage_to_champions": me.get("totalDamageDealtToChampions"),
        "game_duration_seconds": game_duration_seconds,
        "game_duration_min": round(game_duration_min, 2),
    }

def export_my_matches_from_raw(my_puuid, raw_dir="data/raw", csv_path=MY_MATCHES_CSV_PATH):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    json_paths = glob(f"{raw_dir}/*.json")

    rows = []
    skipped_count = 0

    for json_path in json_paths:
        with open(json_path, "r", encoding="utf-8") as jf:
            data = json.load(jf)

        queue_id = data["info"].get("queueId")

        if not is_allowed_queue_id(queue_id):
            skipped_count += 1
            continue

        row = my_participant_to_row(data, my_puuid)

        if row is None:
            skipped_count += 1
            continue

        rows.append(row)

    # data/raw が空（取得失敗・キャッシュ未作成）のとき既存CSVを空で上書きしない
    if not rows and os.path.exists(csv_path):
        print(f"対象試合が0件のため、my_matches.csvは更新しません（スキップ {skipped_count} 件）")
        return

    rows.sort(key=lambda r: r["date"], reverse=True)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MY_MATCH_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"my_matches.csv 出力完了: {len(rows)} 件 / スキップ {skipped_count} 件")