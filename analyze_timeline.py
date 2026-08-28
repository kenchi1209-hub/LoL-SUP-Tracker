import argparse
import copy
import json
import math
import os
from raw_paths import DEFAULT_RAW_ROOT, paths_for_match

from config import GAME_NAME, TAG_LINE


# ============================================================
# Settings
# ============================================================

EVENT_TYPES = {
    "CHAMPION_KILL",
    "WARD_PLACED",
    "WARD_KILL",
    "ELITE_MONSTER_KILL",
    "BUILDING_KILL",
}

OBJECTIVE_EVENT_TYPES = {
    "ELITE_MONSTER_KILL",
    "BUILDING_KILL",
}

# Fight判定
FIGHT_TIME_GAP_MS = 30 * 1000
FIGHT_EXTENDED_TIME_GAP_MS = 45 * 1000
FIGHT_DISTANCE = 3500

# Objective紐付け
OBJECTIVE_CONTEXT_WINDOW_MS = 45 * 1000
BUILDING_OBJECTIVE_DISTANCE = 4000

# Phase判定
EARLY_END_MS = 14 * 60 * 1000
MID_END_MS = 25 * 60 * 1000


# ============================================================
# Basic
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def find_player(
    match_data,
    puuid=None,
    participant_id=None,
    champion=None,
):
    participants = match_data["info"]["participants"]

    # main.pyなど外部処理ではPUUIDを最優先
    if puuid:
        return next(
            p
            for p in participants
            if p.get("puuid") == puuid
        )

    if participant_id is not None:
        return next(
            p
            for p in participants
            if p["participantId"] == participant_id
        )

    if champion:
        return next(
            p
            for p in participants
            if p["championName"].lower() == champion.lower()
        )

    # CLI単発実行時などは従来どおりRiot IDから特定
    return next(
        p
        for p in participants
        if p.get("riotIdGameName", "").lower() == (GAME_NAME or "").lower()
        and p.get("riotIdTagline", "").lower() == (TAG_LINE or "").lower()
    )


def participant_label(participants, participant_id):
    participant = participants.get(participant_id)

    if not participant:
        return None

    return {
        "participant_id": participant_id,
        "champion": participant["championName"],
        "team_id": participant["teamId"],
    }


def format_timestamp(timestamp):
    total_seconds = timestamp / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60

    return f"{minutes:02d}:{seconds:06.3f}"


def nearest_frame(frames, participant_id, timestamp):
    frame = min(
        frames,
        key=lambda item: abs(item["timestamp"] - timestamp),
    )

    participant_frame = frame["participantFrames"][str(participant_id)]

    return {
        "frame_timestamp": frame["timestamp"],
        "offset_ms": frame["timestamp"] - timestamp,
        "level": participant_frame["level"],
        "current_gold": participant_frame["currentGold"],
        "total_gold": participant_frame["totalGold"],
        "cs": (
            participant_frame["minionsKilled"]
            + participant_frame["jungleMinionsKilled"]
        ),
        "position": participant_frame["position"],
        "xp": participant_frame["xp"],
    }


# ============================================================
# Event helpers
# ============================================================

def compact_event(
    event,
    participants,
    player_team_id,
    center_timestamp,
):
    compact = {
        "type": event["type"],
        "timestamp": event["timestamp"],
        "offset_ms": event["timestamp"] - center_timestamp,
    }

    if event["type"] == "CHAMPION_KILL":
        killer = participant_label(
            participants,
            event.get("killerId"),
        )

        victim = participant_label(
            participants,
            event.get("victimId"),
        )

        assists = [
            participant_label(
                participants,
                participant_id,
            )
            for participant_id in event.get(
                "assistingParticipantIds",
                [],
            )
        ]

        compact.update(
            {
                "position": event.get("position"),
                "killer": killer,
                "victim": victim,
                "assists": assists,
                "winning_team_id": (
                    killer["team_id"]
                    if killer
                    else None
                ),
                "is_friendly_kill": bool(
                    killer
                    and killer["team_id"] == player_team_id
                ),
            }
        )

    elif event["type"] == "WARD_PLACED":
        compact.update(
            {
                "creator": participant_label(
                    participants,
                    event.get("creatorId"),
                ),
                "ward_type": event.get("wardType"),
            }
        )

    elif event["type"] == "WARD_KILL":
        compact.update(
            {
                "killer": participant_label(
                    participants,
                    event.get("killerId"),
                ),
                "ward_type": event.get("wardType"),
            }
        )

    elif event["type"] == "ELITE_MONSTER_KILL":
        compact.update(
            {
                "killer": participant_label(
                    participants,
                    event.get("killerId"),
                ),
                "monster_type": event.get("monsterType"),
                "monster_sub_type": event.get("monsterSubType"),
                "position": event.get("position"),
            }
        )

    elif event["type"] == "BUILDING_KILL":
        compact.update(
            {
                "killer": participant_label(
                    participants,
                    event.get("killerId"),
                ),
                "team_id": event.get("teamId"),
                "building_type": event.get("buildingType"),
                "lane_type": event.get("laneType"),
                "position": event.get("position"),
            }
        )

    return compact


