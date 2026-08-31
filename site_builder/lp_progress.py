"""LP Progress page payload and HTML generation.

The browser receives only the compact, display-safe LP timeline.  PrivateData
remains the source of truth for the complete LP history and match data.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

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
HISTORICAL_RECONSTRUCTED_PATH = (
    _paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_reconstructed.json"
)
HISTORICAL_MAPPING_PATH = (
    _paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_match_mapping.json"
)


def configure_data_root(data_root=None):
    """Point the build at a local or PrivateData root."""
    global LP_HISTORY_PATH, HISTORICAL_RECONSTRUCTED_PATH, HISTORICAL_MAPPING_PATH
    paths = get_data_paths(data_root)
    LP_HISTORY_PATH = paths.csv / "lp_history.json"
    HISTORICAL_RECONSTRUCTED_PATH = (
        paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_reconstructed.json"
    )
    HISTORICAL_MAPPING_PATH = (
        paths.raw / "lp_progress" / "recovered" / "blitz_2026-08-31_match_mapping.json"
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
    if (
        not isinstance(recovered, dict)
        or recovered.get("source") != "blitz"
        or recovered.get("confidence") != "historical_reconstructed"
        or not isinstance(recovered.get("matches"), list)
    ):
        return None

    mapping_by_game = {
        item.get("games"): item
        for item in mapping.get("mappings", [])
        if isinstance(item, dict) and isinstance(item.get("games"), int)
    }
    gaps = [
        {
            "game_number": item["games"],
            "timestamp_jst": _timestamp_jst(item.get("timestamp")),
            "reason": str((item.get("evidence") or {}).get("reason", "ambiguous")),
        }
        for item in mapping_by_game.values()
        if item.get("status") != "exact_match"
    ]
    points = []
    segment_index = -1
    previous_game = None
    for record in sorted(recovered["matches"], key=lambda item: item.get("game_number", -1)):
        if not isinstance(record, dict):
            continue
        match_id = str(record.get("match_id", ""))
        game_number = record.get("game_number")
        rank = _rank({
            "tier": record.get("tier_after"),
            "division": record.get("division_after"),
            "lp": record.get("lp_after"),
        })
        timestamp_jst = _timestamp_jst(record.get("blitz_timestamp"))
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
        if match_id in official_ids:
            continue
        metadata = _match_metadata(row, match_id)
        points.append({
            "kind": "historical",
            "match_id": match_id,
            "timestamp_jst": timestamp_jst,
            "champion": metadata["champion"],
            "champion_name": metadata["champion_name"],
            "champion_icon_id": metadata["champion_icon_id"],
            "patch": metadata["patch"],
            "win": metadata["win"],
            "rank": rank,
            "score": rank["score"],
            "candidate_lp_delta": record.get("candidate_lp_delta"),
            "segment_id": f"historical-{segment_index}",
            "source": "blitz",
            "confidence": "historical_reconstructed",
        })

    if not points:
        return None
    return {
        "source": "blitz",
        "confidence": "historical_reconstructed",
        "notice": "過去履歴の一部はBlitz保存データから復元した参考値です。正式取得LPとは区別して表示しています。",
        "points": points,
        "gaps": gaps,
        "overlap_excluded": len(recovered["matches"]) - len(points),
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
            "game_datetime_jst": "",
            "champion": "Unknown",
            "champion_name": "Unknown",
            "champion_icon_id": "",
            "patch": "",
            "win": None,
            "queue": "RANKED_SOLO_5x5",
        }
    champion = str(row.get("champion", ""))
    return {
        "match_id": match_id,
        "game_datetime_jst": str(row.get("date", "")).replace(" ", "T") + "+09:00",
        "champion": champion,
        "champion_name": champion_name_ja(champion),
        "champion_icon_id": champion_icon_id(champion),
        "patch": normalize_patch(row.get("patch", "")),
        "win": bool(row.get("_win", False)),
        "queue": "RANKED_SOLO_5x5",
    }


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
    return metadata


def build_lp_payload(rows, version):
    """Build a minimum public LP payload from PrivateData read-only inputs."""
    history = load_lp_history()
    rows_by_id = {str(row.get("match_id", "")): row for row in rows}
    baseline = _rank(history.get("baseline", {}))
    if baseline is None:
        return {
            "schema_version": 1,
            "tracking_started_jst": "",
            "queue": "RANKED_SOLO_5x5",
            "baseline": None,
            "checkpoints": [],
            "points": [],
            "matches": [],
            "historical": _historical_payload(rows_by_id, set()),
            "seasons": load_seasons(),
            "ddragon_version": version,
        }

    base_event = {
        "kind": "baseline",
        "timestamp_jst": str(history["baseline"].get("captured_at_jst", "")),
        "rank": baseline,
        "score": baseline["score"],
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
    for item in exact_matches:
        points.append({
            "kind": "exact",
            "timestamp_jst": item["game_datetime_jst"],
            "match_id": item["match_id"],
            "champion": item["champion"],
            "champion_name": item["champion_name"],
            "patch": item["patch"],
            "win": item["win"],
            "queue": item["queue"],
            "rank": item["after"],
            "score": item["score"],
            "lp_delta": item["lp_delta"],
            "confidence": item["confidence"],
            "segment_id": item["segment_id"],
        })

    matches = ambiguous_matches + exact_matches
    matches.sort(key=lambda item: (item.get("game_datetime_jst", ""), item["match_id"]))
    points.sort(key=lambda item: (item.get("timestamp_jst", ""), item.get("match_id", "")))
    latest = next((item for item in reversed(exact_matches) if item.get("after")), None)
    if latest is None and checkpoints:
        latest_rank = checkpoints[-1]["rank"]
    else:
        latest_rank = latest["after"] if latest else baseline
    historical = _historical_payload(
        rows_by_id,
        {item["match_id"] for item in exact_matches},
    )
    return {
        "schema_version": 1,
        "tracking_started_jst": base_event["timestamp_jst"],
        "queue": str(history.get("queue_type", "RANKED_SOLO_5x5")),
        "baseline": base_event,
        "checkpoints": checkpoints,
        "points": points,
        "matches": matches,
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
