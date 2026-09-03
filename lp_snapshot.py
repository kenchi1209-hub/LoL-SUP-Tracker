"""Capture exact, per-match Solo/Duo LP history after a ranked match.

This command is intentionally separate from the daily batch update.  It writes a
match snapshot only when exactly one previously uncaptured Solo/Duo match exists
and League-V4 confirms the expected W/L counter transition.
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

from data_paths import get_data_paths
from raw_paths import paths_for_match
from timezone_utils import JST, now_jst


SCHEMA_VERSION = 1
SOLO_QUEUE_TYPE = "RANKED_SOLO_5x5"
SOLO_QUEUE_ID = 420
BASELINE_RELATIVE_PATH = Path("lp_progress") / "baseline.json"
CHECKPOINTS_RELATIVE_PATH = Path("lp_progress") / "checkpoints"
HISTORY_FILENAME = "lp_history.json"
TIER_INDEX = {
    "IRON": 0,
    "BRONZE": 1,
    "SILVER": 2,
    "GOLD": 3,
    "PLATINUM": 4,
    "EMERALD": 5,
    "DIAMOND": 6,
}
DIVISION_OFFSET = {"IV": 0, "III": 100, "II": 200, "I": 300}
APEX_TIERS = {"MASTER", "GRANDMASTER", "CHALLENGER"}


class LPSnapshotError(RuntimeError):
    """Base error for an operation that must not produce a confirmed snapshot."""


class AmbiguousHistoryError(LPSnapshotError):
    """Raised when one current League state cannot be assigned to one match."""


class LeagueUpdateTimeout(LPSnapshotError):
    """Raised when League-V4 does not reflect the match before the deadline."""


class CheckpointNotRequiredError(LPSnapshotError):
    """Raised when a checkpoint would hide an exact-capture opportunity."""


def iso_jst(value=None):
    current = value or now_jst()
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    return current.astimezone(JST).replace(microsecond=0).isoformat()


def parse_timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def rank_value(rank):
    """Convert a rank object to the continuous graph score."""
    tier = str(rank.get("tier", "")).upper()
    lp = int(rank.get("lp", rank.get("leaguePoints", 0)))
    if tier in TIER_INDEX:
        division = str(rank.get("division", rank.get("rank", ""))).upper()
        if division not in DIVISION_OFFSET:
            raise ValueError(f"Invalid division for {tier}: {division}")
        return TIER_INDEX[tier] * 400 + DIVISION_OFFSET[division] + lp
    if tier in APEX_TIERS:
        return 2800 + lp
    raise ValueError(f"Unsupported tier: {tier}")


def compact_rank(entry):
    if not isinstance(entry, dict) or entry.get("queueType") != SOLO_QUEUE_TYPE:
        raise LPSnapshotError("Solo/Duo rank entry is unavailable")
    tier = str(entry.get("tier", "")).upper()
    result = {
        "tier": tier,
        "division": None if tier in APEX_TIERS else str(entry.get("rank", "")).upper(),
        "lp": int(entry.get("leaguePoints", 0)),
        "wins": int(entry.get("wins", 0)),
        "losses": int(entry.get("losses", 0)),
    }
    rank_value(result)
    return result


def compact_rank_before(entry):
    """Normalize a non-identifying Queue 420 rank captured before a match.

    The LCU uses ``division`` / ``leaguePoints`` while the persisted LP schema
    uses ``division`` / ``lp``.  Keep the conversion here so a pre-match
    observation can be compared to the previous exact snapshot without ever
    using the match result to infer an LP value.
    """
    if not isinstance(entry, dict):
        raise LPSnapshotError("Pre-match rank snapshot is unavailable")
    normalized = {
        "queueType": entry.get("queueType", SOLO_QUEUE_TYPE),
        "tier": entry.get("tier"),
        "rank": entry.get("rank", entry.get("division")),
        "leaguePoints": entry.get("leaguePoints", entry.get("lp")),
        "wins": entry.get("wins"),
        "losses": entry.get("losses"),
    }
    if normalized["queueType"] != SOLO_QUEUE_TYPE:
        raise LPSnapshotError("Pre-match rank snapshot is not Solo/Duo")
    return compact_rank(normalized)


def atomic_json_dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def baseline_path(raw_root):
    return Path(raw_root) / BASELINE_RELATIVE_PATH


def checkpoints_dir(raw_root):
    return Path(raw_root) / CHECKPOINTS_RELATIVE_PATH


def checkpoint_id(captured_at):
    return f"checkpoint-{parse_timestamp(captured_at).astimezone(JST).strftime('%Y%m%dT%H%M%S%z')}"


def checkpoint_path(raw_root, snapshot_id):
    return checkpoints_dir(raw_root) / f"{snapshot_id}.json"


def history_path(csv_root):
    return Path(csv_root) / HISTORY_FILENAME


def create_baseline(current_rank_path, raw_root, csv_root, captured_at=None):
    """Create the immutable starting point without calling Riot APIs."""
    output = baseline_path(raw_root)
    if output.exists():
        raise LPSnapshotError(f"Baseline already exists: {output}")
    rank = compact_rank(load_json(current_rank_path))
    baseline = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_type": "baseline",
        "queue_type": SOLO_QUEUE_TYPE,
        "queue_id": SOLO_QUEUE_ID,
        "captured_at_jst": iso_jst(captured_at),
        **rank,
        "confidence": "baseline",
    }
    atomic_json_dump(output, baseline)
    rebuild_lp_history(raw_root, csv_root)
    return output


def iter_rank_after_paths(raw_root):
    yield from sorted(Path(raw_root).glob("*/rank_after.json"))


def iter_checkpoint_paths(raw_root):
    yield from sorted(checkpoints_dir(raw_root).glob("*.json"))


def load_confirmed_snapshots(raw_root):
    snapshots = []
    for path in iter_rank_after_paths(raw_root):
        try:
            snapshot = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if (
            snapshot.get("schema_version") == SCHEMA_VERSION
            and snapshot.get("snapshot_type") == "rank_after"
            and snapshot.get("confidence") == "exact"
            and snapshot.get("queue_id") == SOLO_QUEUE_ID
        ):
            snapshots.append(snapshot)
    return snapshots


def load_checkpoints(raw_root):
    checkpoints = []
    for path in iter_checkpoint_paths(raw_root):
        try:
            checkpoint = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if (
            checkpoint.get("schema_version") == SCHEMA_VERSION
            and checkpoint.get("snapshot_type") == "checkpoint"
            and checkpoint.get("confidence") == "checkpoint"
            and checkpoint.get("queue_id") == SOLO_QUEUE_ID
        ):
            checkpoints.append(checkpoint)
    return checkpoints


def rank_state(rank):
    return {
        key: rank.get(key)
        for key in ("tier", "division", "lp", "wins", "losses")
    }


def event_timestamp(event):
    return parse_timestamp(event["captured_at_jst"])


def validated_events(raw_root, baseline):
    """Validate the exact/checkpoint chain and return events with segment IDs."""
    current = rank_state(baseline)
    previous_type = "baseline"
    previous_id = "baseline"
    segment_index = 0
    validated = []
    events = load_confirmed_snapshots(raw_root) + load_checkpoints(raw_root)
    for snapshot in sorted(events, key=lambda item: (event_timestamp(item), item.get("snapshot_id", item.get("match_id", "")))):
        kind = snapshot.get("snapshot_type")
        if kind == "checkpoint":
            gap = snapshot.get("gap")
            if not isinstance(gap, dict):
                raise LPSnapshotError("Checkpoint gap is missing")
            match_ids = gap.get("match_ids")
            games = gap.get("games")
            wins = gap.get("wins")
            losses = gap.get("losses")
            if (
                not isinstance(match_ids, list)
                or not all(isinstance(match_id, str) and match_id for match_id in match_ids)
                or games != len(match_ids)
                or not isinstance(wins, int)
                or not isinstance(losses, int)
                or wins + losses != games
                or games < 2
            ):
                raise LPSnapshotError("Invalid checkpoint gap")
            if snapshot.get("games_since_previous_snapshot") != games:
                raise LPSnapshotError("Invalid checkpoint game count")
            if snapshot.get("previous_snapshot_type") != previous_type or snapshot.get("previous_snapshot_id") != previous_id:
                raise LPSnapshotError("Discontinuous checkpoint")
            after = rank_state(snapshot)
            expected = (int(current["wins"]) + wins, int(current["losses"]) + losses)
            if (after.get("wins"), after.get("losses")) != expected:
                raise LPSnapshotError("Invalid checkpoint W/L")
            if "match_id" in snapshot or "lp_delta" in snapshot:
                raise LPSnapshotError("Checkpoint must not contain match LP fields")
            segment_index += 1
            validated.append({"event": snapshot, "segment_id": f"segment-{segment_index}"})
            current = after
            previous_type = "checkpoint"
            previous_id = snapshot.get("snapshot_id")
            continue
        if kind != "rank_after":
            raise LPSnapshotError("Unknown LP history event")
        if snapshot.get("games_since_previous_snapshot") != 1:
            raise LPSnapshotError(
                f"Invalid game count in LP snapshot: {snapshot.get('match_id')}"
            )
        before = rank_state(snapshot.get("before") or {})
        after = rank_state(snapshot.get("after") or {})
        if before != current:
            raise LPSnapshotError(
                f"Discontinuous LP snapshot: {snapshot.get('match_id')}"
            )
        expected_wins, expected_losses = expected_record(before, snapshot.get("win") is True)
        if (after.get("wins"), after.get("losses")) != (expected_wins, expected_losses):
            raise LPSnapshotError(
                f"Invalid W/L in LP snapshot: {snapshot.get('match_id')}"
            )
        expected_delta = rank_value(after) - rank_value(before)
        if snapshot.get("lp_delta") != expected_delta:
            raise LPSnapshotError(
                f"Invalid LP delta in snapshot: {snapshot.get('match_id')}"
            )
        validated.append({"event": snapshot, "segment_id": f"segment-{segment_index}"})
        current = after
        previous_type = "rank_after"
        previous_id = snapshot.get("match_id")
    return validated


def validated_snapshots(raw_root, baseline):
    """Backward-compatible exact snapshot view used by existing callers/tests."""
    return [item["event"] for item in validated_events(raw_root, baseline) if item["event"].get("snapshot_type") == "rank_after"]


def previous_state(raw_root):
    baseline = load_json(baseline_path(raw_root))
    if baseline.get("snapshot_type") != "baseline":
        raise LPSnapshotError("Invalid LP baseline")
    events = validated_events(raw_root, baseline)
    if events:
        latest = events[-1]["event"]
        state = latest["after"] if latest["snapshot_type"] == "rank_after" else latest
        return rank_state(state), latest["captured_at_jst"], events
    rank = {key: baseline.get(key) for key in ("tier", "division", "lp", "wins", "losses")}
    return rank, baseline["captured_at_jst"], events


def reconcile_previous_rank_after(raw_root, csv_root, next_before, next_game_datetime_jst, captured_at=None):
    """Confirm or correct only the immediately preceding exact LP snapshot.

    ``next_before`` is an LCU rank observation from the start of the next
    Queue 420 game.  A correction is safe only when its W/L counters are
    unchanged from the preceding match's observed after state and the next
    match is chronologically later.  Any other mismatch remains untouched and
    is returned as ``needs_review``.
    """
    baseline = load_json(baseline_path(raw_root))
    events = validated_events(raw_root, baseline)
    if not events or events[-1]["event"].get("snapshot_type") != "rank_after":
        return {"status": "not_applicable", "changed": False}

    previous = events[-1]["event"]
    observed_after = rank_state(previous.get("after") or {})
    next_before = compact_rank_before(next_before)
    try:
        next_game_time = parse_timestamp(next_game_datetime_jst)
        previous_game_time = parse_timestamp(previous["game_datetime_jst"])
    except (KeyError, TypeError, ValueError):
        return {"status": "needs_review", "changed": False}
    if next_game_time <= previous_game_time:
        return {"status": "needs_review", "changed": False}

    observed_record = (observed_after.get("wins"), observed_after.get("losses"))
    next_record = (next_before.get("wins"), next_before.get("losses"))
    if observed_record != next_record:
        return {"status": "needs_review", "changed": False}

    snapshot_path = paths_for_match(previous["match_id"], raw_root).rank_after
    if observed_after == next_before:
        if previous.get("lp_status") == "confirmed":
            return {"status": "confirmed", "changed": False, "match_id": previous["match_id"]}
        previous["lp_status"] = "confirmed"
        previous.setdefault("lp_delta_source", "post_match_snapshot")
        atomic_json_dump(snapshot_path, previous)
        rebuild_lp_history(raw_root, csv_root)
        return {"status": "confirmed", "changed": True, "match_id": previous["match_id"]}

    observed_delta = previous.get("observed_lp_delta", previous.get("lp_delta"))
    if not isinstance(observed_delta, (int, float)):
        return {"status": "needs_review", "changed": False}
    final_delta = rank_value(next_before) - rank_value(rank_state(previous.get("before") or {}))
    previous["after_observed"] = observed_after
    previous["observed_lp_delta"] = observed_delta
    previous["after"] = next_before
    previous["lp_delta"] = final_delta
    previous["lp_delta_final"] = final_delta
    previous["lp_correction"] = final_delta - observed_delta
    previous["lp_delta_source"] = "next_rank_before"
    previous["lp_adjustment_type"] = "unknown_adjustment"
    previous["lp_status"] = "corrected"
    previous["corrected_at_jst"] = iso_jst(captured_at)
    atomic_json_dump(snapshot_path, previous)
    rebuild_lp_history(raw_root, csv_root)
    return {"status": "corrected", "changed": True, "match_id": previous["match_id"]}


def match_end_jst(detail):
    info = detail.get("info") or {}
    timestamp = info.get("gameEndTimestamp")
    if timestamp is None:
        timestamp = int(info.get("gameCreation", 0)) + int(info.get("gameDuration", 0)) * 1000
    return datetime.fromtimestamp(int(timestamp) / 1000, tz=JST)


def match_metadata(detail, puuid):
    info = detail.get("info") or {}
    if int(info.get("queueId", 0)) != SOLO_QUEUE_ID:
        return None
    me = next(
        (item for item in info.get("participants", []) if item.get("puuid") == puuid),
        None,
    )
    if me is None:
        raise LPSnapshotError("Player was not found in Match Detail")
    game_creation = datetime.fromtimestamp(int(info["gameCreation"]) / 1000, tz=JST)
    version = str(info.get("gameVersion", ""))
    patch = ".".join(version.split(".")[:2])
    return {
        "match_id": (detail.get("metadata") or {}).get("matchId", ""),
        "game_datetime_jst": iso_jst(game_creation),
        "game_end_jst": match_end_jst(detail),
        "patch": patch,
        "champion": me.get("championName", ""),
        "win": bool(me.get("win")),
    }


def discover_uncaptured_solo_matches(
    puuid, raw_root, cutoff_jst, fetch_match_ids, fetch_match_detail, count=100
):
    captured_ids = {item["match_id"] for item in load_confirmed_snapshots(raw_root)}
    cutoff = parse_timestamp(cutoff_jst)
    found = []
    for match_id in dict.fromkeys(fetch_match_ids(puuid, count=count)):
        if match_id in captured_ids:
            continue
        local_path = paths_for_match(match_id, raw_root).detail
        detail = load_json(local_path) if local_path.is_file() else fetch_match_detail(match_id)
        metadata = match_metadata(detail, puuid)
        if metadata and metadata["game_end_jst"] > cutoff:
            metadata["match_id"] = match_id
            found.append(metadata)
    return sorted(found, key=lambda item: (item["game_datetime_jst"], item["match_id"]))


def parse_match_date(value):
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)


def discover_local_uncaptured_solo_matches(raw_root, csv_root, cutoff_jst, puuid=None):
    """Find checkpoint gaps from existing PrivateData without Match-V5 calls."""
    captured_ids = {item["match_id"] for item in load_confirmed_snapshots(raw_root)}
    cutoff = parse_timestamp(cutoff_jst)
    found = []
    if puuid:
        for detail_path in sorted(Path(raw_root).glob("*/match.json")):
            detail = load_json(detail_path)
            metadata = match_metadata(detail, puuid)
            if (
                metadata
                and metadata["match_id"] not in captured_ids
                and metadata["game_end_jst"] > cutoff
            ):
                found.append({key: metadata[key] for key in ("match_id", "game_datetime_jst", "patch", "champion", "win")})
        return sorted(found, key=lambda item: (item["game_datetime_jst"], item["match_id"]))

    csv_path = Path(csv_root) / "my_matches.csv"
    if not csv_path.is_file():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            match_id = row.get("match_id", "")
            if not match_id or match_id in captured_ids or str(row.get("queue_id", "")) != str(SOLO_QUEUE_ID):
                continue
            game_datetime = parse_match_date(row.get("date", ""))
            if game_datetime <= cutoff:
                continue
            win_value = str(row.get("win", row.get("result", ""))).strip().lower()
            if win_value in {"true", "1", "win", "w"}:
                won = True
            elif win_value in {"false", "0", "loss", "l"}:
                won = False
            else:
                raise LPSnapshotError(f"Invalid win value for checkpoint gap: {match_id}")
            found.append({
                "match_id": match_id,
                "game_datetime_jst": iso_jst(game_datetime),
                "patch": row.get("patch", ""),
                "champion": row.get("champion", ""),
                "win": won,
            })
    return sorted(found, key=lambda item: (item["game_datetime_jst"], item["match_id"]))


def expected_record(before, won):
    return (
        int(before["wins"]) + (1 if won else 0),
        int(before["losses"]) + (0 if won else 1),
    )


def wait_for_league_update(
    before, won, fetch_current_rank, timeout_seconds=120, poll_interval_seconds=5,
    monotonic=time.monotonic, sleep=time.sleep,
):
    expected_wins, expected_losses = expected_record(before, won)
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            entry = fetch_current_rank()
            after = compact_rank(entry)
        except (requests.RequestException, ValueError, TypeError, LPSnapshotError) as error:
            if monotonic() >= deadline:
                raise LeagueUpdateTimeout("League-V4 update timed out") from error
        else:
            current = (after["wins"], after["losses"])
            previous = (int(before["wins"]), int(before["losses"]))
            expected = (expected_wins, expected_losses)
            if current == expected:
                return after
            if current != previous:
                raise AmbiguousHistoryError(
                    f"Unexpected W/L transition: {previous} -> {current}; expected {expected}"
                )
            if monotonic() >= deadline:
                raise LeagueUpdateTimeout("League-V4 did not reflect the match before timeout")
        sleep(poll_interval_seconds)


def build_rank_after(match, before, after, captured_at=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_type": "rank_after",
        "match_id": match["match_id"],
        "queue_type": SOLO_QUEUE_TYPE,
        "queue_id": SOLO_QUEUE_ID,
        "game_datetime_jst": match["game_datetime_jst"],
        "patch": match["patch"],
        "champion": match["champion"],
        "win": match["win"],
        "captured_at_jst": iso_jst(captured_at),
        "capture_mode": "manual_post_match",
        "confidence": "exact",
        "before": dict(before),
        "after": dict(after),
        "lp_delta": rank_value(after) - rank_value(before),
        "lp_delta_source": "post_match_snapshot",
        "lp_status": "provisional",
        "games_since_previous_snapshot": 1,
    }


def history_record(snapshot):
    before = snapshot["before"]
    after = snapshot["after"]
    return {
        "match_id": snapshot["match_id"],
        "game_datetime_jst": snapshot["game_datetime_jst"],
        "patch": snapshot["patch"],
        "champion": snapshot["champion"],
        "win": snapshot["win"],
        "queue": snapshot["queue_type"],
        "tier_before": before["tier"],
        "division_before": before.get("division"),
        "lp_before": before["lp"],
        "tier_after": after["tier"],
        "division_after": after.get("division"),
        "lp_after": after["lp"],
        "lp_delta": snapshot["lp_delta"],
        "observed_lp_delta": snapshot.get("observed_lp_delta"),
        "lp_correction": snapshot.get("lp_correction"),
        "lp_delta_source": snapshot.get("lp_delta_source", "post_match_snapshot"),
        "lp_status": snapshot.get("lp_status", "confirmed"),
        "lp_adjustment_type": snapshot.get("lp_adjustment_type"),
        "confidence": snapshot["confidence"],
    }


def checkpoint_record(snapshot, segment_id):
    return {
        key: snapshot.get(key)
        for key in (
            "snapshot_id", "captured_at_jst", "tier", "division", "lp", "wins", "losses",
            "confidence", "reason", "games_since_previous_snapshot",
            "previous_snapshot_type", "previous_snapshot_id", "gap",
        )
    } | {"segment_id": segment_id, "gap_before": True}


def rebuild_lp_history(raw_root, csv_root):
    baseline = load_json(baseline_path(raw_root))
    public_baseline = {
        key: baseline.get(key)
        for key in (
            "captured_at_jst", "tier", "division", "lp", "wins", "losses", "confidence"
        )
    }
    events = validated_events(raw_root, baseline)
    history = {
        "schema_version": SCHEMA_VERSION,
        "queue_type": SOLO_QUEUE_TYPE,
        "queue_id": SOLO_QUEUE_ID,
        "baseline": public_baseline | {"segment_id": "segment-0"},
        "checkpoints": [
            checkpoint_record(item["event"], item["segment_id"])
            for item in events if item["event"].get("snapshot_type") == "checkpoint"
        ],
        "matches": [
            history_record(item["event"]) | {"segment_id": item["segment_id"]}
            for item in events if item["event"].get("snapshot_type") == "rank_after"
        ],
    }
    atomic_json_dump(history_path(csv_root), history)
    return history


def capture_one(
    puuid, raw_root, csv_root, fetch_match_ids, fetch_match_detail,
    fetch_current_rank, timeout_seconds=120, poll_interval_seconds=5,
    captured_at=None, monotonic=time.monotonic, sleep=time.sleep,
    next_rank_before=None,
):
    before, cutoff_jst, _snapshots = previous_state(raw_root)
    candidates = discover_uncaptured_solo_matches(
        puuid, raw_root, cutoff_jst, fetch_match_ids, fetch_match_detail
    )
    if not candidates:
        print("[INFO] No new Solo/Duo Ranked match; nothing to update.")
        return None
    if len(candidates) != 1:
        raise AmbiguousHistoryError(
            f"{len(candidates)} uncaptured Solo/Duo matches found; no LP was assigned"
        )
    match = candidates[0]
    reconciliation = None
    if next_rank_before is not None:
        reconciliation = reconcile_previous_rank_after(
            raw_root,
            csv_root,
            next_rank_before,
            match["game_datetime_jst"],
            captured_at=captured_at,
        )
        if reconciliation["status"] == "needs_review":
            raise AmbiguousHistoryError(
                "Previous LP snapshot differs from next pre-match rank; manual review required"
            )
        if reconciliation["status"] == "corrected":
            before, cutoff_jst, _snapshots = previous_state(raw_root)
    after = wait_for_league_update(
        before, match["win"], fetch_current_rank, timeout_seconds,
        poll_interval_seconds, monotonic, sleep,
    )
    snapshot = build_rank_after(match, before, after, captured_at)
    if reconciliation and reconciliation["status"] == "corrected":
        snapshot["reconciled_previous_match_id"] = reconciliation["match_id"]
    output = paths_for_match(match["match_id"], raw_root).rank_after
    if output.exists():
        raise LPSnapshotError(f"rank_after already exists: {output}")
    atomic_json_dump(output, snapshot)
    rebuild_lp_history(raw_root, csv_root)
    return output


def build_checkpoint(before, previous_events, candidates, after, captured_at=None):
    captured_at_jst = iso_jst(captured_at)
    snapshot_id = checkpoint_id(captured_at_jst)
    previous_type = "baseline"
    previous_id = "baseline"
    if previous_events:
        previous = previous_events[-1]["event"]
        previous_type = previous["snapshot_type"]
        previous_id = previous.get("snapshot_id", previous.get("match_id"))
    wins = sum(1 for candidate in candidates if candidate["win"])
    losses = len(candidates) - wins
    expected = (int(before["wins"]) + wins, int(before["losses"]) + losses)
    if (after["wins"], after["losses"]) != expected:
        raise AmbiguousHistoryError(
            f"Checkpoint W/L mismatch: expected {expected}, got {(after['wins'], after['losses'])}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_type": "checkpoint",
        "snapshot_id": snapshot_id,
        "captured_at_jst": captured_at_jst,
        "queue_type": SOLO_QUEUE_TYPE,
        "queue_id": SOLO_QUEUE_ID,
        **rank_state(after),
        "confidence": "checkpoint",
        "reason": "multiple_uncaptured_ranked_matches",
        "games_since_previous_snapshot": len(candidates),
        "previous_snapshot_type": previous_type,
        "previous_snapshot_id": previous_id,
        "gap": {
            "reason": "multiple_uncaptured_ranked_matches",
            "match_ids": [candidate["match_id"] for candidate in candidates],
            "games": len(candidates),
            "wins": wins,
            "losses": losses,
        },
    }


def create_checkpoint(raw_root, csv_root, fetch_current_rank, captured_at=None, puuid=None):
    before, cutoff_jst, events = previous_state(raw_root)
    candidates = discover_local_uncaptured_solo_matches(raw_root, csv_root, cutoff_jst, puuid)
    if not candidates:
        raise CheckpointNotRequiredError("No uncaptured Solo/Duo match; checkpoint was not created")
    if len(candidates) == 1:
        raise CheckpointNotRequiredError("One uncaptured Solo/Duo match; use capture instead")
    after = compact_rank(fetch_current_rank())
    checkpoint = build_checkpoint(before, events, candidates, after, captured_at)
    output = checkpoint_path(raw_root, checkpoint["snapshot_id"])
    if output.exists():
        raise LPSnapshotError(f"Checkpoint already exists: {output}")
    atomic_json_dump(output, checkpoint)
    rebuild_lp_history(raw_root, csv_root)
    return output


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "capture", "checkpoint", "rebuild"))
    parser.add_argument("--data-root")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--next-rank-before-json",
        help="Non-identifying Queue 420 LCU rank captured before the match being captured",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    paths = get_data_paths(args.data_root)
    try:
        if args.command == "baseline":
            output = create_baseline(
                paths.csv / "current_rank.json", paths.raw, paths.csv
            )
            print(f"LP baseline saved: {output}")
            return 0
        if args.command == "rebuild":
            rebuild_lp_history(paths.raw, paths.csv)
            print(f"LP history rebuilt: {history_path(paths.csv)}")
            return 0

        if args.command == "checkpoint":
            from riot_api import get_current_solo_rank

            current_rank = load_json(paths.csv / "current_rank.json")
            puuid = current_rank.get("puuid")
            if not isinstance(puuid, str) or not puuid:
                raise LPSnapshotError("current_rank.json does not contain a PUUID for League-V4")
            output = create_checkpoint(
                paths.raw, paths.csv, lambda: get_current_solo_rank(puuid), puuid=puuid
            )
            print(f"LP checkpoint saved: {output}")
            return 0

        # Import API configuration only for the explicit capture command.
        from config import GAME_NAME, TAG_LINE
        from riot_api import get_current_solo_rank, get_match_detail, get_match_ids, get_puuid

        puuid = get_puuid(GAME_NAME, TAG_LINE)
        next_rank_before = None
        if args.next_rank_before_json:
            try:
                next_rank_before = json.loads(args.next_rank_before_json)
            except json.JSONDecodeError as error:
                raise LPSnapshotError("Invalid next pre-match rank JSON") from error
        output = capture_one(
            puuid,
            paths.raw,
            paths.csv,
            get_match_ids,
            get_match_detail,
            lambda: get_current_solo_rank(puuid),
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
            next_rank_before=next_rank_before,
        )
        if output:
            print(f"Exact LP snapshot saved: {output}")
        return 0
    except AmbiguousHistoryError as error:
        print(f"AMBIGUOUS: {error}", file=sys.stderr)
        return 2
    except (LPSnapshotError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