def get_player_relation(event, participant_id):
    if event.get("killerId") == participant_id:
        return "KILL"

    if event.get("victimId") == participant_id:
        return "DEATH"

    if participant_id in event.get(
        "assistingParticipantIds",
        [],
    ):
        return "ASSIST"

    return None


def event_participant_ids(event):
    participant_ids = set()

    killer_id = event.get("killerId")
    victim_id = event.get("victimId")

    if killer_id:
        participant_ids.add(killer_id)

    if victim_id:
        participant_ids.add(victim_id)

    participant_ids.update(
        event.get(
            "assistingParticipantIds",
            [],
        )
    )

    return participant_ids


def position_distance(position_a, position_b):
    if not position_a or not position_b:
        return None

    dx = position_a.get("x", 0) - position_b.get("x", 0)
    dy = position_a.get("y", 0) - position_b.get("y", 0)

    return math.sqrt(
        dx * dx
        + dy * dy
    )


# ============================================================
# Fight grouping
# ============================================================

def should_continue_fight(fight, event):
    previous_event = fight["events"][-1]

    time_gap = (
        event["timestamp"]
        - previous_event["timestamp"]
    )

    if time_gap <= FIGHT_TIME_GAP_MS:
        distance = position_distance(
            previous_event.get("position"),
            event.get("position"),
        )

        if distance is None:
            return True

        return distance <= FIGHT_DISTANCE

    if time_gap <= FIGHT_EXTENDED_TIME_GAP_MS:
        distance = position_distance(
            previous_event.get("position"),
            event.get("position"),
        )

        if (
            distance is None
            or distance > FIGHT_DISTANCE
        ):
            return False

        fight_participants = set()

        for fight_event in fight["events"]:
            fight_participants.update(
                event_participant_ids(
                    fight_event
                )
            )

        current_participants = event_participant_ids(
            event
        )

        return bool(
            fight_participants
            & current_participants
        )

    return False


def build_fight(
    fight_id,
    raw_events,
    participants,
    player,
):
    participant_id = player["participantId"]
    player_team_id = player["teamId"]

    start_timestamp = raw_events[0]["timestamp"]
    end_timestamp = raw_events[-1]["timestamp"]

    participant_ids = set()

    friendly_kills = 0
    enemy_kills = 0

    my_kills = 0
    my_deaths = 0
    my_assists = 0

    my_relations = []
    compact_events = []
    positions = []

    for event in raw_events:
        participant_ids.update(
            event_participant_ids(event)
        )

        position = event.get("position")

        if position:
            positions.append(position)

        killer = participants.get(
            event.get("killerId")
        )

        if killer:
            if killer["teamId"] == player_team_id:
                friendly_kills += 1
            else:
                enemy_kills += 1

        relation = get_player_relation(
            event,
            participant_id,
        )

        if relation == "KILL":
            my_kills += 1

        elif relation == "DEATH":
            my_deaths += 1

        elif relation == "ASSIST":
            my_assists += 1

        if relation:
            my_relations.append(
                {
                    "relation": relation,
                    "timestamp": event["timestamp"],
                }
            )

        compact_events.append(
            compact_event(
                event,
                participants,
                player_team_id,
                start_timestamp,
            )
        )

    involved = (
        my_kills > 0
        or my_deaths > 0
        or my_assists > 0
    )

    if friendly_kills > enemy_kills:
        result = "WIN"

    elif friendly_kills < enemy_kills:
        result = "LOSS"

    else:
        result = "EVEN"

    center_position = None

    if positions:
        center_position = {
            "x": round(
                sum(
                    position["x"]
                    for position in positions
                )
                / len(positions)
            ),
            "y": round(
                sum(
                    position["y"]
                    for position in positions
                )
                / len(positions)
            ),
        }

    participant_list = [
        participant_label(
            participants,
            current_id,
        )
        for current_id in sorted(participant_ids)
    ]

    return {
        "fight_id": fight_id,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "duration_ms": (
            end_timestamp
            - start_timestamp
        ),
        "center_position": center_position,
        "participant_count": len(participant_ids),
        "participants": participant_list,
        "friendly_kills": friendly_kills,
        "enemy_kills": enemy_kills,
        "result": result,
        "player_involved": involved,
        "my_kda": {
            "kills": my_kills,
            "deaths": my_deaths,
            "assists": my_assists,
        },
        "my_relations": my_relations,
        "events": compact_events,
        "objective_events": [],
    }


