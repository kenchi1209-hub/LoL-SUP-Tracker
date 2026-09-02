"""LP Progress page payload and HTML generation.

The browser receives only the compact, display-safe LP timeline.  PrivateData
remains the source of truth for the complete LP history and match data.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from champion_registry import champion_icon_id, champion_name_ja
from data_paths import get_data_paths
from lp_snapshot import rank_value
from site_builder.patches import normalize_patch
from site_builder.render import (
    BASE_DIR,
    esc,
    page_header_context,
    render_navigation,
)
from timezone_utils import JST


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SEASONS_PATH = REPOSITORY_ROOT / "lp_seasons.json"
_paths = get_data_paths()
LP_HISTORY_PATH = _paths.csv / "lp_history.json"
RAW_ROOT = _paths.raw
HISTORICAL_RECONSTRUCTED_PATH = (
    _paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_reconstructed.json"
)
HISTORICAL_MAPPING_PATH = (
    _paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_match_mapping.json"
)
MOBALYTICS_HISTORICAL_PATH = (
    _paths.raw / "lp_progress" / "recovered" / "mobalytics_historical.json"
)


def configure_data_root(data_root=None):
    """Point the build at a local or PrivateData root."""
    global LP_HISTORY_PATH, RAW_ROOT, HISTORICAL_RECONSTRUCTED_PATH, HISTORICAL_MAPPING_PATH, MOBALYTICS_HISTORICAL_PATH
    paths = get_data_paths(data_root)
    LP_HISTORY_PATH = paths.csv / "lp_history.json"
    RAW_ROOT = paths.raw
    HISTORICAL_RECONSTRUCTED_PATH = (
        paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_reconstructed.json"
    )
    HISTORICAL_MAPPING_PATH = (
        paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_match_mapping.json"
    )
    MOBALYTICS_HISTORICAL_PATH = (
        paths.raw / "lp_progress" / "recovered" / "mobalytics_historical.json"
    )


def _load_json(path, fallback):
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError):
        return fallback
    return value


def load_lp_history():
    value = _load_json(LP_HISTORY_PATH, {})
    return value if isinstance(value, dict) else {}


def _rank_after_record(match_id, expected_rank):
    """Read only the public-safe W/L pair from the selected exact snapshot."""
    snapshot = _load_json(RAW_ROOT / str(match_id) / "rank_after.json", {})
    after = snapshot.get("after") if isinstance(snapshot, dict) else None
    rank = _rank(after) if isinstance(after, dict) else None
    if rank != expected_rank:
        return None
    wins, losses = after.get("wins"), after.get("losses")
    if not isinstance(wins, int) or not isinstance(losses, int):
        return None
    return {"wins": wins, "losses": losses}


def _timestamp_jst(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(JST).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _historical_payload(rows_by_id, official_ids):
    """Build an optional, display-safe Blitz recovered series.

    The source remains explicitly separate from official exact LP history.  Only
    reconstructed exact mappings are exposed, and official match overlaps are
    withheld so the chart cannot draw the same match twice.
    """
    recovered = _load_json(HISTORICAL_RECONSTRUCTED_PATH, {})
    mapping = _load_json(HISTORICAL_MAPPING_PATH, {})
    mobalytics = _load_json(MOBALYTICS_HISTORICAL_PATH, {})
    if (
        not isinstance(recovered, dict)
        or recovered.get("source") != "blitz"
        or recovered.get("confidence") != "historical_reconstructed"
        or not isinstance(recovered.get("matches"), list)
    ):
        return None

    mobalytics_records = []
    if (
        isinstance(mobalytics, dict)
        and mobalytics.get("source") == "mobalytics"
        and mobalytics.get("confidence") == "mobalytics_historical_verified"
        and isinstance(mobalytics.get("matches"), list)
    ):
        mobalytics_records = [
            record
            for record in mobalytics["matches"]
            if isinstance(record, dict)
            and record.get("source") == "mobalytics_historical"
            and record.get("confidence") == "mobalytics_historical_verified"
        ]

    mapping_by_game = {
        item.get("games"): item
        for item in mapping.get("mappings", [])
        if isinstance(item, dict) and isinstance(item.get("games"), int)
    }
    resolved_games = {
        record.get("game_number")
        for record in mobalytics_records
        if isinstance(record.get("game_number"), int)
    }
    gaps = [
        {
            "game_number": item["games"],
            "timestamp_jst": _timestamp_jst(item.get("timestamp")),
            "reason": str((item.get("evidence") or {}).get("reason", "ambiguous")),
        }
        for item in mapping_by_game.values()
        if item.get("status") != "exact_match" and item.get("games") not in resolved_games
    ]
    points = []
    usable_matches = []
    segment_index = -1
    previous_game = None
    records = [*recovered["matches"], *mobalytics_records]
    for record in sorted(records, key=lambda item: item.get("game_number", -1)):
        if not isinstance(record, dict):
            continue
        match_id = str(record.get("match_id", ""))
        game_number = record.get("game_number")
        rank = _rank({
            "tier": record.get("tier_after"),
            "division": record.get("division_after"),
            "lp": record.get("lp_after"),
        })
        timestamp_jst = str(record.get("game_datetime_jst", "")) or _timestamp_jst(record.get("blitz_timestamp"))
        row = rows_by_id.get(match_id)
        if (
            not match_id
            or not isinstance(game_number, int)
            or rank is None
            or not timestamp_jst
            or not isinstance(row, dict)
        ):
            continue
        if previous_game is None or game_number != previous_game + 1:
            segment_index += 1
        previous_game = game_number
        metadata = _match_metadata(row, match_id)
        item = {
            "kind": "historical",
            "match_id": match_id,
            "match_url": metadata["match_url"],
            "timestamp_jst": timestamp_jst,
            "game_datetime_jst": timestamp_jst,
            "champion": metadata["champion"],
            "champion_name": metadata["champion_name"],
            "champion_icon_id": metadata["champion_icon_id"],
            "patch": metadata["patch"],
            "win": metadata["win"],
            "kills": metadata["kills"],
            "deaths": metadata["deaths"],
            "assists": metadata["assists"],
            "kp_pct": metadata["kp_pct"],
            "vision_score": metadata["vision_score"],
            "vision_score_per_min": metadata["vision_score_per_min"],
            "rank": rank,
            "after": rank,
            "score": rank["score"],
            "candidate_lp_delta": record.get("lp_delta", record.get("candidate_lp_delta")),
            "lp_delta": record.get("lp_delta", record.get("candidate_lp_delta")),
            "game_number": game_number,
            "wins_after": record.get("wins_after"),
            "losses_after": record.get("losses_after"),
            "segment_id": f"historical-{segment_index}",
            "source": str(record.get("source", "blitz")),
            "confidence": str(record.get("confidence", "historical_reconstructed")),
        }
        usable_matches.append(item)
        if match_id not in official_ids:
            points.append(item)

    if not usable_matches:
        return None
    return {
        "source": "historical",
        "confidence": "mixed_historical",
        "notice": "過去履歴の一部はBlitzまたはMobalyticsのMatch記録から復元した参考値です。正式取得LPとは区別して表示しています。",
        "points": points,
        "usable_matches": usable_matches,
        "gaps": gaps,
        "overlap_excluded": len(usable_matches) - len(points),
    }


def load_seasons():
    value = _load_json(SEASONS_PATH, {"seasons": []})
    seasons = value.get("seasons", []) if isinstance(value, dict) else []
    return [
        {
            "id": str(item.get("id", "")),
            "label": str(item.get("label", "")),
            "start_jst": str(item.get("start_jst", "")),
            "end_jst": item.get("end_jst"),
        }
        for item in seasons
        if isinstance(item, dict) and item.get("start_jst")
    ]


def _rank(rank):
    """Return a display-safe rank with the Phase 1 continuous score."""
    if not isinstance(rank, dict):
        return None
    try:
        compact = {
            "tier": str(rank.get("tier", "")).upper(),
            "division": rank.get("division", rank.get("rank")),
            "lp": int(rank.get("lp", rank.get("leaguePoints", 0))),
        }
        score = rank_value(compact)
    except (TypeError, ValueError):
        return None
    return compact | {"score": score}


def _match_metadata(row, match_id):
    """Only retain fields that the public LP view needs."""
    if not isinstance(row, dict):
        return {
            "match_id": match_id,
            "match_url": _match_url(match_id),
            "game_datetime_jst": "",
            "champion": "Unknown",
            "champion_name": "Unknown",
            "champion_icon_id": "",
            "patch": "",
            "win": None,
            "kills": None,
            "deaths": None,
            "assists": None,
            "kp_pct": None,
            "vision_score": None,
            "vision_score_per_min": None,
            "queue": "RANKED_SOLO_5x5",
        }
    champion = str(row.get("champion", ""))

    def match_integer(name):
        try:
            return int(float(row.get(name)))
        except (TypeError, ValueError):
            return None

    def match_float(name):
        try:
            value = row.get(name)
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    kills = match_integer("kills")
    deaths = match_integer("deaths")
    assists = match_integer("assists")
    team_kills = match_integer("team_kills")
    vision_score = match_float("vision_score")
    vision_score_per_min = match_float("vision_score_per_min")
    duration_seconds = match_float("game_duration_seconds")
    if vision_score_per_min is None and vision_score is not None and duration_seconds and duration_seconds > 0:
        vision_score_per_min = vision_score / (duration_seconds / 60)
    kp_pct = (
        (kills + assists) / team_kills * 100
        if kills is not None and assists is not None and team_kills and team_kills > 0
        else None
    )

    return {
        "match_id": match_id,
        "match_url": _match_url(match_id),
        "game_datetime_jst": str(row.get("date", "")).replace(" ", "T") + "+09:00",
        "champion": champion,
        "champion_name": champion_name_ja(champion),
        "champion_icon_id": champion_icon_id(champion),
        "patch": normalize_patch(row.get("patch", "")),
        "win": bool(row.get("_win", False)),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kp_pct": kp_pct,
        "vision_score": vision_score,
        "vision_score_per_min": vision_score_per_min,
        "queue": "RANKED_SOLO_5x5",
    }


def _match_url(match_id):
    """Return the public Match History anchor for a known match only."""
    match_id = str(match_id or "")
    if not match_id:
        return ""
    # Mirrors encodeURIComponent() used by match-history.js for the DOM id.
    encoded_match_id = quote(match_id, safe="-_.!~*'()")
    return f"history.html#match-{encoded_match_id}"


def _history_match(record, rows_by_id):
    match_id = str(record.get("match_id", ""))
    metadata = _match_metadata(rows_by_id.get(match_id), match_id)
    before = _rank({
        "tier": record.get("tier_before"),
        "division": record.get("division_before"),
        "lp": record.get("lp_before"),
    })
    after = _rank({
        "tier": record.get("tier_after"),
        "division": record.get("division_after"),
        "lp": record.get("lp_after"),
    })
    # lp_history remains authoritative for exact snapshot values; my_matches
    # enriches only the display name/icon if it is available.
    champion = str(record.get("champion", metadata["champion"]))
    metadata.update({
        "game_datetime_jst": str(record.get("game_datetime_jst", metadata["game_datetime_jst"])),
        "champion": champion,
        "champion_name": champion_name_ja(champion),
        "champion_icon_id": champion_icon_id(champion),
        "patch": normalize_patch(record.get("patch", metadata["patch"])),
        "win": bool(record.get("win", metadata["win"])),
        "queue": str(record.get("queue", "RANKED_SOLO_5x5")),
        "before": before,
        "after": after,
        "score": after["score"] if after else None,
        "lp_delta": record.get("lp_delta"),
        "confidence": str(record.get("confidence", "")),
        "segment_id": str(record.get("segment_id", "")),
        "source": "exact",
    })
    rank_after_record = _rank_after_record(match_id, after)
    if rank_after_record:
        metadata["wins_after"] = rank_after_record["wins"]
        metadata["losses_after"] = rank_after_record["losses"]
    return metadata


def _assign_official_game_numbers(exact_matches, historical_matches):
    """Attach verified cumulative game numbers to official exact records.

    Recovered records are the direct source when IDs overlap.  An official-only
    run is numbered only when known recovered anchors surround it and its exact
    win/loss sequence exactly reaches the next anchor's cumulative record.
    """
    historical_by_id = {item["match_id"]: item for item in historical_matches}
    for item in exact_matches:
        historical = historical_by_id.get(item["match_id"])
        if historical:
            item["game_number"] = historical["game_number"]
            item["wins_after"] = historical.get("wins_after")
            item["losses_after"] = historical.get("losses_after")
        elif isinstance(item.get("wins_after"), int) and isinstance(item.get("losses_after"), int):
            item["game_number"] = item["wins_after"] + item["losses_after"]

    known = [index for index, item in enumerate(exact_matches) if isinstance(item.get("game_number"), int)]
    for left_index, right_index in zip(known, known[1:]):
        left = exact_matches[left_index]
        right = exact_matches[right_index]
        span = right_index - left_index
        left_game, right_game = left["game_number"], right["game_number"]
        if right_game - left_game != span:
            continue
        left_wins, left_losses = left.get("wins_after"), left.get("losses_after")
        right_wins, right_losses = right.get("wins_after"), right.get("losses_after")
        if not all(isinstance(value, int) for value in (left_wins, left_losses, right_wins, right_losses)):
            continue
        bridge = exact_matches[left_index + 1:right_index + 1]
        wins = sum(item.get("win") is True for item in bridge)
        losses = sum(item.get("win") is False for item in bridge)
        if (left_wins + wins, left_losses + losses) != (right_wins, right_losses):
            continue
        for offset, item in enumerate(bridge, start=1):
            item["game_number"] = left_game + offset


def _usable_matches(exact_matches, historical):
    """Create one public-safe summary series with official exact precedence."""
    recovered = list((historical or {}).get("usable_matches", []))
    by_match_id = {item["match_id"]: item for item in recovered}
    _assign_official_game_numbers(exact_matches, recovered)
    for exact in exact_matches:
        historical_item = by_match_id.get(exact["match_id"], {})
        summary = dict(historical_item)
        summary.update(exact)
        summary["kind"] = "exact"
        summary["source"] = "exact"
        summary["rank"] = exact.get("after")
        summary["score"] = exact.get("score")
        summary["lp_delta"] = exact.get("lp_delta")
        if "game_number" not in summary and historical_item.get("game_number") is not None:
            summary["game_number"] = historical_item["game_number"]
        by_match_id[exact["match_id"]] = summary
    return sorted(
        by_match_id.values(),
        key=lambda item: (item.get("game_number") is None, item.get("game_number", 0), item.get("game_datetime_jst", "")),
    )


def _summary_for_matches(matches, latest_rank=None, latest_record=None):
    """Return compact metrics for the already de-duplicated usable history."""
    ordered = [item for item in matches if isinstance(item.get("rank"), dict)]
    ordered.sort(key=lambda item: (item.get("game_number") is None, item.get("game_number", 0), item.get("game_datetime_jst", "")))
    known = [item for item in ordered if isinstance(item.get("win"), bool)]
    wins = sum(item["win"] for item in known)
    losses = len(known) - wins
    latest_history_record = next(
        (
            item for item in reversed(ordered)
            if isinstance(item.get("wins_after"), int) and isinstance(item.get("losses_after"), int)
        ),
        None,
    )
    if latest_history_record:
        wins, losses = latest_history_record["wins_after"], latest_history_record["losses_after"]
    if latest_record:
        wins, losses = latest_record["wins"], latest_record["losses"]
    deltas = [item for item in ordered if isinstance(item.get("lp_delta"), (int, float))]
    start_rank = ordered[0]["rank"] if ordered else None
    end_rank = latest_rank or (ordered[-1]["rank"] if ordered else None)
    peak = max(ordered, key=lambda item: (item["rank"]["score"], item.get("game_number", -1))) if ordered else None
    total_games = max((item.get("game_number", 0) for item in ordered if isinstance(item.get("game_number"), int)), default=0)
    tracked = len({item.get("game_number") for item in ordered if isinstance(item.get("game_number"), int)})
    return {
        "record": {"wins": wins, "losses": losses, "known": len(known)},
        "net_lp": sum(item["lp_delta"] for item in deltas) if deltas else None,
        "start_rank": start_rank,
        "end_rank": end_rank,
        "peak_rank": peak["rank"] if peak else None,
        "peak_game_number": peak.get("game_number") if peak else None,
        "games_tracked": tracked,
        "games_total": total_games,
        "lp_available": len(deltas),
        "lp_delta": sum(item["lp_delta"] for item in deltas) if deltas else None,
    }


def build_lp_payload(rows, version):
    """Build a minimum public LP payload from PrivateData read-only inputs."""
    history = load_lp_history()
    rows_by_id = {str(row.get("match_id", "")): row for row in rows}
    baseline = _rank(history.get("baseline", {}))
    if baseline is None:
        return {
            "schema_version": 1,
            "tracking_started_jst": "",
            "history_started_jst": "",
            "queue": "RANKED_SOLO_5x5",
            "baseline": None,
            "checkpoints": [],
            "points": [],
            "matches": [],
            "usable_matches": [],
            "usable_summary": _summary_for_matches([]),
            "historical": _historical_payload(rows_by_id, set()),
            "seasons": load_seasons(),
            "ddragon_version": version,
        }

    base_event = {
        "kind": "baseline",
        "timestamp_jst": str(history["baseline"].get("captured_at_jst", "")),
        "rank": baseline,
        "score": baseline["score"],
        "game_number": int(history["baseline"].get("wins", 0)) + int(history["baseline"].get("losses", 0)),
        "segment_id": str(history["baseline"].get("segment_id", "segment-0")),
    }
    checkpoints = []
    points = [base_event]
    ambiguous_matches = []
    for checkpoint in history.get("checkpoints", []):
        if not isinstance(checkpoint, dict):
            continue
        rank = _rank(checkpoint)
        if rank is None:
            continue
        gap = checkpoint.get("gap") if isinstance(checkpoint.get("gap"), dict) else {}
        public_gap = {
            "games": gap.get("games"),
            "wins": gap.get("wins"),
            "losses": gap.get("losses"),
            "match_ids": [str(value) for value in gap.get("match_ids", []) if isinstance(value, str)],
        }
        public_checkpoint = {
            "kind": "checkpoint",
            "snapshot_id": str(checkpoint.get("snapshot_id", "")),
            "timestamp_jst": str(checkpoint.get("captured_at_jst", "")),
            "rank": rank,
            "score": rank["score"],
            "game_number": int(checkpoint.get("wins", 0)) + int(checkpoint.get("losses", 0)),
            "segment_id": str(checkpoint.get("segment_id", "")),
            "gap": public_gap,
        }
        checkpoints.append(public_checkpoint)
        points.append(public_checkpoint)
        for match_id in public_gap["match_ids"]:
            item = _match_metadata(rows_by_id.get(match_id), match_id)
            item.update({
                "lp_delta": None,
                "confidence": "ambiguous",
                "segment_id": public_checkpoint["segment_id"],
                "source": "gap",
            })
            ambiguous_matches.append(item)

    exact_matches = [
        _history_match(record, rows_by_id)
        for record in history.get("matches", [])
        if isinstance(record, dict) and record.get("confidence") == "exact"
    ]
    historical = _historical_payload(
        rows_by_id,
        {item["match_id"] for item in exact_matches},
    )
    usable_matches = _usable_matches(exact_matches, historical)
    usable_by_id = {item["match_id"]: item for item in usable_matches}
    for item in exact_matches:
        usable = usable_by_id.get(item["match_id"], {})
        points.append({
            "kind": "exact",
            "timestamp_jst": item["game_datetime_jst"],
            "match_id": item["match_id"],
            "match_url": item["match_url"],
            "champion": item["champion"],
            "champion_name": item["champion_name"],
            "patch": item["patch"],
            "win": item["win"],
            "queue": item["queue"],
            "rank": item["after"],
            "score": item["score"],
            "game_number": usable.get("game_number"),
            "lp_delta": item["lp_delta"],
            "confidence": item["confidence"],
            "segment_id": item["segment_id"],
        })

    matches = ambiguous_matches + exact_matches
    matches.sort(key=lambda item: (item.get("game_datetime_jst", ""), item["match_id"]))
    points.sort(key=lambda item: (item.get("timestamp_jst", ""), item.get("match_id", "")))
    latest = max(
        (item for item in exact_matches if item.get("after")),
        key=lambda item: item.get("game_datetime_jst", ""),
        default=None,
    )
    if latest is None and checkpoints:
        latest_rank = checkpoints[-1]["rank"]
    else:
        latest_rank = latest["after"] if latest else baseline
    latest_record = _rank_after_record(latest["match_id"], latest_rank) if latest else None
    return {
        "schema_version": 1,
        "tracking_started_jst": base_event["timestamp_jst"],
        "history_started_jst": usable_matches[0].get("game_datetime_jst", "") if usable_matches else base_event["timestamp_jst"],
        "queue": str(history.get("queue_type", "RANKED_SOLO_5x5")),
        "baseline": base_event,
        "checkpoints": checkpoints,
        "points": points,
        "matches": matches,
        "usable_matches": usable_matches,
        "usable_summary": _summary_for_matches(usable_matches, latest_rank, latest_record),
        "historical": historical,
        "latest_rank": latest_rank,
        "seasons": load_seasons(),
        "ddragon_version": version,
    }


LP_TEMPLATE = (BASE_DIR / "templates" / "lp.html").read_text(encoding="utf-8")


def build_lp_page(rows, payload):
    """Return the shell with a compact, display-safe JSON payload."""
    context = page_header_context(rows)
    return LP_TEMPLATE.format(
        **context,
        navigation=render_navigation("lp"),
        payload=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"),
    )
