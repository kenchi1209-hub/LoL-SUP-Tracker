import csv
import os
from collections import defaultdict
from champion_registry import champion_name_ja
from queue_map import queue_id_to_name
from data_paths import CSV_ROOT

MY_MATCHES_CSV_PATH = CSV_ROOT / "my_matches.csv"
SUMMARY_TXT_PATH = CSV_ROOT / "summary.txt"

def to_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def to_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default

def is_win(value):
    return str(value).lower() == "true"

def safe_avg(values):
    return sum(values) / len(values) if values else 0

def get_date_range(rows):
    if not rows:
        return "", ""
    dates = [r["date"] for r in rows if r.get("date")]
    if not dates:
        return "", ""
    return min(dates), max(dates)

def format_percent(value):
    return f"{value * 100:.1f}%"

def format_kda(kills, deaths, assists):
    if deaths == 0:
        return "Perfect"
    return f"{(kills + assists) / deaths:.2f}"

def load_my_matches(csv_path=MY_MATCHES_CSV_PATH):
    if not os.path.exists(csv_path):
        print(f"my_matches.csvが見つかりません: {csv_path}")
        return []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows

def summarize_overall(rows):
    total = len(rows)
    wins = sum(1 for r in rows if is_win(r["win"]))
    losses = total - wins

    kills = [to_int(r["kills"]) for r in rows]
    deaths = [to_int(r["deaths"]) for r in rows]
    assists = [to_int(r["assists"]) for r in rows]
    cs = [to_float(r["cs"]) for r in rows]
    cs_per_min = [to_float(r["cs_per_min"]) for r in rows]
    vision_score = [to_float(r["vision_score"]) for r in rows]
    vision_score_per_min = [to_float(r["vision_score_per_min"]) for r in rows]

    total_kills = sum(kills)
    total_deaths = sum(deaths)
    total_assists = sum(assists)

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total if total else 0,
        "avg_kills": safe_avg(kills),
        "avg_deaths": safe_avg(deaths),
        "avg_assists": safe_avg(assists),
        "kda_ratio": format_kda(total_kills, total_deaths, total_assists),
        "avg_cs": safe_avg(cs),
        "avg_cs_per_min": safe_avg(cs_per_min),
        "avg_vision_score": safe_avg(vision_score),
        "avg_vision_score_per_min": safe_avg(vision_score_per_min),
    }

def group_by_champion(rows):
    grouped = defaultdict(list)

    for r in rows:
        grouped[champion_name_ja(r["champion"])].append(r)

    summaries = []

    for champion, champion_rows in grouped.items():
        total = len(champion_rows)
        wins = sum(1 for r in champion_rows if is_win(r["win"]))
        losses = total - wins

        kills = [to_int(r["kills"]) for r in champion_rows]
        deaths = [to_int(r["deaths"]) for r in champion_rows]
        assists = [to_int(r["assists"]) for r in champion_rows]
        vision_score = [to_float(r["vision_score"]) for r in champion_rows]
        vision_score_per_min = [to_float(r["vision_score_per_min"]) for r in champion_rows]
        cs_per_min = [to_float(r["cs_per_min"]) for r in champion_rows]

        total_kills = sum(kills)
        total_deaths = sum(deaths)
        total_assists = sum(assists)

        summaries.append({
            "champion": champion,
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total else 0,
            "avg_kills": safe_avg(kills),
            "avg_deaths": safe_avg(deaths),
            "avg_assists": safe_avg(assists),
            "kda_ratio": format_kda(total_kills, total_deaths, total_assists),
            "avg_vision_score": safe_avg(vision_score),
            "avg_vision_score_per_min": safe_avg(vision_score_per_min),
            "avg_cs_per_min": safe_avg(cs_per_min),
        })

    summaries.sort(key=lambda x: (x["total"], x["win_rate"]), reverse=True)
    return summaries

def filter_support_rows(rows):
    return [r for r in rows if r["role"] == "UTILITY"]
ROLE_NAME_MAP = {
    "TOP": "TOP",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
    "UTILITY": "SUP",
    "": "",
    None: "",
}