def group_fights(
    champion_kills,
    participants,
    player,
):
    if not champion_kills:
        return []

    raw_fights = []

    current_fight = {
        "events": [
            champion_kills[0]
        ]
    }

    for event in champion_kills[1:]:
        if should_continue_fight(
            current_fight,
            event,
        ):
            current_fight[
                "events"
            ].append(event)

        else:
            raw_fights.append(
                current_fight
            )

            current_fight = {
                "events": [
                    event
                ]
            }

    raw_fights.append(
        current_fight
    )

    fights = []

    for index, fight in enumerate(
        raw_fights,
        start=1,
    ):
        fights.append(
            build_fight(
                index,
                fight["events"],
                participants,
                player,
            )
        )

    return fights


# ============================================================
# Objective
# ============================================================

def distance_from_event_to_fight(
    event_timestamp,
    fight,
):
    start = fight["start_timestamp"]
    end = fight["end_timestamp"]

    if (
        start
        <= event_timestamp
        <= end
    ):
        return 0

    if event_timestamp < start:
        return (
            start
            - event_timestamp
        )

    return (
        event_timestamp
        - end
    )


def objective_event_info(
    event,
    participants,
    player_team_id,
):
    event_type = event["type"]

    info = {
        "type": event_type,
        "timestamp": event["timestamp"],
        "position": event.get("position"),
    }

    if event_type == "ELITE_MONSTER_KILL":
        killer = participant_label(
            participants,
            event.get("killerId"),
        )

        team_id = (
            killer["team_id"]
            if killer
            else None
        )

        relation = "UNKNOWN"

        if team_id == player_team_id:
            relation = "FRIENDLY"

        elif team_id is not None:
            relation = "ENEMY"

        info.update(
            {
                "relation": relation,
                "killer": killer,
                "monster_type": (
                    event.get("monsterType")
                ),
                "monster_sub_type": (
                    event.get("monsterSubType")
                ),
            }
        )

    elif event_type == "BUILDING_KILL":
        killer = participant_label(
            participants,
            event.get("killerId"),
        )

        destroyed_team_id = event.get(
            "teamId"
        )

        relation = "UNKNOWN"

        # BUILDING_KILLのteamIdは破壊された側
        if destroyed_team_id:
            if (
                destroyed_team_id
                != player_team_id
            ):
                relation = "FRIENDLY"
            else:
                relation = "ENEMY"

        elif killer:
            relation = (
                "FRIENDLY"
                if killer["team_id"]
                == player_team_id
                else "ENEMY"
            )

        info.update(
            {
                "relation": relation,
                "killer": killer,
                "destroyed_team_id": (
                    destroyed_team_id
                ),
                "building_type": (
                    event.get("buildingType")
                ),
                "lane_type": (
                    event.get("laneType")
                ),
            }
        )

    return info


def attach_objectives_to_fights(
    events,
    fights,
    participants,
    player_team_id,
):
    if not fights:
        return

    objective_events = [
        event
        for event in events
        if event["type"]
        in OBJECTIVE_EVENT_TYPES
    ]

    for event in objective_events:
        timestamp = event["timestamp"]
        event_type = event["type"]

        candidate_fights = []

        for fight in fights:
            time_distance = (
                distance_from_event_to_fight(
                    timestamp,
                    fight,
                )
            )

            if (
                time_distance
                > OBJECTIVE_CONTEXT_WINDOW_MS
            ):
                continue

            # Tower / Inhibitorのみ位置判定
            if event_type == "BUILDING_KILL":
                fight_position = fight.get(
                    "center_position"
                )

                event_position = event.get(
                    "position"
                )

                building_distance = position_distance(
                    fight_position,
                    event_position,
                )

                if (
                    building_distance is not None
                    and building_distance
                    > BUILDING_OBJECTIVE_DISTANCE
                ):
                    continue

            candidate_fights.append(
                (
                    time_distance,
                    fight,
                )
            )

        if not candidate_fights:
            continue

        candidate_fights.sort(
            key=lambda item: item[0]
        )

        _, nearest_fight = (
            candidate_fights[0]
        )

        info = objective_event_info(
            event,
            participants,
            player_team_id,
        )

        info[
            "offset_from_fight_start_ms"
        ] = (
            timestamp
            - nearest_fight[
                "start_timestamp"
            ]
        )

        if event_type == "BUILDING_KILL":
            info[
                "distance_from_fight"
            ] = position_distance(
                nearest_fight.get(
                    "center_position"
                ),
                event.get(
                    "position"
                ),
            )

        nearest_fight[
            "objective_events"
        ].append(info)


