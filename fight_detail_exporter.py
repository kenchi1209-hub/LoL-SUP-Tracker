import glob
import json
import os

from champion_map import CHAMPION_JA_MAP


TIMELINE_PATTERN = "data/raw/timeline/*_combat_timeline.json"
OUTPUT_PATH = "data/csv/fight_details.json"


def compact_fight_person(person):
    if not isinstance(person, dict):
        return {"champion": "Unknown", "champion_name": "Unknown"}
    champion = person.get("champion") or "Unknown"
    return {
        "champion": champion,
        "champion_name": CHAMPION_JA_MAP.get(champion, champion),
    }


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


def compact_review_fight(fight):
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
            compact_fight_person(person)
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


def export_fight_details(output_path=OUTPUT_PATH):
    details = {}
    failed = 0
    for path in sorted(glob.glob(TIMELINE_PATTERN)):
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("combat timeline root must be an object")
            match_id = data.get("match_id") or os.path.basename(path).removesuffix(
                "_combat_timeline.json"
            )
            fights = data.get("review_fights", [])
            if not isinstance(fights, list):
                fights = []
            details[match_id] = [
                compact_review_fight(fight)
                for fight in fights
                if isinstance(fight, dict)
            ]
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failed += 1
            print(f"Fight Detail読み込み失敗: {path} | {error}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(details, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")

    print(
        f"fight_details.json 出力完了: {len(details)}件 / "
        f"失敗 {failed}件 / {output_path}"
    )
    return output_path


if __name__ == "__main__":
    export_fight_details()