def group_by_queue(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[queue_id_to_name(r["queue_id"])].append(r)
    summaries = []
    for queue, queue_rows in grouped.items():
        total = len(queue_rows)
        wins = sum(1 for r in queue_rows if is_win(r["win"]))
        losses = total - wins
        kills = [to_int(r["kills"]) for r in queue_rows]
        deaths = [to_int(r["deaths"]) for r in queue_rows]
        assists = [to_int(r["assists"]) for r in queue_rows]
        vision_score = [to_float(r["vision_score"]) for r in queue_rows]
        vision_score_per_min = [to_float(r["vision_score_per_min"]) for r in queue_rows]
        cs_per_min = [to_float(r["cs_per_min"]) for r in queue_rows]
        total_kills = sum(kills)
        total_deaths = sum(deaths)
        total_assists = sum(assists)
        summaries.append({
            "queue": queue,
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total else 0,
            "avg_kills": safe_avg(kills),
            "avg_deaths": safe_avg(deaths),
            "avg_assists": safe_avg(assists),
            "kda_ratio": format_kda(total_kills, total_deaths, total_assists),
            "avg_vision_score": safe_avg(vision_score),
            "avg_vision_score_per_min": safe_avg(vision_score_per_min),
            "avg_cs_per_min": safe_avg(cs_per_min),
        })
    queue_order = {"ランク": 0, "ドラフト": 1, "フレックス": 2, "ARAM": 3, "アリーナ": 4}
    summaries.sort(key=lambda x: (queue_order.get(x["queue"], 99), -x["total"]))
    return summaries

def role_to_name(role):
    return ROLE_NAME_MAP.get(role, role)
def group_by_role(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[role_to_name(r["role"])].append(r)
    summaries = []
    for role, role_rows in grouped.items():
        total = len(role_rows)
        wins = sum(1 for r in role_rows if is_win(r["win"]))
        losses = total - wins
        kills = [to_int(r["kills"]) for r in role_rows]
        deaths = [to_int(r["deaths"]) for r in role_rows]
        assists = [to_int(r["assists"]) for r in role_rows]
        vision_score = [to_float(r["vision_score"]) for r in role_rows]
        vision_score_per_min = [to_float(r["vision_score_per_min"]) for r in role_rows]
        cs_per_min = [to_float(r["cs_per_min"]) for r in role_rows]
        total_kills = sum(kills)
        total_deaths = sum(deaths)
        total_assists = sum(assists)
        summaries.append({
            "role": role,
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total else 0,
            "avg_kills": safe_avg(kills),
            "avg_deaths": safe_avg(deaths),
            "avg_assists": safe_avg(assists),
            "kda_ratio": format_kda(total_kills, total_deaths, total_assists),
            "avg_vision_score": safe_avg(vision_score),
            "avg_vision_score_per_min": safe_avg(vision_score_per_min),
            "avg_cs_per_min": safe_avg(cs_per_min),
        })
    role_order = {"SUP": 0, "ADC": 1, "JG": 2, "MID": 3, "TOP": 4}
    summaries.sort(key=lambda x: (role_order.get(x["role"], 99), -x["total"]))
    return summaries

def build_summary_text(rows):
    overall = summarize_overall(rows)
    champion_summaries = group_by_champion(rows)
    role_summaries = group_by_role(rows)
    queue_summaries = group_by_queue(rows)
    support_rows = filter_support_rows(rows)
    support_overall = summarize_overall(support_rows) if support_rows else None
    support_champion_summaries = group_by_champion(support_rows) if support_rows else []
    support_queue_summaries = group_by_queue(support_rows) if support_rows else []
    start_date, end_date = get_date_range(rows)

    lines = []

    lines.append("LoL SUP Gold Project Summary")
    if start_date and end_date:
        lines.append(f"対象期間：{start_date} ～ {end_date}")
    lines.append("")
    lines.append("■ 全体成績")
    lines.append(f"対象試合数：{overall['total']}戦")
    lines.append(f"勝敗：{overall['wins']}勝 {overall['losses']}敗")
    lines.append(f"勝率：{format_percent(overall['win_rate'])}")
    lines.append(
        f"平均KDA：{overall['avg_kills']:.1f} / {overall['avg_deaths']:.1f} / {overall['avg_assists']:.1f}"
    )
    lines.append(f"KDA Ratio：{overall['kda_ratio']}")
    lines.append(f"平均CS：{overall['avg_cs']:.1f}")
    lines.append(f"平均CS/m：{overall['avg_cs_per_min']:.1f}")
    lines.append(f"平均VS：{overall['avg_vision_score']:.1f}")
    lines.append(f"平均VS/m：{overall['avg_vision_score_per_min']:.2f}")
    lines.append("")

    if support_overall:
        lines.append("■ SUP成績")
        lines.append(f"対象試合数：{support_overall['total']}戦")
        lines.append(f"勝敗：{support_overall['wins']}勝 {support_overall['losses']}敗")
        lines.append(f"勝率：{format_percent(support_overall['win_rate'])}")
        lines.append(
            f"平均KDA：{support_overall['avg_kills']:.1f} / {support_overall['avg_deaths']:.1f} / {support_overall['avg_assists']:.1f}"
        )
        lines.append(f"KDA Ratio：{support_overall['kda_ratio']}")
        lines.append(f"平均CS：{support_overall['avg_cs']:.1f}")
        lines.append(f"平均CS/m：{support_overall['avg_cs_per_min']:.1f}")
        lines.append(f"平均VS：{support_overall['avg_vision_score']:.1f}")
        lines.append(f"平均VS/m：{support_overall['avg_vision_score_per_min']:.2f}")
        lines.append("")
    lines.append("■ ロール別成績")
    for s in role_summaries:
        lines.append(
            f"{s['role']}：{s['total']}戦 {s['wins']}勝{s['losses']}敗 "
            f"勝率{format_percent(s['win_rate'])} / "
            f"平均KDA {s['avg_kills']:.1f}/{s['avg_deaths']:.1f}/{s['avg_assists']:.1f} "
            f"/ KDA {s['kda_ratio']} / "
            f"平均CS/m {s['avg_cs_per_min']:.1f} / "
            f"平均VS {s['avg_vision_score']:.1f} / VS/m {s['avg_vision_score_per_min']:.2f}"
        )
    lines.append("")

    lines.append("■ キュー別成績")
    for s in queue_summaries:
        lines.append(
            f"{s['queue']}：{s['total']}戦 {s['wins']}勝{s['losses']}敗 "
            f"勝率{format_percent(s['win_rate'])} / "
            f"平均KDA {s['avg_kills']:.1f}/{s['avg_deaths']:.1f}/{s['avg_assists']:.1f} "
            f"/ KDA {s['kda_ratio']} / "
            f"平均CS/m {s['avg_cs_per_min']:.1f} / "
            f"平均VS {s['avg_vision_score']:.1f} / VS/m {s['avg_vision_score_per_min']:.2f}"
        )
    lines.append("")
    if support_queue_summaries:
        lines.append("■ SUPキュー別成績")
        for s in support_queue_summaries:
            lines.append(
                f"{s['queue']}：{s['total']}戦 {s['wins']}勝{s['losses']}敗 "
                f"勝率{format_percent(s['win_rate'])} / "
                f"平均KDA {s['avg_kills']:.1f}/{s['avg_deaths']:.1f}/{s['avg_assists']:.1f} "
                f"/ KDA {s['kda_ratio']} / "
                f"平均CS/m {s['avg_cs_per_min']:.1f} / "
                f"平均VS {s['avg_vision_score']:.1f} / VS/m {s['avg_vision_score_per_min']:.2f}"
            )
        lines.append("")

    lines.append("■ チャンピオン別")
    for s in champion_summaries:
        lines.append(
            f"{s['champion']}：{s['total']}戦 {s['wins']}勝{s['losses']}敗 "
            f"勝率{format_percent(s['win_rate'])} / "
            f"平均KDA {s['avg_kills']:.1f}/{s['avg_deaths']:.1f}/{s['avg_assists']:.1f} "
            f"/ KDA {s['kda_ratio']} / "
            f"平均VS {s['avg_vision_score']:.1f} / VS/m {s['avg_vision_score_per_min']:.2f}"
        )
    lines.append("")

    if support_champion_summaries:
        lines.append("■ SUPチャンピオン別")
        for s in support_champion_summaries:
            lines.append(
                f"{s['champion']}：{s['total']}戦 {s['wins']}勝{s['losses']}敗 "
                f"勝率{format_percent(s['win_rate'])} / "
                f"平均KDA {s['avg_kills']:.1f}/{s['avg_deaths']:.1f}/{s['avg_assists']:.1f} "
                f"/ KDA {s['kda_ratio']} / "
                f"平均VS {s['avg_vision_score']:.1f} / VS/m {s['avg_vision_score_per_min']:.2f}"
            )

    return "\n".join(lines)

def export_summary(
    my_matches_csv_path=MY_MATCHES_CSV_PATH,
    summary_txt_path=SUMMARY_TXT_PATH,
):
    rows = load_my_matches(my_matches_csv_path)

    if not rows:
        print("summary.txtを作成できませんでした")
        return

    text = build_summary_text(rows)

    os.makedirs(os.path.dirname(summary_txt_path), exist_ok=True)

    with open(summary_txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"summary.txt 出力完了: {len(rows)} 件")
