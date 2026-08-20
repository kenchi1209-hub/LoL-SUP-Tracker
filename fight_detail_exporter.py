import argparse
import glob
import json
import os
import tempfile
from pathlib import Path

from champion_map import CHAMPION_JA_MAP
from raw_paths import DEFAULT_RAW_ROOT, iter_combat_timeline_paths, match_id_from_path


OUTPUT_PATH = "data/csv/fight_details.json"


class FightDetailExportError(RuntimeError):
    pass


def compact_fight_person(person, player_team_id=None, include_relation=False):
    if not isinstance(person, dict):
        return {"champion": "Unknown", "champion_name": "Unknown"}
    champion = person.get("champion") or "Unknown"
    compact = {
        "champion": champion,
        "champion_name": CHAMPION_JA_MAP.get(champion, champion),
    }
    team_id = person.get("team_id")
    if include_relation and player_team_id is not None and team_id is not None:
        compact["relation"] = "FRIENDLY" if team_id == player_team_id else "ENEMY"
    return compact


def compact_objective(objective):
    return {
        key: objective.get(key)
        for key in (
            "type",
            "timestamp",
            "relation",
            "monster_type",
            "monster_sub_type",
            "building_type",
            "lane_type",
        )
        if objective.get(key) is not None
    }


def compact_review_fight(fight, player_team_id=None):
    events = []
    for event in fight.get("events", []) or []:
        if not isinstance(event, dict) or event.get("type") != "CHAMPION_KILL":
            continue
        events.append(
            {
                "type": "CHAMPION_KILL",
                "timestamp": event.get("timestamp", 0),
                "killer": compact_fight_person(event.get("killer")),
                "victim": compact_fight_person(event.get("victim")),
                "assists": [
                    compact_fight_person(person)
                    for person in event.get("assists", []) or []
                    if isinstance(person, dict)
                ],
            }
        )

    return {
        "fight_id": fight.get("fight_id"),
        "phase": fight.get("phase", ""),
        "scale": fight.get("scale", ""),
        "survival": fight.get("survival", ""),
        "result": fight.get("result", ""),
        "start_timestamp": fight.get("start_timestamp", 0),
        "end_timestamp": fight.get("end_timestamp", 0),
        "duration_ms": fight.get("duration_ms", 0),
        "participant_count": fight.get("participant_count", 0),
        "participants": [
            compact_fight_person(person, player_team_id, include_relation=True)
            for person in fight.get("participants", []) or []
            if isinstance(person, dict)
        ],
        "my_kda": fight.get("my_kda") or {},
        "friendly_kills": fight.get("friendly_kills", 0),
        "enemy_kills": fight.get("enemy_kills", 0),
        "objective_context": fight.get("objective_context") or {},
        "objectives_before": [
            compact_objective(objective)
            for objective in fight.get("objectives_before", []) or []
            if isinstance(objective, dict)
        ],
        "objectives_during": [
            compact_objective(objective)
            for objective in fight.get("objectives_during", []) or []
            if isinstance(objective, dict)
        ],
        "objectives_after": [
            compact_objective(objective)
            for objective in fight.get("objectives_after", []) or []
            if isinstance(objective, dict)
        ],
        "events": events,
    }


def build_fight_details(timeline_pattern=None, raw_root=DEFAULT_RAW_ROOT):
    details = {}
    failures = []
    paths = (
        sorted(Path(path) for path in glob.glob(timeline_pattern))
        if timeline_pattern
        else sorted(iter_combat_timeline_paths(raw_root))
    )
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("combat timeline root must be an object")
            match_id = data.get("match_id") or match_id_from_path(path)
            if match_id in details:
                raise ValueError(f"duplicate match_id: {match_id}")
            fights = data.get("review_fights", [])
            if not isinstance(fights, list):
                fights = []
            player_team_id = (data.get("participant") or {}).get("team_id")
            details[match_id] = [
                compact_review_fight(fight, player_team_id)
                for fight in fights
                if isinstance(fight, dict)
            ]
        except Exception as error:
            failures.append((path, error))
            print(f"Fight Detail読み込み失敗: {path} | {error}")

    return details, failures


def load_existing_fight_details(output_path):
    if not os.path.exists(output_path):
        return {}
    try:
        with open(output_path, "r", encoding="utf-8") as file:
            details = json.load(file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise FightDetailExportError(
            f"既存Fight Detailを読み込めません: {output_path} | {error}"
        ) from error
    if not isinstance(details, dict):
        raise FightDetailExportError("既存fight_details.jsonのrootがobjectではありません")
    return details


def write_json_atomic(details, output_path):
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(output_path)}.",
        suffix=".tmp",
        dir=output_dir,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            json.dump(details, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def export_fight_details(
    output_path=OUTPUT_PATH,
    allow_removals=False,
    timeline_pattern=None,
    raw_root=DEFAULT_RAW_ROOT,
):
    details, failures = build_fight_details(timeline_pattern, raw_root)
    existing_details = load_existing_fight_details(output_path)
    missing_ids = sorted(set(existing_details) - set(details))

    print(f"existing: {len(existing_details)}")
    print(f"generated: {len(details)}")
    print(f"missing: {len(missing_ids)}")
    for match_id in missing_ids:
        print(f"MISSING {match_id}")

    if failures:
        raise FightDetailExportError(
            f"解析失敗が{len(failures)}件あるため、出力を中止しました"
        )
    if missing_ids and not allow_removals:
        raise FightDetailExportError(
            "既存公開データからMatchが減少するため、出力を中止しました。"
            "意図的に削除する場合のみ--allow-removalsを指定してください"
        )

    write_json_atomic(details, output_path)

    print(
        f"fight_details.json 出力完了: {len(details)}件 / "
        f"失敗 {len(failures)}件 / {output_path}"
    )
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="combat timelineから公開用Fight Detail JSONを生成します"
    )
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help="既存公開JSONからMatchが減少する出力を明示的に許可します",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        export_fight_details(allow_removals=args.allow_removals)
    except FightDetailExportError as error:
        raise SystemExit(f"Fight Detail出力中止: {error}") from error
