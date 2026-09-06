import json
import os
import tempfile

from raw_paths import DEFAULT_RAW_ROOT, iter_match_detail_paths, match_id_from_path, paths_for_match
from rank_snapshot import rank_short
from data_paths import CSV_ROOT


OUTPUT_PATH = CSV_ROOT / "match_details.json"
ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MIDDLE": 2, "BOTTOM": 3, "UTILITY": 4}
SIDE_BY_TEAM_ID = {100: "BLUE", 200: "RED"}
TIMELINE_TARGETS = {"at_10": 600000, "at_15": 900000}


class MatchDetailExportError(RuntimeError):
    pass


def is_player(participant, my_puuid):
    return bool(my_puuid) and participant.get("puuid") == my_puuid


def percentage(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def participant_team_metrics(participants):
    totals = {}
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        team_id = participant.get("teamId")
        if team_id is None:
            continue
        total = totals.setdefault(team_id, {"kills": 0, "damage": 0})
        total["kills"] += participant.get("kills", 0) or 0
        total["damage"] += participant.get("totalDamageDealtToChampions", 0) or 0
    return totals


def value_or_none(value):
    return value if value is not None else None


def timeline_frame_metrics(timeline, participant_id, timestamp):
    """Return only the participant-frame values used by the public detail view."""
    frames = ((timeline or {}).get("info") or {}).get("frames") or []
    eligible = sorted(
        (
            frame for frame in frames
            if isinstance(frame, dict) and isinstance(frame.get("timestamp"), int)
            and frame["timestamp"] <= timestamp
        ),
        key=lambda frame: frame["timestamp"],
        reverse=True,
    )
    for timeline_frame in eligible:
        participant_frames = timeline_frame.get("participantFrames") or {}
        frame = participant_frames.get(str(participant_id)) or participant_frames.get(participant_id)
        if isinstance(frame, dict):
            return {
                "gold": value_or_none(frame.get("totalGold")),
                "xp": value_or_none(frame.get("xp")),
                "level": value_or_none(frame.get("level")),
                "minions": value_or_none(frame.get("minionsKilled")),
                "jungle_minions": value_or_none(frame.get("jungleMinionsKilled")),
            }
    return None


def level_timestamps(timeline, participant_id):
    result = {}
    for frame in ((timeline or {}).get("info") or {}).get("frames") or []:
        for event in frame.get("events") or []:
            if event.get("type") != "LEVEL_UP" or event.get("participantId") != participant_id:
                continue
            level = event.get("level")
            if level in (6, 11, 16) and level not in result:
                result[str(level)] = event.get("timestamp")
    return result


def timeline_details(timeline, participant_id):
    values = {
        key: timeline_frame_metrics(timeline, participant_id, timestamp)
        for key, timestamp in TIMELINE_TARGETS.items()
    }
    values["level_timestamps"] = level_timestamps(timeline, participant_id)
    return values


def challenge_value(participant, key):
    challenges = participant.get("challenges") or {}
    return challenges.get(key) if key in challenges else None


def compact_participant(participant, player_team_id, my_puuid, snapshot, team_totals, timeline):
    team_id = participant.get("teamId")
    if team_id is None:
        raise ValueError("participant teamId is missing")
    role = participant.get("teamPosition") or participant.get("individualPosition") or ""
    kills = participant.get("kills", 0) or 0
    assists = participant.get("assists", 0) or 0
    damage = participant.get("totalDamageDealtToChampions", 0) or 0
    totals = team_totals.get(team_id, {})
    participant_id = participant.get("participantId")
    minion_cs = participant.get("totalMinionsKilled", 0) or 0
    jungle_cs = participant.get("neutralMinionsKilled", 0) or 0
    return {
        "relation": "ALLY" if team_id == player_team_id else "ENEMY",
        "role": role,
        "champion": participant.get("championName") or "Unknown",
        "kills": kills,
        "deaths": participant.get("deaths", 0),
        "assists": assists,
        "win": bool(participant.get("win")),
        "cs": minion_cs + jungle_cs,
        "minion_cs": minion_cs,
        "jungle_cs": jungle_cs,
        "vision_score": participant.get("visionScore", 0),
        "damage_to_champions": damage,
        "is_self": is_player(participant, my_puuid),
        "rank": rank_short(snapshot, participant.get("participantId")),
        "kp_pct": percentage(kills + assists, totals.get("kills", 0)),
        "dmg_pct": percentage(damage, totals.get("damage", 0)),
        "gold_earned": participant.get("goldEarned", 0) or 0,
        "damage_taken": participant.get("totalDamageTaken", 0) or 0,
        "damage_self_mitigated": participant.get("damageSelfMitigated", 0) or 0,
        "largest_killing_spree": participant.get("largestKillingSpree", 0) or 0,
        "largest_multi_kill": participant.get("largestMultiKill", 0) or 0,
        "time_ccing_others": participant.get("timeCCingOthers", 0) or 0,
        "total_time_cc_dealt": participant.get("totalTimeCCDealt", 0) or 0,
        "total_heal": participant.get("totalHeal", 0) or 0,
        "heal_on_teammates": participant.get("totalHealsOnTeammates", 0) or 0,
        "shield_on_teammates": participant.get("totalDamageShieldedOnTeammates", 0) or 0,
        "wards_placed": participant.get("wardsPlaced", 0) or 0,
        "wards_killed": participant.get("wardsKilled", 0) or 0,
        "control_wards_bought": participant.get("visionWardsBoughtInGame", 0) or 0,
        "control_wards_placed": challenge_value(participant, "controlWardsPlaced"),
        "solo_kills": challenge_value(participant, "soloKills"),
        "timeline": timeline_details(timeline, participant_id),
    }


def add_lane_opponent_deltas(participants):
    """Add lane comparisons only when each side has exactly one explicit role."""
    for participant in participants:
        role = participant.get("role")
        opposite_relation = "ENEMY" if participant.get("relation") == "ALLY" else "ALLY"
        candidates = [
            other for other in participants
            if other.get("relation") == opposite_relation and other.get("role") == role
        ]
        if not role or len(candidates) != 1:
            continue
        opponent = candidates[0]
        comparison = {"champion": opponent.get("champion"), "role": role}
        for key in TIMELINE_TARGETS:
            own = (participant.get("timeline") or {}).get(key)
            other = (opponent.get("timeline") or {}).get(key)
            if not isinstance(own, dict) or not isinstance(other, dict):
                continue
            values = {}
            for field in ("gold", "xp", "minions", "jungle_minions"):
                if own.get(field) is not None and other.get(field) is not None:
                    values[field] = own[field] - other[field]
            if values:
                comparison[key] = values
        if any(key in comparison for key in TIMELINE_TARGETS):
            participant["lane_opponent"] = comparison


def compact_match(data, my_puuid, snapshot=None, timeline=None):
    info = data.get("info") or {}
    participants = info.get("participants") or []
    player = next((p for p in participants if is_player(p, my_puuid)), None)
    if player is None:
        raise ValueError("player participant was not found")
    player_team_id = player.get("teamId")
    side = SIDE_BY_TEAM_ID.get(player_team_id)
    if side is None:
        raise ValueError(f"unsupported player teamId: {player_team_id}")

    team_totals = participant_team_metrics(participants)
    compact = [
        compact_participant(participant, player_team_id, my_puuid, snapshot, team_totals, timeline)
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
    add_lane_opponent_deltas(compact)
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
            snapshot_path = paths_for_match(match_id, raw_root).rank_snapshot
            snapshot = None
            if snapshot_path.is_file():
                with snapshot_path.open("r", encoding="utf-8") as file:
                    snapshot = json.load(file)
            timeline_path = paths_for_match(match_id, raw_root).timeline
            timeline = None
            if timeline_path.is_file():
                with timeline_path.open("r", encoding="utf-8") as file:
                    timeline = json.load(file)
            if match_id in details:
                raise ValueError(f"duplicate match_id: {match_id}")
            details[match_id] = compact_match(data, my_puuid, snapshot, timeline)
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
        if hasattr(os, "fchmod"):
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