def attach_objectives_to_my_fights(
    events,
    my_fights,
    participants,
    player_team_id,
):
    """Keep the established review-objective assignment API unchanged."""
    attach_objectives_to_fights(
        events,
        my_fights,
        participants,
        player_team_id,
    )


# ============================================================
# Review Context
# ============================================================

def get_game_phase(timestamp):
    if timestamp < EARLY_END_MS:
        return "EARLY"

    if timestamp < MID_END_MS:
        return "MID"

    return "LATE"


def get_fight_scale(participant_count):
    if participant_count <= 2:
        return "SOLO"

    if participant_count <= 4:
        return "SMALL"

    if participant_count <= 7:
        return "SKIRMISH"

    return "TEAMFIGHT"


def get_survival(fight):
    if fight["my_kda"]["deaths"] > 0:
        return "DIED"

    return "SURVIVED"


def get_objective_timing(
    objective,
    fight,
):
    timestamp = objective["timestamp"]

    if timestamp < fight["start_timestamp"]:
        return "BEFORE"

    if timestamp <= fight["end_timestamp"]:
        return "DURING"

    return "AFTER"


def evaluate_objective_group(objectives):
    if not objectives:
        return "NONE"

    friendly = any(
        objective.get("relation")
        == "FRIENDLY"
        for objective in objectives
    )

    enemy = any(
        objective.get("relation")
        == "ENEMY"
        for objective in objectives
    )

    if friendly and enemy:
        return "TRADE"

    if friendly:
        return "GAIN"

    if enemy:
        return "LOSS"

    return "NONE"


def build_fight_context(fights, include_player_involved=False):
    context_fights = []

    for fight in fights:
        objectives_before = []
        objectives_during = []
        objectives_after = []

        for objective in fight.get(
            "objective_events",
            [],
        ):
            timing = get_objective_timing(
                objective,
                fight,
            )

            if timing == "BEFORE":
                objectives_before.append(
                    objective
                )

            elif timing == "DURING":
                objectives_during.append(
                    objective
                )

            else:
                objectives_after.append(
                    objective
                )

        objective_context = {
            "before": evaluate_objective_group(
                objectives_before
            ),
            "during": evaluate_objective_group(
                objectives_during
            ),
            "after": evaluate_objective_group(
                objectives_after
            ),
        }

        context_fight = {
                "fight_id": fight["fight_id"],
                "phase": get_game_phase(
                    fight["start_timestamp"]
                ),
                "scale": get_fight_scale(
                    fight["participant_count"]
                ),
                "survival": (
                    get_survival(fight)
                    if fight["player_involved"]
                    else "NOT_INVOLVED"
                ),
                "result": fight["result"],
                "start_timestamp": (
                    fight["start_timestamp"]
                ),
                "end_timestamp": (
                    fight["end_timestamp"]
                ),
                "duration_ms": (
                    fight["duration_ms"]
                ),
                "participant_count": (
                    fight["participant_count"]
                ),
                "participants": (
                    fight["participants"]
                ),
                "center_position": (
                    fight["center_position"]
                ),
                "my_kda": (
                    fight["my_kda"]
                    if fight["player_involved"]
                    else None
                ),
                "friendly_kills": (
                    fight["friendly_kills"]
                ),
                "enemy_kills": (
                    fight["enemy_kills"]
                ),
                "objective_context": (
                    objective_context
                ),
                "objectives_before": (
                    objectives_before
                ),
                "objectives_during": (
                    objectives_during
                ),
                "objectives_after": (
                    objectives_after
                ),
                "events": fight["events"],
                "my_relations": (
                    fight["my_relations"]
                ),
            }
        if include_player_involved:
            context_fight["player_involved"] = fight["player_involved"]
        context_fights.append(context_fight)

    return context_fights


def build_review_context(my_fights):
    """Build the established SELF-only review payload without new fields."""
    return build_fight_context(my_fights)


def build_all_fight_context(fights):
    """Build display context for every detected fight, including non-SELF fights."""
    return build_fight_context(fights, include_player_involved=True)


