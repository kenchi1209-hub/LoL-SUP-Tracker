"""Capture exact, per-match Solo/Duo LP history after a ranked match.

This command is intentionally separate from the daily batch update.  It writes a
match snapshot only when exactly one previously uncaptured Solo/Duo match exists
and League-V4 confirms the expected W/L counter transition.
"""

import argparse
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
    return sorted(snapshots, key=lambda item: (item["game_datetime_jst"], item["match_id"]))


def rank_state(rank):
    return {
        key: rank.get(key)
        for key in ("tier", "division", "lp", "wins", "losses")
    }


def validated_snapshots(raw_root, baseline):
    """Return the exact chain, refusing corrupt or discontinuous history."""
    current = rank_state(baseline)
    validated = []
    for snapshot in load_confirmed_snapshots(raw_root):
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
        validated.append(snapshot)
        current = after
    return validated


def previous_state(raw_root):
    baseline = load_json(baseline_path(raw_root))
    if baseline.get("snapshot_type") != "baseline":
        raise LPSnapshotError("Invalid LP baseline")
    snapshots = validated_snapshots(raw_root, baseline)
    if snapshots:
        latest = snapshots[-1]
        return latest["after"], latest["captured_at_jst"], snapshots
    rank = {key: baseline.get(key) for key in ("tier", "division", "lp", "wins", "losses")}
    return rank, baseline["captured_at_jst"], snapshots


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
        "confidence": snapshot["confidence"],
    }


def rebuild_lp_history(raw_root, csv_root):
    baseline = load_json(baseline_path(raw_root))
    public_baseline = {
        key: baseline.get(key)
        for key in (
            "captured_at_jst", "tier", "division", "lp", "wins", "losses", "confidence"
        )
    }
    history = {
        "schema_version": SCHEMA_VERSION,
        "queue_type": SOLO_QUEUE_TYPE,
        "queue_id": SOLO_QUEUE_ID,
        "baseline": public_baseline,
        "matches": [history_record(item) for item in validated_snapshots(raw_root, baseline)],
    }
    atomic_json_dump(history_path(csv_root), history)
    return history


def capture_one(
    puuid, raw_root, csv_root, fetch_match_ids, fetch_match_detail,
    fetch_current_rank, timeout_seconds=120, poll_interval_seconds=5,
    captured_at=None, monotonic=time.monotonic, sleep=time.sleep,
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
    after = wait_for_league_update(
        before, match["win"], fetch_current_rank, timeout_seconds,
        poll_interval_seconds, monotonic, sleep,
    )
    snapshot = build_rank_after(match, before, after, captured_at)
    output = paths_for_match(match["match_id"], raw_root).rank_after
    if output.exists():
        raise LPSnapshotError(f"rank_after already exists: {output}")
    atomic_json_dump(output, snapshot)
    rebuild_lp_history(raw_root, csv_root)
    return output


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "capture", "rebuild"))
    parser.add_argument("--data-root")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--poll-interval", type=float, default=5)
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

        # Import API configuration only for the explicit capture command.
        from config import GAME_NAME, TAG_LINE
        from riot_api import get_current_solo_rank, get_match_detail, get_match_ids, get_puuid

        puuid = get_puuid(GAME_NAME, TAG_LINE)
        output = capture_one(
            puuid,
            paths.raw,
            paths.csv,
            get_match_ids,
            get_match_detail,
            lambda: get_current_solo_rank(puuid),
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
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
