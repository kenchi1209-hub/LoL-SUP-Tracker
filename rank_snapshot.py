"""Optional, per-match League-V4 rank snapshots for newly fetched matches."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from raw_paths import paths_for_match


SOLO_QUEUE = "RANKED_SOLO_5x5"
FLEX_QUEUE = "RANKED_FLEX_SR"
RANK_PREFIXES = {
    "IRON": "I",
    "BRONZE": "B",
    "SILVER": "S",
    "GOLD": "G",
    "PLATINUM": "P",
    "EMERALD": "E",
    "DIAMOND": "D",
}
APEX_RANKS = {"MASTER": "M", "GRANDMASTER": "GM", "CHALLENGER": "C"}


def captured_at_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_entry(entry):
    if not isinstance(entry, dict):
        return None
    tier = entry.get("tier")
    rank = entry.get("rank")
    if not isinstance(tier, str) or not tier:
        return None
    compact = {"tier": tier}
    if isinstance(rank, str) and rank:
        compact["rank"] = rank
    return compact


def entries_by_queue(entries):
    result = {"solo": None, "flex": None}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        queue_type = entry.get("queueType")
        if queue_type == SOLO_QUEUE:
            result["solo"] = compact_entry(entry)
        elif queue_type == FLEX_QUEUE:
            result["flex"] = compact_entry(entry)
    return result


def failure_entry(participant_id):
    return {
        "participantId": participant_id,
        "fetch_status": "error",
        "solo": None,
        "flex": None,
    }


def success_entry(participant_id, entries):
    queues = entries_by_queue(entries)
    return {
        "participantId": participant_id,
        "fetch_status": "success",
        "solo": queues["solo"],
        "flex": queues["flex"],
    }


def build_snapshot(match_id, match_data, fetch_entries, cache, captured_at=None):
    """Build one snapshot without retaining participant identity values on disk."""
    participants = (match_data.get("info") or {}).get("participants") or []
    snapshot_participants = []
    for participant in participants:
        participant_id = participant.get("participantId") if isinstance(participant, dict) else None
        puuid = participant.get("puuid") if isinstance(participant, dict) else None
        if not isinstance(participant_id, int) or not puuid:
            snapshot_participants.append(failure_entry(participant_id))
            continue
        if puuid not in cache:
            try:
                cache[puuid] = ("success", fetch_entries(puuid))
            except (requests.RequestException, ValueError, TypeError):
                cache[puuid] = ("error", None)
        status, entries = cache[puuid]
        snapshot_participants.append(
            success_entry(participant_id, entries) if status == "success" else failure_entry(participant_id)
        )
    return {
        "match_id": match_id,
        "captured_at": captured_at or captured_at_now(),
        "participants": snapshot_participants,
    }


def write_snapshot_atomic(snapshot, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(snapshot, file, ensure_ascii=True, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def capture_rank_snapshots(match_ids, raw_root, fetch_entries, captured_at=None):
    """Persist snapshots only for the supplied new match IDs; no backfill scan."""
    cache = {}
    paths = []
    for match_id in match_ids:
        raw_paths = paths_for_match(match_id, raw_root)
        if raw_paths.rank_snapshot.is_file():
            print(f"既存Rank snapshotスキップ: {raw_paths.rank_snapshot}")
            continue
        with raw_paths.detail.open("r", encoding="utf-8") as file:
            match_data = json.load(file)
        snapshot = build_snapshot(match_id, match_data, fetch_entries, cache, captured_at)
        write_snapshot_atomic(snapshot, raw_paths.rank_snapshot)
        paths.append(raw_paths.rank_snapshot)
    return paths


def rank_short(snapshot, participant_id):
    """Return a public Solo/Duo-only value: rank, UR, or - for unavailable data."""
    if not isinstance(snapshot, dict):
        return "-"
    for entry in snapshot.get("participants", []):
        if not isinstance(entry, dict) or entry.get("participantId") != participant_id:
            continue
        if entry.get("fetch_status") != "success":
            return "-"
        solo = entry.get("solo")
        if solo is None:
            return "UR"
        if not isinstance(solo, dict):
            return "-"
        tier = solo.get("tier")
        division = solo.get("rank")
        if tier in APEX_RANKS:
            return APEX_RANKS[tier]
        prefix = RANK_PREFIXES.get(tier)
        if prefix and isinstance(division, str) and division in {"I", "II", "III", "IV"}:
            return f"{prefix}{ {'I': 1, 'II': 2, 'III': 3, 'IV': 4}[division] }"
        return "-"
    return "-"