def build_all_fight_context_from_timeline(
    match_data,
    timeline_data,
    player,
):
    """Rebuild all-Fight display context without changing review-context behavior."""
    combat = analyze_combat(match_data, timeline_data, player)
    fights = copy.deepcopy(combat["fights"])

    # analyze_combat assigns objectives to the SELF-only review subset.  Resetting
    # this copy keeps the established review assignment separate from all-Fight data.
    for fight in fights:
        fight["objective_events"] = []

    participant_map = {
        participant["participantId"]: participant
        for participant
        in match_data["info"]["participants"]
    }
    if not participant_map:
        return []

    events = sorted(
        (
            event
            for frame in timeline_data["info"]["frames"]
            for event in frame["events"]
        ),
        key=lambda event: event["timestamp"],
    )
    attach_objectives_to_fights(
        events,
        fights,
        participant_map,
        player["teamId"],
    )
    return build_all_fight_context(fights)


# ============================================================
# Combat analysis
# ============================================================

def analyze_combat(
    match_data,
    timeline_data,
    player,
    window_seconds=60,
):
    participant_id = player["participantId"]
    player_team_id = player["teamId"]

    participants = {
        participant["participantId"]: participant
        for participant
        in match_data["info"]["participants"]
    }

    frames = timeline_data["info"]["frames"]

    events = sorted(
        (
            event
            for frame in frames
            for event in frame["events"]
        ),
        key=lambda event: event["timestamp"],
    )

    champion_kills = [
        event
        for event in events
        if event["type"] == "CHAMPION_KILL"
    ]

    player_events = []

    window_ms = window_seconds * 1000

    kill_number = 0
    death_number = 0
    assist_number = 0

    for event in champion_kills:
        relation = get_player_relation(
            event,
            participant_id,
        )

        if relation is None:
            continue

        if relation == "KILL":
            kill_number += 1
            relation_number = kill_number

        elif relation == "DEATH":
            death_number += 1
            relation_number = death_number

        else:
            assist_number += 1
            relation_number = assist_number

        timestamp = event["timestamp"]

        nearby_events = [
            compact_event(
                nearby_event,
                participants,
                player_team_id,
                timestamp,
            )
            for nearby_event in events
            if (
                nearby_event["type"]
                in EVENT_TYPES
                and timestamp - window_ms
                <= nearby_event["timestamp"]
                <= timestamp + window_ms
            )
        ]

        damage_received = event.get(
            "victimDamageReceived",
            [],
        )

        tower_damage = 0

        if relation == "DEATH":
            tower_damage = sum(
                damage.get(
                    "physicalDamage",
                    0,
                )
                + damage.get(
                    "magicDamage",
                    0,
                )
                + damage.get(
                    "trueDamage",
                    0,
                )
                for damage
                in damage_received
                if damage.get("type")
                == "TOWER"
            )

        player_events.append(
            {
                "relation": relation,
                "relation_number": (
                    relation_number
                ),
                "timestamp": timestamp,
                "position": (
                    event.get("position")
                ),
                "killer": participant_label(
                    participants,
                    event.get("killerId"),
                ),
                "victim": participant_label(
                    participants,
                    event.get("victimId"),
                ),
                "assists": [
                    participant_label(
                        participants,
                        assist_id,
                    )
                    for assist_id
                    in event.get(
                        "assistingParticipantIds",
                        [],
                    )
                ],
                "snapshot": nearest_frame(
                    frames,
                    participant_id,
                    timestamp,
                ),
                "tower_damage": (
                    tower_damage
                ),
                "damage_source_types": sorted(
                    {
                        damage.get("type")
                        for damage
                        in damage_received
                        if damage.get("type")
                    }
                ),
                "nearby_events": (
                    nearby_events
                ),
            }
        )

    fights = group_fights(
        champion_kills,
        participants,
        player,
    )

    my_fights = [
        fight
        for fight in fights
        if fight["player_involved"]
    ]

    attach_objectives_to_my_fights(
        events,
        my_fights,
        participants,
        player_team_id,
    )

    review_fights = build_review_context(
        my_fights
    )

    return {
        "player_events": player_events,
        "fights": fights,
        "my_fights": my_fights,
        "review_fights": review_fights,
    }


# ============================================================
# Objective labels
# ============================================================

