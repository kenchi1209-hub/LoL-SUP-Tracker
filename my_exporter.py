import csv
import json
import os
from datetime import datetime

from queue_map import is_allowed_queue_id
from config import GAME_NAME, TAG_LINE
from timezone_utils import JST
from raw_paths import DEFAULT_RAW_ROOT, iter_match_detail_paths


MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"
TIMELINE_SUMMARY_CSV_PATH = "data/csv/timeline_summary.csv"


BASE_MATCH_COLUMNS = [
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


TIMELINE_COLUMNS = [
    "combat_events",
    "all_fights",
    "my_fights",
    "fight_wins",
    "fight_evens",
    "fight_losses",
    "survived_fights",
    "died_fights",
    "solo_fights",
    "small_fights",
    "skirmishes",
    "teamfights",
    "early_fights",
    "mid_fights",
    "late_fights",
    "objective_before_gain",
    "objective_before_loss",
    "objective_during_gain",
    "objective_during_loss",
    "objective_after_gain",
    "objective_after_loss",
]


MY_MATCH_COLUMNS = (
    BASE_MATCH_COLUMNS
    + TIMELINE_COLUMNS
)


def format_game_date(game_creation_ms):
    dt = datetime.fromtimestamp(
        game_creation_ms / 1000,
        tz=JST,
    )

    return dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_team_totals(participants, team_id):
    team_players = [
        p
        for p in participants
        if p.get("teamId") == team_id
    ]

    return {
        "team_kills": sum(
            p.get("kills", 0)
            for p in team_players
        ),
        "team_deaths": sum(
            p.get("deaths", 0)
            for p in team_players
        ),
        "team_assists": sum(
            p.get("assists", 0)
            for p in team_players
        ),
    }


def is_me(participant, my_puuid):
    participant_puuid = participant.get(
        "puuid"
    )

    riot_game_name = participant.get(
        "riotIdGameName",
        "",
    )

    riot_tag_line = participant.get(
        "riotIdTagline",
        "",
    )

    if participant_puuid == my_puuid:
        return True

    if (
        riot_game_name.lower()
        == GAME_NAME.lower()
        and riot_tag_line.lower()
        == TAG_LINE.lower()
    ):
        return True

    return False


def my_participant_to_row(data, my_puuid):
    match_id = data["metadata"]["matchId"]

    info = data["info"]
    participants = info["participants"]

    me = None

    for participant in participants:
        if is_me(
            participant,
            my_puuid,
        ):
            me = participant
            break

    if me is None:
        return None

    game_duration_seconds = info.get(
        "gameDuration",
        0,
    )

    game_duration_min = (
        game_duration_seconds / 60
        if game_duration_seconds
        else 0
    )

    cs = (
        me.get(
            "totalMinionsKilled",
            0,
        )
        + me.get(
            "neutralMinionsKilled",
            0,
        )
    )

    vision_score = me.get(
        "visionScore",
        0,
    )

    team_totals = get_team_totals(
        participants,
        me.get("teamId"),
    )

    return {
        "match_id": match_id,
        "date": format_game_date(
            info.get("gameCreation")
        ),
        "queue_id": info.get(
            "queueId"
        ),
        "game_mode": info.get(
            "gameMode"
        ),
        "game_type": info.get(
            "gameType"
        ),
        "patch": info.get(
            "gameVersion"
        ),
        "role": me.get(
            "teamPosition"
        ),
        "champion": me.get(
            "championName"
        ),
        "win": me.get(
            "win"
        ),
        "kills": me.get(
            "kills"
        ),
        "deaths": me.get(
            "deaths"
        ),
        "assists": me.get(
            "assists"
        ),
        "team_kills": (
            team_totals["team_kills"]
        ),
        "team_deaths": (
            team_totals["team_deaths"]
        ),
        "team_assists": (
            team_totals["team_assists"]
        ),
        "cs": cs,
        "cs_per_min": (
            round(
                cs / game_duration_min,
                2,
            )
            if game_duration_min
            else 0
        ),
        "vision_score": vision_score,
        "vision_score_per_min": (
            round(
                vision_score
                / game_duration_min,
                2,
            )
            if game_duration_min
            else 0
        ),
        "wards_placed": me.get(
            "wardsPlaced",
            0,
        ),
        "wards_killed": me.get(
            "wardsKilled",
            0,
        ),
        "control_wards_bought": me.get(
            "visionWardsBoughtInGame",
            0,
        ),
        "gold_earned": me.get(
            "goldEarned"
        ),
        "total_damage_to_champions": (
            me.get(
                "totalDamageDealtToChampions"
            )
        ),
        "game_duration_seconds": (
            game_duration_seconds
        ),
        "game_duration_min": round(
            game_duration_min,
            2,
        ),
    }


def to_int(value, default=0):
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def load_timeline_summary(
    csv_path=TIMELINE_SUMMARY_CSV_PATH,
):
    if not os.path.exists(csv_path):
        print(
            "timeline_summary.csv がありません。"
            "Timeline列は0で出力します。"
        )
        return {}

    timeline_by_match = {}

    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            match_id = row.get(
                "match_id"
            )

            if not match_id:
                continue

            my_fights = to_int(
                row.get("my_fights")
            )

            small_fights = to_int(
                row.get("small_fights")
            )

            skirmishes = to_int(
                row.get("skirmishes")
            )

            teamfights = to_int(
                row.get("teamfights")
            )

            solo_fights = max(
                0,
                my_fights
                - small_fights
                - skirmishes
                - teamfights,
            )

            timeline_by_match[
                match_id
            ] = {
                "combat_events": to_int(
                    row.get(
                        "combat_events"
                    )
                ),
                "all_fights": to_int(
                    row.get(
                        "all_fights"
                    )
                ),
                "my_fights": my_fights,
                "fight_wins": to_int(
                    row.get(
                        "fight_wins"
                    )
                ),
                "fight_evens": to_int(
                    row.get(
                        "fight_evens"
                    )
                ),
                "fight_losses": to_int(
                    row.get(
                        "fight_losses"
                    )
                ),
                "survived_fights": to_int(
                    row.get(
                        "survived_fights"
                    )
                ),
                "died_fights": to_int(
                    row.get(
                        "died_fights"
                    )
                ),
                "solo_fights": solo_fights,
                "small_fights": (
                    small_fights
                ),
                "skirmishes": (
                    skirmishes
                ),
                "teamfights": (
                    teamfights
                ),
                "early_fights": to_int(
                    row.get(
                        "early_fights"
                    )
                ),
                "mid_fights": to_int(
                    row.get(
                        "mid_fights"
                    )
                ),
                "late_fights": to_int(
                    row.get(
                        "late_fights"
                    )
                ),
                "objective_before_gain": to_int(
                    row.get(
                        "objective_before_gain"
                    )
                ),
                "objective_before_loss": to_int(
                    row.get(
                        "objective_before_loss"
                    )
                ),
                "objective_during_gain": to_int(
                    row.get(
                        "objective_during_gain"
                    )
                ),
                "objective_during_loss": to_int(
                    row.get(
                        "objective_during_loss"
                    )
                ),
                "objective_after_gain": to_int(
                    row.get(
                        "objective_after_gain"
                    )
                ),
                "objective_after_loss": to_int(
                    row.get(
                        "objective_after_loss"
                    )
                ),
            }

    return timeline_by_match


def add_timeline_summary(
    row,
    timeline_by_match,
):
    match_id = row["match_id"]

    timeline = timeline_by_match.get(
        match_id
    )

    if timeline is None:
        for column in TIMELINE_COLUMNS:
            row[column] = 0

        return row

    for column in TIMELINE_COLUMNS:
        row[column] = timeline.get(
            column,
            0,
        )

    return row


def export_my_matches_from_raw(
    my_puuid,
    raw_dir=DEFAULT_RAW_ROOT,
    csv_path=MY_MATCHES_CSV_PATH,
):
    os.makedirs(
        os.path.dirname(csv_path),
        exist_ok=True,
    )

    timeline_by_match = (
        load_timeline_summary()
    )

    json_paths = list(iter_match_detail_paths(raw_dir))

    rows = []
    skipped_count = 0
    timeline_joined_count = 0
    timeline_missing_count = 0

    for json_path in json_paths:
        with open(
            json_path,
            "r",
            encoding="utf-8",
        ) as jf:
            data = json.load(jf)

        queue_id = data["info"].get(
            "queueId"
        )

        if not is_allowed_queue_id(
            queue_id
        ):
            skipped_count += 1
            continue

        row = my_participant_to_row(
            data,
            my_puuid,
        )

        if row is None:
            skipped_count += 1
            continue

        match_id = row["match_id"]

        if match_id in timeline_by_match:
            timeline_joined_count += 1
        else:
            timeline_missing_count += 1

        row = add_timeline_summary(
            row,
            timeline_by_match,
        )

        rows.append(row)

    # data/rawが空の場合、
    # 既存CSVを空で上書きしない
    if (
        not rows
        and os.path.exists(csv_path)
    ):
        print(
            "対象試合が0件のため、"
            "my_matches.csvは更新しません"
            f"（スキップ {skipped_count} 件）"
        )
        return

    rows.sort(
        key=lambda row: row["date"],
        reverse=True,
    )

    with open(
        csv_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=MY_MATCH_COLUMNS,
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        "my_matches.csv 出力完了: "
        f"{len(rows)} 件 "
        f"/ スキップ {skipped_count} 件 "
        f"/ Timeline結合 {timeline_joined_count} 件 "
        f"/ Timelineなし {timeline_missing_count} 件"
    )
