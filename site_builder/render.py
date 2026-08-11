"""GitHub Pages 向けの HTML 部品とページテンプレートを扱う。"""

import html
import json
import os
from functools import lru_cache
from pathlib import Path

from champion_map import CHAMPION_JA_MAP
from queue_map import queue_id_to_name
from site_builder.champion_ids import champion_icon_id
from site_builder.data import (
    aggregate,
    format_rank_name,
    is_ranked,
    load_current_rank,
    load_last_updated,
)
from site_builder.patches import normalize_patch
from timezone_utils import now_jst


BASE_DIR = Path(__file__).resolve().parent
FIGHT_DETAILS_PATH = Path("data/csv/fight_details.json")


def load_template(name):
    return (BASE_DIR / "templates" / name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_fight_details():
    try:
        with FIGHT_DETAILS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def load_review_fights(match_id):
    fights = load_fight_details().get(match_id, [])
    if not isinstance(fights, list):
        return []
    return fights


def page_header_context(rows):
    """TOP系ページで共有するヘッダー値を返す。"""
    aggregate_all = aggregate(rows)
    current_rank = load_current_rank()
    game_name = os.getenv("RIOT_GAME_NAME", "")
    tag_line = os.getenv("RIOT_TAG_LINE", "")
    player = f"{game_name}#{tag_line}" if game_name else "LoL SUP Tracker"
    return {
        "player": esc(player),
        "latest": esc(rows[0].get("date", "")[:16] if rows else "-"),
        "data_updated": esc(load_last_updated()),
        "now": esc(now_jst().strftime("%Y-%m-%d %H:%M")),
        "games": aggregate_all["games"] if aggregate_all else 0,
        "rank_name": esc(format_rank_name(current_rank) if current_rank else "-"),
        "rank_lp": esc(current_rank.get("leaguePoints", 0) if current_rank else "-"),
        "rank_record": esc(
            f'{current_rank.get("wins", 0)}勝 {current_rank.get("losses", 0)}敗'
            if current_rank else "-"
        ),
    }


# 内部ロール名 -> 表示名
ROLE_LABEL = {
    "UTILITY": "SUP",
    "BOTTOM": "ADC",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "TOP": "TOP",
}
ROLE_ORDER = ["UTILITY", "MIDDLE", "BOTTOM", "JUNGLE", "TOP"]

STATISTICS_COLGROUP = (
    '<colgroup><col class="col-name"><col class="col-games">'
    '<col class="col-record"><col class="col-winrate">'
    '<col class="col-kda-line"><col class="col-kda">'
    '<col class="col-cspm"><col class="col-vspm">'
    '</colgroup>'
)

NAV_ITEMS = (
    ("overview", "Overview", "index.html"),
    ("support", "SUP", "support.html"),
    ("mid", "MID", "mid.html"),
    ("top", "TOP", "top.html"),
    ("adc", "ADC", "adc.html"),
    ("jungle", "JG", "jungle.html"),
    ("history", "Match History", "history.html"),
)


def match_history_data(rows):
    """TOP/ロール共通Match History用のJSONを生成する。"""
    matches = [
        {
            "match_id": row.get("match_id", ""),
            "date": row.get("date", ""),
            "patch": normalize_patch(row.get("patch", row.get("gameVersion", ""))),
            "champion": row.get("champion", ""),
            "champion_name": CHAMPION_JA_MAP.get(
                row.get("champion", ""), row.get("champion", "")
            ),
            "champion_icon_id": champion_icon_id(row.get("champion", "")),
            "queue_id": str(row.get("queue_id", "")),
            "queue_name": queue_id_to_name(row.get("queue_id", "")),
            "role": row.get("role", ""),
            "win": row.get("_win", False),
            "kills": row.get("_k", 0),
            "deaths": row.get("_d", 0),
            "assists": row.get("_a", 0),
            "cs": row.get("_cs", 0),
            "vision_score": row.get("_vs", 0),
            "wards_placed": row.get("wards_placed", 0),
            "wards_killed": row.get("wards_killed", 0),
            "control_wards_bought": row.get("control_wards_bought", 0),
            "damage_to_champions": row.get("_dmg", 0),
            "team_kills": row.get("team_kills", 0),
            "game_duration_seconds": row.get("game_duration_seconds", 0),
            "my_fights": row.get("my_fights", 0),
            "fight_wins": row.get("fight_wins", 0),
            "fight_evens": row.get("fight_evens", 0),
            "fight_losses": row.get("fight_losses", 0),
            "survived_fights": row.get("survived_fights", 0),
            "died_fights": row.get("died_fights", 0),
            "teamfights": row.get("teamfights", 0),
            "fights": load_review_fights(row.get("match_id", "")),
        }
        for row in rows
    ]
    return json.dumps(matches, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def match_history_champion_options(rows):
    champions = sorted({row.get("champion", "") for row in rows if row.get("champion")})
    return "".join(
        f'<option value="{esc(champion)}">{esc(CHAMPION_JA_MAP.get(champion, champion))}</option>'
        for champion in champions
    )


def render_match_history(rows, version, mode="top"):
    top_controls = ""
    data = ""
    if mode == "top":
        top_controls = f"""
        <div class="match-history-field"><label for="mh-period">期間</label><select id="mh-period">
          <option value="season">シーズン</option><option value="two_months">直近2か月</option>
          <option value="current_month">今月</option><option value="previous_month">前月</option>
          <option value="recent20">直近20戦</option><option value="custom">カスタム期間</option>
        </select></div>
        <div class="match-history-field"><label for="mh-champion">チャンピオン</label><select id="mh-champion"><option value="ALL">ALL</option>{match_history_champion_options(rows)}</select></div>
        <div class="match-history-field"><label for="mh-queue">キュー</label><select id="mh-queue"><option value="all">全体</option><option value="ranked">ランク</option><option value="draft">ドラフト</option></select></div>
        <div class="match-history-field"><label for="mh-role">ロール</label><select id="mh-role"><option value="ALL">ALL</option><option value="UTILITY">SUP</option><option value="MIDDLE">MID</option><option value="TOP">TOP</option><option value="BOTTOM">ADC</option><option value="JUNGLE">JG</option></select></div>
        <div id="mh-custom" class="match-history-custom" hidden>
          <div class="match-history-field"><label for="mh-start">開始日</label><input id="mh-start" type="date"></div>
          <div class="match-history-field"><label for="mh-end">終了日</label><input id="mh-end" type="date"></div>
        </div>"""
        data = f'<script id="match-history-data" type="application/json">{match_history_data(rows)}</script>'
    return load_template("match-history.html").format(
        mode=esc(mode),
        version=esc(version),
        top_controls=top_controls,
        data=data,
    )


def wr_class(winrate):
    return "good" if winrate >= 50 else "bad"


def esc(s):
    return html.escape(str(s))


def render_navigation(active_page):
    links = []
    for page_id, label, href in NAV_ITEMS:
        active = page_id == active_page
        class_name = "nav-link active" if active else "nav-link"
        current = ' aria-current="page"' if active else ""
        links.append(
            f'<a class="{class_name}" href="{href}"{current}>{label}</a>'
        )
    return (
        '<nav class="site-nav" aria-label="サイトナビゲーション">'
        f'{"".join(links)}</nav>'
    )


def stat_card(label, value, sub=""):
    sub_html = f'<div class="stat-sub">{esc(sub)}</div>' if sub else ""
    return (
        '<div class="card">'
        f'<div class="stat-label">{esc(label)}</div>'
        f'<div class="stat-value">{value}</div>'
        f"{sub_html}"
        "</div>"
    )


def stat_block(title, agg):
    if not agg:
        return ""
    wr = agg["winrate"]
    cards = "".join([
        stat_card("総試合数", f'{agg["games"]}<span class="unit">戦</span>'),
        stat_card(
            "勝率",
            f'<span class="{wr_class(wr)}">{wr:.1f}<span class="unit">%</span></span>',
            f'{agg["wins"]}勝 {agg["losses"]}敗',
        ),
        stat_card(
            "平均KDA",
            f'{agg["avg_k"]:.1f} / {agg["avg_d"]:.1f} / {agg["avg_a"]:.1f}',
            f'KDA {agg["kda"]:.2f}',
        ),
        stat_card("平均CS/m", f'{agg["avg_cspm"]:.2f}'),
        stat_card("平均VS/m", f'{agg["avg_vspm"]:.2f}', f'VS {agg["avg_vs"]:.1f}'),
    ])
    return (
        f'<section class="block"><h2>{esc(title)}</h2>'
        f'<div class="cards">{cards}</div></section>'
    )


def render_performance_summary(overall, ranked):
    """TOPの全体・ランク集計を比較表で表示する。"""
    rows = []
    for label, aggregate_result in (("全体", overall), ("ランク", ranked)):
        if not aggregate_result:
            continue
        winrate = aggregate_result["winrate"]
        rows.append(
            '<tr>'
            f'<td class="name">{esc(label)}</td>'
            f'<td class="num">{aggregate_result["games"]}</td>'
            f'<td class="num">{aggregate_result["wins"]}-{aggregate_result["losses"]}</td>'
            f'<td class="wr winrate-column">{wr_bar(winrate)}</td>'
            f'<td class="num kda-column">{aggregate_result["avg_k"]:.1f}/{aggregate_result["avg_d"]:.1f}/{aggregate_result["avg_a"]:.1f}</td>'
            f'<td class="num">{aggregate_result["kda"]:.2f}</td>'
            f'<td class="num">{aggregate_result["avg_cspm"]:.2f}</td>'
            f'<td class="num">{aggregate_result["avg_vspm"]:.2f}</td>'
            '</tr>'
        )
    return (
        '<section class="block performance-summary">'
        '<h2>成績概要</h2>'
        f'<div class="table-wrap statistics-table"><table>{STATISTICS_COLGROUP}'
        '<thead><tr><th>区分</th><th>試合</th><th>勝敗</th><th class="winrate-column">勝率</th><th class="kda-column">K/D/A</th>'
        '<th>KDA</th><th>CS/m</th><th>VS/m</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '</section>'
    )


def wr_bar(winrate):
    cls = wr_class(winrate)
    return (
        '<div class="bar">'
        f'<div class="bar-fill {cls}" style="width:{min(winrate,100):.1f}%"></div>'
        f'<span class="bar-text">{winrate:.1f}%</span>'
        "</div>"
    )


def render_simple_table(title, items):
    body = ""
    for it in items:
        body += (
            "<tr>"
            f'<td class="name">{esc(it["label"])}</td>'
            f'<td class="num">{it["games"]}</td>'
            f'<td class="num">{it["wins"]}-{it["losses"]}</td>'
            f'<td class="wr winrate-column">{wr_bar(it["winrate"])}</td>'
            f'<td class="num kda-column">{it["avg_k"]:.1f}/{it["avg_d"]:.1f}/{it["avg_a"]:.1f}</td>'
            f'<td class="num">{it["kda"]:.2f}</td>'
            f'<td class="num">{it["avg_cspm"]:.2f}</td>'
            f'<td class="num">{it["avg_vspm"]:.2f}</td>'
            "</tr>"
        )
    return (
        f'<section class="block"><h2>{esc(title)}</h2>'
        f'<div class="table-wrap statistics-table"><table>{STATISTICS_COLGROUP}'
        "<thead><tr>"
        "<th>区分</th><th>試合</th><th>勝敗</th><th class=\"winrate-column\">勝率</th>"
        "<th class=\"kda-column\">K/D/A</th><th>KDA</th><th>CS/m</th><th>VS/m</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table></div></section>"
    )


def render_champion_table(items, version, title="チャンピオン別"):
    if not items:
        return ""

    body = ""
    for it in items:
        champ = it["_key"]
        ja = CHAMPION_JA_MAP.get(champ, champ)
        icon = (
            f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/"
            f"{champion_icon_id(champ)}.png"
        )
        body += (
            "<tr>"
            '<td class="name champ">'
            f'<img loading="lazy" src="{esc(icon)}" alt="" '
            f'onerror="this.style.display=\'none\'">'
            f'<span>{esc(ja)}</span></td>'
            f'<td class="num">{it["games"]}</td>'
            f'<td class="num">{it["wins"]}-{it["losses"]}</td>'
            f'<td class="wr winrate-column">{wr_bar(it["winrate"])}</td>'
            f'<td class="num kda-column">{it["avg_k"]:.1f}/{it["avg_d"]:.1f}/{it["avg_a"]:.1f}</td>'
            f'<td class="num">{it["kda"]:.2f}</td>'
            f'<td class="num">{it["avg_cspm"]:.2f}</td>'
            f'<td class="num">{it["avg_vspm"]:.2f}</td>'
            "</tr>"
        )
    return (
        f'<section class="block"><h2>{esc(title)}</h2>'
        f'<div class="table-wrap statistics-table"><table>{STATISTICS_COLGROUP}'
        "<thead><tr>"
        "<th>チャンピオン</th><th>試合</th><th>勝敗</th><th class=\"winrate-column\">勝率</th>"
        "<th class=\"kda-column\">K/D/A</th><th>KDA</th><th>CS/m</th><th>VS/m</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table></div></section>"
    )


def render_form(rows, limit=20):
    """直近の勝敗をドットで表示（新しい順を左→右で古い→新しいに並べ替え）。"""
    recent = rows[:limit][::-1]
    dots = ""
    for r in recent:
        cls = "win" if r["_win"] else "loss"
        dots += f'<span class="dot {cls}"></span>'
    w = sum(1 for r in recent if r["_win"])
    return (
        '<section class="block"><h2>直近フォーム'
        f'<span class="form-sub">直近{len(recent)}戦 {w}勝{len(recent)-w}敗</span></h2>'
        f'<div class="form">{dots}</div></section>'
    )


def render_overview_cards(rows):
    """ページ上部の現在地カード。"""
    agg = aggregate(rows)
    if not agg:
        return ""

    ranked_rows = [r for r in rows if is_ranked(r)]
    ranked_agg = aggregate(ranked_rows)

    current_rank = load_current_rank()
    rank_name = format_rank_name(current_rank)
    rank_lp = current_rank.get("leaguePoints", 0) if current_rank else 0

    recent = rows[:20]
    recent_agg = aggregate(recent)
    recent_wins = recent_agg["wins"] if recent_agg else 0
    recent_losses = recent_agg["losses"] if recent_agg else 0
    recent_kda = recent_agg["kda"] if recent_agg else 0
    recent_vspm = recent_agg["avg_vspm"] if recent_agg else 0


    wr = agg["winrate"]

    cards = "".join([
        stat_card(
            "分析対象戦数",
            f'{agg["games"]}<span class="unit">戦</span>',
            "ドラフト / ランク・リメイク除外",
        ),
        stat_card(
            "全体成績",
            f'<span class="{wr_class(wr)}">{wr:.1f}<span class="unit">%</span></span>',
            f'{agg["wins"]}勝 {agg["losses"]}敗',
        ),
        stat_card(
            "直近20戦",
            f'{recent_wins}勝 {recent_losses}敗',
            f'KDA {recent_kda:.2f} / VS/m {recent_vspm:.2f}',
        ),
        stat_card(
           "ランク勝率",
           (
                f'<span class="{wr_class(ranked_agg["winrate"])}">'
                f'{ranked_agg["winrate"]:.1f}<span class="unit">%</span></span>'
                if ranked_agg else "-"
           ),
           (
                f'{ranked_agg["wins"]}勝 {ranked_agg["losses"]}敗'
                if ranked_agg else "ランク戦なし"
           ),
        ),
        stat_card(
            "現在ランク",
            f'{esc(rank_name)}',
            (
                f'{rank_lp}LP / '
                f'{current_rank.get("wins", 0)}勝 '
                f'{current_rank.get("losses", 0)}敗'
                if current_rank else "ランク情報なし"
            ),
        ),
    ])

    return (
        '<section class="block"><h2>現在地</h2>'
        f'<div class="cards">{cards}</div></section>'
    )


PAGE_TEMPLATE = load_template("top.html")