def objective_label(objective):
    if objective["type"] == "ELITE_MONSTER_KILL":
        monster_type = objective.get(
            "monster_type"
        )

        monster_sub_type = objective.get(
            "monster_sub_type"
        )

        if monster_sub_type:
            return (
                f"{monster_type} "
                f"({monster_sub_type})"
            )

        return (
            monster_type
            or "ELITE_MONSTER"
        )

    if objective["type"] == "BUILDING_KILL":
        building = (
            objective.get(
                "building_type"
            )
            or "BUILDING"
        )

        lane = objective.get(
            "lane_type"
        )

        if lane:
            return (
                f"{building} "
                f"({lane})"
            )

        return building

    return objective["type"]


# ============================================================
# Fight Context TXT
# ============================================================

def export_fight_context(
    match_id,
    player,
    my_fights,
    raw_root=DEFAULT_RAW_ROOT,
):
    output_path = paths_for_match(match_id, raw_root).fight_context
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"Match ID: {match_id}",
        (
            f"Player: {player['championName']} "
            f"(participantId="
            f"{player['participantId']})"
        ),
        f"My Fights: {len(my_fights)}",
        "",
    ]

    for fight in my_fights:
        my_kda = fight["my_kda"]

        participant_names = [
            participant["champion"]
            for participant
            in fight["participants"]
            if participant
        ]

        lines.append(
            f"Fight #{fight['fight_id']}"
        )

        lines.append(
            "Time: "
            f"{format_timestamp(fight['start_timestamp'])}"
            " - "
            f"{format_timestamp(fight['end_timestamp'])}"
        )
        
        lines.append(
            "Duration: "
            f"{fight['duration_ms'] / 1000:.1f}s"
        )

        position = fight.get(
            "center_position"
        )

        if position:
            lines.append(
                "Position: "
                f"x={position['x']}, "
                f"y={position['y']}"
            )
        else:
            lines.append(
                "Position: unknown"
            )

        lines.append(
            "Participants: "
            + ", ".join(
                participant_names
            )
        )

        lines.append(
            "My KDA: "
            f"{my_kda['kills']}/"
            f"{my_kda['deaths']}/"
            f"{my_kda['assists']}"
        )

        lines.append(
            "Team Kills: "
            f"{fight['friendly_kills']}"
            "-"
            f"{fight['enemy_kills']}"
        )

        lines.append(
            f"Result: "
            f"{fight['result']}"
        )

        lines.append("Events:")

        for event in fight["events"]:
            if (
                event["type"]
                != "CHAMPION_KILL"
            ):
                continue

            killer = event.get("killer")
            victim = event.get("victim")
            assists = event.get(
                "assists",
                [],
            )

            killer_name = (
                killer["champion"]
                if killer
                else "Unknown"
            )

            victim_name = (
                victim["champion"]
                if victim
                else "Unknown"
            )

            assist_names = [
                assist["champion"]
                for assist in assists
                if assist
            ]

            event_text = (
                f"  "
                f"{format_timestamp(event['timestamp'])} "
                f"{killer_name}"
                " -> "
                f"{victim_name}"
            )

            if assist_names:
                event_text += (
                    " [Assist: "
                    + ", ".join(
                        assist_names
                    )
                    + "]"
                )

            lines.append(event_text)

        objectives = fight.get(
            "objective_events",
            [],
        )

        lines.append(
            "Objectives:"
        )

        if not objectives:
            lines.append(
                "  None"
            )

        else:
            for objective in objectives:
                relation = objective.get(
                    "relation",
                    "UNKNOWN",
                )

                label = objective_label(
                    objective
                )

                objective_text = (
                    f"  "
                    f"{format_timestamp(objective['timestamp'])} "
                    f"[{relation}] "
                    f"{label}"
                )

                if (
                    objective["type"]
                    == "BUILDING_KILL"
                ):
                    distance = objective.get(
                        "distance_from_fight"
                    )

                    if distance is not None:
                        objective_text += (
                            " "
                            f"[distance="
                            f"{distance:.0f}]"
                        )

                lines.append(
                    objective_text
                )

        lines.append("")

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            "\n".join(lines)
        )

    return output_path


# ============================================================
# Fight Review Context TXT
# ============================================================

def format_review_objective(
    objective,
    fight,
):
    timing = get_objective_timing(
        objective,
        fight,
    )

    relation = objective.get(
        "relation",
        "UNKNOWN",
    )

    label = objective_label(
        objective
    )

    timestamp = format_timestamp(
        objective["timestamp"]
    )

    return (
        f"{timing} "
        f"{timestamp} "
        f"[{relation}] "
        f"{label}"
    )


