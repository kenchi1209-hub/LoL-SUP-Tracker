"""CSV/JSON の読み込み、型変換、試合データの集計を扱う。"""

import csv
import json
import os
from data_paths import get_data_paths

_paths = get_data_paths()
MATCHES_CSV = _paths.csv / "my_matches.csv"
LAST_UPDATED_TXT = _paths.csv / "last_updated.txt"
CURRENT_RANK_JSON = _paths.csv / "current_rank.json"


def configure_data_root(data_root=None):
    global MATCHES_CSV, LAST_UPDATED_TXT, CURRENT_RANK_JSON
    paths = get_data_paths(data_root)
    MATCHES_CSV = paths.csv / "my_matches.csv"
    LAST_UPDATED_TXT = paths.csv / "last_updated.txt"
    CURRENT_RANK_JSON = paths.csv / "current_rank.json"


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def seconds_to_mmss(seconds):
    seconds = to_int(seconds)
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"


def load_matches():
    if not os.path.exists(MATCHES_CSV):
        return []
    with open(MATCHES_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_win"] = str(r.get("win", "")).strip().lower() == "true"
        r["_k"] = to_int(r.get("kills"))
        r["_d"] = to_int(r.get("deaths"))
        r["_a"] = to_int(r.get("assists"))
        r["_cs"] = to_float(r.get("cs"))
        r["_cspm"] = to_float(r.get("cs_per_min"))
        r["_vs"] = to_float(r.get("vision_score"))
        r["_vspm"] = to_float(r.get("vision_score_per_min"))
        r["_dmg"] = to_int(r.get("total_damage_to_champions"))
    # 5分未満の試合はリメイク/即終了扱いとしてサイト集計から除外
    rows = [r for r in rows if to_int(r.get("game_duration_seconds")) >= 300]
    # 日付降順（新しい順）
    rows.sort(key=lambda x: x.get("date", ""), reverse=True)
    return rows


def load_last_updated():
    if not os.path.exists(LAST_UPDATED_TXT):
        return "-"
    with open(LAST_UPDATED_TXT, encoding="utf-8") as f:
        return f.read().strip() or "-"


def load_current_rank():
    if not os.path.exists(CURRENT_RANK_JSON):
        return None
    try:
        with open(CURRENT_RANK_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def format_rank_name(rank_data):
    if not rank_data:
        return "UNRANKED"
    tier = str(rank_data.get("tier", "")).upper()
    division = str(rank_data.get("rank", ""))
    tier_labels = {
        "IRON": "IRON",
        "BRONZE": "BRONZE",
        "SILVER": "SILVER",
        "GOLD": "GOLD",
        "PLATINUM": "PLATINUM",
        "EMERALD": "EMERALD",
        "DIAMOND": "DIAMOND",
        "MASTER": "MASTER",
        "GRANDMASTER": "GRANDMASTER",
        "CHALLENGER": "CHALLENGER",
    }
    label = tier_labels.get(tier, tier)
    return f"{label} {division}".strip()


def aggregate(rows):
    """試合リストから成績サマリーを計算する。"""
    n = len(rows)
    if n == 0:
        return None

    wins = sum(1 for r in rows if r["_win"])
    sumk = sum(r["_k"] for r in rows)
    sumd = sum(r["_d"] for r in rows)
    suma = sum(r["_a"] for r in rows)

    total_cs = sum(r["_cs"] for r in rows)
    total_vs = sum(r["_vs"] for r in rows)
    total_seconds = sum(
        to_int(r.get("game_duration_seconds"))
        for r in rows
    )
    total_minutes = total_seconds / 60 if total_seconds else 0

    return {
        "games": n,
        "wins": wins,
        "losses": n - wins,
        "winrate": wins / n * 100,
        "avg_k": sumk / n,
        "avg_d": sumd / n,
        "avg_a": suma / n,
        "kda": (sumk + suma) / max(sumd, 1),
        "avg_cs": total_cs / n,
        "avg_cspm": total_cs / total_minutes if total_minutes else 0,
        "avg_vs": total_vs / n,
        "avg_vspm": total_vs / total_minutes if total_minutes else 0,
    }


def group_by(rows, keyfn):
    groups = {}
    for r in rows:
        groups.setdefault(keyfn(r), []).append(r)
    return groups


def table_rows_for_groups(groups, label_fn, sort_key="games"):
    items = []
    for key, grp in groups.items():
        agg = aggregate(grp)
        agg["label"] = label_fn(key)
        agg["_key"] = key
        items.append(agg)
    items.sort(key=lambda x: x[sort_key], reverse=True)
    return items


def is_ranked(row):
    return str(row.get("queue_id", "")) == "420"


def is_support(row):
    return row.get("role") == "UTILITY"
