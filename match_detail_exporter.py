import json
import os
import tempfile

from raw_paths import DEFAULT_RAW_ROOT, iter_match_detail_paths, match_id_from_path


OUTPUT_PATH = "data/csv/match_details.json"
ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MIDDLE": 2, "BOTTOM": 3, "UTILITY": 4}
SIDE_BY_TEAM_ID = {100: "BLUE", 200: "RED"}


class MatchDetailExportError(RuntimeError):
    pass


def is_player(participant, my_puuid):
    return bool(my_puuid) and participant.get("puuid") == my_puuid


def compact_participant(participant, player_team_id, my_puuid):
    team_id = participant.get("teamId")
    if team_id is None:
        raise ValueError("participant teamId is missing")
    role = participant.get("teamPosition") or participant.get("individualPosition") or ""
    return {
        "relation": "ALLY" if team_id == player_team_id else "ENEMY",
        "role": role,
        "champion": participant.get("championName") or "Unknown",
        "kills": participant.get("kills", 0),
        "deaths": participant.get("deaths", 0),
        "assists": participant.get("assists", 0),
        "cs": participant.get("totalMinionsKilled", 0)
        + participant.get("neutralMinionsKilled", 0),
        "vision_score": participant.get("visionScore", 0),
        "damage_to_champions": participant.get("totalDamageDealtToChampions", 0),
        "is_self": is_player(participant, my_puuid),
    }


def compact_match(data, my_puuid):
    info = data.get("info") or {}
    participants = info.get("participants") or []
    player = next((p for p in participants if is_player(p, my_puuid)), None)
    if player is None:
        raise ValueError("player participant was not found")
    player_team_id = player.get("teamId")
    side = SIDE_BY_TEAM_ID.get(player_team_id)
    if side is None:
        raise ValueError(f"unsupported player teamId: {player_team_id}")

    compact = [
        compact_participant(participant, player_team_id, my_puuid)
        for participant in participants
        if isinstance(participant, dict)
    ]
    compact.sort(
        key=lambda participant: (
            participant["relation"] != "ALLY",
            ROLE_ORDER.get(participant["role"], 99),
            participant["champion"],
        )
    )
    return {
        "game_duration_seconds": info.get("gameDuration", 0),
        "side": side,
        "participants": compact,
    }


def build_match_details(my_puuid, raw_root=DEFAULT_RAW_ROOT):
    details = {}
    failures = []
    for path in sorted(iter_match_detail_paths(raw_root)):
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            match_id = (data.get("metadata") or {}).get("matchId") or match_id_from_path(path)
            if match_id in details:
                raise ValueError(f"duplicate match_id: {match_id}")
            details[match_id] = compact_match(data, my_puuid)
        except Exception as error:
            failures.append((path, error))
            print(f"Match Detail公開データ読み込み失敗: {path} | {error}")
    return details, failures


def load_existing_match_details(output_path):
    if not os.path.exists(output_path):
        return {}
    try:
        with open(output_path, "r", encoding="utf-8") as file:
            details = json.load(file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise MatchDetailExportError(
            f"既存Match Detail公開データを読み込めません: {output_path} | {error}"
        ) from error
    if not isinstance(details, dict):
        raise MatchDetailExportError("既存match_details.jsonのrootがobjectではありません")
    return details


def write_json_atomic(details, output_path):
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(output_path)}.", suffix=".tmp", dir=output_dir
    )
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(details, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def export_match_details(
    my_puuid,
    raw_root=DEFAULT_RAW_ROOT,
    output_path=OUTPUT_PATH,
    allow_removals=False,
):
    details, failures = build_match_details(my_puuid, raw_root)
    existing = load_existing_match_details(output_path)
    missing_ids = sorted(set(existing) - set(details))
    print(f"existing: {len(existing)}")
    print(f"generated: {len(details)}")
    print(f"missing: {len(missing_ids)}")
    for match_id in missing_ids:
        print(f"MISSING {match_id}")
    if failures:
        raise MatchDetailExportError(
            f"解析失敗が{len(failures)}件あるため、出力を中止しました"
        )
    if missing_ids and not allow_removals:
        raise MatchDetailExportError(
            "既存公開データからMatchが減少するため、出力を中止しました"
        )
    if not details and existing:
        raise MatchDetailExportError("生成対象が0件のため、既存公開データを維持します")
    write_json_atomic(details, output_path)
    print(f"match_details.json 出力完了: {len(details)}件 / {output_path}")
    return output_path