def export_fight_review_context(
    match_id,
    player,
    review_fights,
    raw_root=DEFAULT_RAW_ROOT,
):
    output_path = paths_for_match(match_id, raw_root).fight_review_context
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"Match ID: {match_id}",
        (
            f"Player: "
            f"{player['championName']} "
            f"(participantId="
            f"{player['participantId']})"
        ),
        (
            f"Review Fights: "
            f"{len(review_fights)}"
        ),
        "",
    ]

    for fight in review_fights:
        my_kda = fight["my_kda"]

        participant_names = [
            participant["champion"]
            for participant
            in fight["participants"]
            if participant
        ]

        objective_context = fight[
            "objective_context"
        ]

        lines.append(
            (
                f"Fight #{fight['fight_id']} "
                f"| {fight['phase']} "
                f"| {fight['scale']} "
                f"| {fight['survival']} "
                f"| {fight['result']}"
            )
        )

        lines.append(
            (
                "Time: "
                f"{format_timestamp(fight['start_timestamp'])}"
                "-"
                f"{format_timestamp(fight['end_timestamp'])} "
                "| Duration "
                f"{fight['duration_ms'] / 1000:.1f}s"
            )
        )

        lines.append(
            (
                "My KDA: "
                f"{my_kda['kills']}/"
                f"{my_kda['deaths']}/"
                f"{my_kda['assists']} "
                "| Team Kills "
                f"{fight['friendly_kills']}"
                "-"
                f"{fight['enemy_kills']}"
            )
        )

        lines.append(
            (
                "Scale: "
                f"{fight['participant_count']} players "
                "| Participants: "
                + ", ".join(
                    participant_names
                )
            )
        )

        lines.append(
            (
                "Objective Context: "
                f"BEFORE="
                f"{objective_context['before']} "
                "| DURING="
                f"{objective_context['during']} "
                "| AFTER="
                f"{objective_context['after']}"
            )
        )

        all_objectives = (
            fight["objectives_before"]
            + fight["objectives_during"]
            + fight["objectives_after"]
        )

        lines.append(
            "Objectives:"
        )

        if not all_objectives:
            lines.append(
                "  None"
            )

        else:
            for objective in all_objectives:
                lines.append(
                    "  "
                    + format_review_objective(
                        objective,
                        fight,
                    )
                )

        lines.append(
            "Sequence:"
        )

        for event in fight["events"]:
            if (
                event["type"]
                != "CHAMPION_KILL"
            ):
                continue

            killer = event.get("killer")
            victim = event.get("victim")
            assists = event.get(
                "assists",
                [],
            )

            killer_name = (
                killer["champion"]
                if killer
                else "Unknown"
            )

            victim_name = (
                victim["champion"]
                if victim
                else "Unknown"
            )

            assist_names = [
                assist["champion"]
                for assist in assists
                if assist
            ]

            sequence_text = (
                f"  "
                f"{format_timestamp(event['timestamp'])} "
                f"{killer_name}"
                " -> "
                f"{victim_name}"
            )

            if assist_names:
                sequence_text += (
                    " [Assist: "
                    + ", ".join(
                        assist_names
                    )
                    + "]"
                )

            lines.append(
                sequence_text
            )

        lines.append("")

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            "\n".join(lines)
        )

    return output_path


# ============================================================
# 外部呼び出し用
# ============================================================

def analyze_match_timeline(
    match_id,
    puuid=None,
    participant_id=None,
    champion=None,
    window_seconds=60,
    raw_root=DEFAULT_RAW_ROOT,
):
    """
    1試合分の保存済みMatch JSON / Timeline JSONを読み込み、
    以下を生成する。

    ・combat_timeline.json
    ・fight_context.txt
    ・fight_review_context.txt

    main.pyからは基本的に
    analyze_match_timeline(match_id, puuid)
    で呼ぶ。
    """

    paths = paths_for_match(match_id, raw_root)
    match_path = paths.detail
    timeline_path = paths.timeline

    if not os.path.exists(match_path):
        raise FileNotFoundError(
            f"Match JSONがありません: {match_path}"
        )

    if not os.path.exists(timeline_path):
        raise FileNotFoundError(
            f"Timeline JSONがありません: "
            f"{timeline_path}"
        )

    match_data = load_json(
        match_path
    )

    timeline_data = load_json(
        timeline_path
    )

    player = find_player(
        match_data,
        puuid=puuid,
        participant_id=participant_id,
        champion=champion,
    )

    analysis = analyze_combat(
        match_data,
        timeline_data,
        player,
        window_seconds,
    )

    combat_events = analysis[
        "player_events"
    ]

    fights = analysis[
        "fights"
    ]

    my_fights = analysis[
        "my_fights"
    ]

    review_fights = analysis[
        "review_fights"
    ]

    kill_count = sum(
        1
        for event in combat_events
        if event["relation"] == "KILL"
    )

    death_count = sum(
        1
        for event in combat_events
        if event["relation"] == "DEATH"
    )

    assist_count = sum(
        1
        for event in combat_events
        if event["relation"] == "ASSIST"
    )

    output = {
        "match_id": match_id,
        "participant": {
            "participant_id": (
                player["participantId"]
            ),
            "puuid": (
                player.get("puuid")
            ),
            "champion": (
                player["championName"]
            ),
            "team_id": (
                player["teamId"]
            ),
        },
        "window_seconds": (
            window_seconds
        ),
        "fight_settings": {
            "normal_time_gap_seconds": (
                FIGHT_TIME_GAP_MS
                // 1000
            ),
            "extended_time_gap_seconds": (
                FIGHT_EXTENDED_TIME_GAP_MS
                // 1000
            ),
            "distance": (
                FIGHT_DISTANCE
            ),
            "objective_context_window_seconds": (
                OBJECTIVE_CONTEXT_WINDOW_MS
                // 1000
            ),
            "building_objective_distance": (
                BUILDING_OBJECTIVE_DISTANCE
            ),
            "early_end_minute": (
                EARLY_END_MS
                // 60000
            ),
            "mid_end_minute": (
                MID_END_MS
                // 60000
            ),
        },
        "summary": {
            "kills": kill_count,
            "deaths": death_count,
            "assists": assist_count,
            "combat_events": (
                len(combat_events)
            ),
            "all_fights": (
                len(fights)
            ),
            "my_fights": (
                len(my_fights)
            ),
            "review_fights": (
                len(review_fights)
            ),
        },
        "combat_events": (
            combat_events
        ),
        "fights": fights,
        "my_fights": (
            my_fights
        ),
        "review_fights": (
            review_fights
        ),
    }

    output_path = paths_for_match(match_id, raw_root).combat
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    fight_context_path = export_fight_context(
        match_id,
        player,
        my_fights,
        raw_root=raw_root,
    )

    review_context_path = (
        export_fight_review_context(
            match_id,
            player,
            review_fights,
            raw_root=raw_root,
        )
    )

    result = {
        "match_id": match_id,
        "champion": (
            player["championName"]
        ),
        "participant_id": (
            player["participantId"]
        ),
        "kills": kill_count,
        "deaths": death_count,
        "assists": assist_count,
        "combat_events": (
            len(combat_events)
        ),
        "all_fights": (
            len(fights)
        ),
        "my_fights": (
            len(my_fights)
        ),
        "review_fights": (
            len(review_fights)
        ),
        "combat_timeline_path": (
            output_path
        ),
        "fight_context_path": (
            fight_context_path
        ),
        "fight_review_context_path": (
            review_context_path
        ),
    }

    return result


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Match Timelineから"
            "K/D/A・Fight・Objective・"
            "Review Contextを解析します"
        )
    )

    parser.add_argument(
        "match_id"
    )

    parser.add_argument(
        "--puuid"
    )

    parser.add_argument(
        "--participant-id",
        type=int,
    )

    parser.add_argument(
        "--champion"
    )

    parser.add_argument(
        "--window",
        type=int,
        default=60,
        help=(
            "K/D/A前後の"
            "イベント抽出秒数"
        ),
    )

    args = (
        parser.parse_args()
    )

    result = analyze_match_timeline(
        match_id=args.match_id,
        puuid=args.puuid,
        participant_id=(
            args.participant_id
        ),
        champion=args.champion,
        window_seconds=args.window,
    )

    print(
        "participantId: "
        f"{result['participant_id']} "
        f"({result['champion']})"
    )

    print(
        "K/D/A: "
        f"{result['kills']}/"
        f"{result['deaths']}/"
        f"{result['assists']}"
    )

    print(
        "combat events: "
        f"{result['combat_events']}"
    )

    print(
        "all fights: "
        f"{result['all_fights']}"
    )

    print(
        "my fights: "
        f"{result['my_fights']}"
    )

    print(
        "review fights: "
        f"{result['review_fights']}"
    )

    print(
        f"{result['combat_timeline_path']} "
        "を保存しました"
    )

    print(
        f"{result['fight_context_path']} "
        "を保存しました"
    )

    print(
        f"{result['fight_review_context_path']} "
        "を保存しました"
    )


if __name__ == "__main__":
    main()
