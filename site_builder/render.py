"""GitHub Pages 向けの HTML 部品とページテンプレートを扱う。"""

import html
import json

from champion_map import CHAMPION_JA_MAP
from queue_map import queue_id_to_name
from site_builder.data import (
    aggregate,
    format_rank_name,
    is_ranked,
    load_current_rank,
    seconds_to_mmss,
)


# 内部ロール名 -> 表示名
ROLE_LABEL = {
    "UTILITY": "SUP",
    "BOTTOM": "ADC",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "TOP": "TOP",
}
ROLE_ORDER = ["UTILITY", "MIDDLE", "BOTTOM", "JUNGLE", "TOP"]

NAV_ITEMS = (
    ("overview", "Overview", "index.html"),
    ("support", "SUP", "support.html"),
    ("mid", "MID", "mid.html"),
    ("top", "TOP", "top.html"),
    ("adc", "ADC", "adc.html"),
    ("jungle", "JG", "jungle.html"),
)

NAV_STYLES = """/* navigation */
.site-nav {
  display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 24px;
}
.site-nav a {
  color: var(--muted); text-decoration: none; border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 12px; font-size: .84rem;
}
.site-nav a:hover { color: var(--text); border-color: var(--accent); }
.site-nav a.active {
  color: var(--text); background: var(--panel2); border-color: var(--accent);
}
/* /navigation */"""

MATCH_HISTORY_STYLES = """/* shared match history */
.match-history-controls {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 10px; margin-bottom: 14px;
}
.match-history-field { display: flex; flex-direction: column; gap: 5px; }
.match-history-field label { color: var(--muted); font-size: .75rem; }
.match-history-field select, .match-history-field input {
  width: 100%; color: var(--text); background: var(--panel2);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 9px; font: inherit;
}
.match-history-custom { display: contents; }
.match-history-custom[hidden] { display: none; }
.match-history-summary { color: var(--muted); font-size: .82rem; margin: 0 0 10px; }
.matches { display: flex; flex-direction: column; gap: 8px; }
.match {
  display: grid; grid-template-columns: 56px minmax(170px,1.4fr) minmax(105px,.7fr) minmax(250px,1.7fr) minmax(145px,.9fr);
  align-items: center; gap: 10px; background: var(--panel); border: 1px solid var(--border);
  border-left-width: 4px; border-radius: 10px; padding: 10px 12px;
}
.match.win { border-left-color: var(--good, #38d39f); }
.match.loss { border-left-color: var(--bad, #ff6b81); }
.m-result { font-weight: 700; font-size: .78rem; }
.match.win .m-result { color: var(--good, #38d39f); }
.match.loss .m-result { color: var(--bad, #ff6b81); }
.m-champ { display: flex; align-items: center; gap: 8px; }
.m-champ img { width: 34px; height: 34px; border-radius: 7px; }
.m-champ-name, .m-kda { font-weight: 600; }
.m-meta, .m-stats, .m-date { color: var(--muted); font-size: .78rem; }
.m-stats { line-height: 1.5; }
.m-date { text-align: right; }
.match-history-empty { color: var(--muted); padding: 24px; text-align: center; }
.match-history-more {
  display: block; margin: 14px auto 0; padding: 8px 18px; color: var(--text);
  background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; cursor: pointer;
}
.match-history-more[hidden], .match-history-empty[hidden] { display: none; }
@media (max-width: 760px) {
  .match { grid-template-columns: 48px 1.4fr 1fr; row-gap: 4px; }
  .m-stats, .m-date { grid-column: 2 / -1; text-align: left; }
}
/* /shared match history */"""


def champ_icon_id(champion):
    """CSV上の英語チャンピオン名を Data Dragon の画像ID表記に寄せる。"""
    special = {
        "Fiddlesticks": "Fiddlesticks",
        "Wukong": "MonkeyKing",
        "Kai'Sa": "Kaisa",
        "Vel'Koz": "Velkoz",
        "Cho'Gath": "Chogath",
    }
    if champion in special:
        return special[champion]
    # Vel'Koz -> Velkoz, Kai'Sa -> Kaisa, Cho'Gath -> Chogath 等
    return (
        champion.replace("'", "")
        .replace(".", "")
        .replace(" ", "")
        .replace("&", "")
    )


def match_history_data(rows):
    """TOP/ロール共通Match History用のJSONを生成する。"""
    matches = [
        {
            "match_id": row.get("match_id", ""),
            "date": row.get("date", ""),
            "patch": row.get("patch", row.get("gameVersion", "")),
            "champion": row.get("champion", ""),
            "champion_name": CHAMPION_JA_MAP.get(
                row.get("champion", ""), row.get("champion", "")
            ),
            "champion_icon_id": champ_icon_id(row.get("champion", "")),
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
    return f"""
    <section class="block match-history" data-match-history-mode="{mode}" data-ddragon-version="{esc(version)}">
      <h2>Match History</h2>
      <div class="match-history-controls">
        {top_controls}
        <div class="match-history-field"><label for="mh-result-{mode}">勝敗</label><select id="mh-result-{mode}" data-match-history-result><option value="ALL">ALL</option><option value="WIN">WIN</option><option value="LOSS">LOSS</option></select></div>
        <div class="match-history-field"><label for="mh-sort-{mode}">並び順</label><select id="mh-sort-{mode}" data-match-history-sort></select></div>
        <div class="match-history-field"><label for="mh-direction-{mode}">方向</label><select id="mh-direction-{mode}" data-match-history-direction><option value="desc">降順</option><option value="asc">昇順</option></select></div>
      </div>
      <p class="match-history-summary" data-match-history-summary></p>
      <div class="matches" data-match-history-list></div>
      <div class="match-history-empty" data-match-history-empty hidden>条件に一致する試合がありません</div>
      <button class="match-history-more" type="button" data-match-history-more hidden>さらに20件表示</button>
    </section>
    {data}
    <script src="assets/match-history-metrics.js" defer></script>
    <script src="assets/match-history.js" defer></script>"""


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
            f'<td class="wr">{wr_bar(it["winrate"])}</td>'
            f'<td class="num">{it["avg_k"]:.1f}/{it["avg_d"]:.1f}/{it["avg_a"]:.1f}</td>'
            f'<td class="num">{it["kda"]:.2f}</td>'
            f'<td class="num">{it["avg_vspm"]:.2f}</td>'
            "</tr>"
        )
    return (
        f'<section class="block"><h2>{esc(title)}</h2>'
        '<div class="table-wrap"><table>'
        "<thead><tr>"
        "<th>区分</th><th>試合</th><th>勝敗</th><th>勝率</th>"
        "<th>平均KDA</th><th>KDA</th><th>VS/m</th>"
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
            f"{champ_icon_id(champ)}.png"
        )
        body += (
            "<tr>"
            '<td class="name champ">'
            f'<img loading="lazy" src="{esc(icon)}" alt="" '
            f'onerror="this.style.display=\'none\'">'
            f'<span>{esc(ja)}</span></td>'
            f'<td class="num">{it["games"]}</td>'
            f'<td class="num">{it["wins"]}-{it["losses"]}</td>'
            f'<td class="wr">{wr_bar(it["winrate"])}</td>'
            f'<td class="num">{it["avg_k"]:.1f}/{it["avg_d"]:.1f}/{it["avg_a"]:.1f}</td>'
            f'<td class="num">{it["kda"]:.2f}</td>'
            f'<td class="num">{it["avg_vspm"]:.2f}</td>'
            "</tr>"
        )
    return (
        f'<section class="block"><h2>{esc(title)}</h2>'
        '<div class="table-wrap"><table>'
        "<thead><tr>"
        "<th>チャンピオン</th><th>試合</th><th>勝敗</th><th>勝率</th>"
        "<th>平均KDA</th><th>KDA</th><th>VS/m</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table></div></section>"
    )


def render_recent(rows, version, limit=20):
    body = ""
    for r in rows[:limit]:
        champ = r.get("champion", "")
        ja = CHAMPION_JA_MAP.get(champ, champ)
        icon = (
            f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/"
            f"{champ_icon_id(champ)}.png"
        )
        win = r["_win"]
        result_cls = "win" if win else "loss"
        result_txt = "WIN" if win else "LOSS"
        role = ROLE_LABEL.get(r.get("role", ""), r.get("role", ""))
        queue = queue_id_to_name(r.get("queue_id", ""))
        date = r.get("date", "")[:16]
        duration = seconds_to_mmss(r.get("game_duration_seconds"))
        body += (
            f'<div class="match {result_cls}">'
            f'<div class="m-result">{result_txt}</div>'
            '<div class="m-champ">'
            f'<img loading="lazy" src="{esc(icon)}" alt="" '
            f'onerror="this.style.display=\'none\'">'
            f'<div><div class="m-champ-name">{esc(ja)}</div>'
            f'<div class="m-meta">{esc(role)} · {esc(queue)}</div></div></div>'
            f'<div class="m-kda">{r["_k"]} / {r["_d"]} / {r["_a"]}</div>'
            f'<div class="m-stats">'
            f'CS {int(r["_cs"])} ({r["_cspm"]:.1f}/m) · '
            f'VS {int(r["_vs"])} ({r["_vspm"]:.2f}/m) · '
            f'Time {duration}'f'</div>'
            f'<div class="m-date">{esc(date)}</div>'
            "</div>"
        )
    return (
        '<section class="block"><h2>最近の試合</h2>'
        f'<div class="matches">{body}</div></section>'
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


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{player} · LoL 実績</title>
<style>
  :root {{
    --bg: #0f1420; --panel: #171d2b; --panel2: #1e2635; --border: #2a3346;
    --text: #e7ecf4; --muted: #8a94a7; --accent: #5b8cff;
    --good: #38d39f; --bad: #ff6b81; --gold: #f0b429;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
      "Noto Sans JP", Meiryo, sans-serif; line-height: 1.5;
  }}
  a {{ color: var(--accent); }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 24px 16px 64px; }}
  header.hero {{
    background: linear-gradient(135deg, #1b2a4a, #131a2b);
    border: 1px solid var(--border); border-radius: 16px;
    padding: 28px 24px; margin-bottom: 24px;
  }}
  .hero h1 {{ margin: 0 0 6px; font-size: 1.7rem; letter-spacing: .3px; }}
  .hero .meta {{ color: var(--muted); font-size: .88rem; }}
  .hero .meta b {{ color: var(--text); font-weight: 600; }}
  h2 {{
    font-size: 1.05rem; margin: 0 0 14px; display: flex; align-items: baseline;
    gap: 10px; color: #cdd6e6;
  }}
  .block {{ margin-bottom: 30px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap: 12px; }}
  .card {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px;
  }}
  .stat-label {{ color: var(--muted); font-size: .78rem; margin-bottom: 6px; }}
  .stat-value {{ font-size: 1.5rem; font-weight: 700; }}
  .stat-value .unit {{ font-size: .8rem; color: var(--muted); font-weight: 500; margin-left: 2px; }}
  .stat-sub {{ color: var(--muted); font-size: .78rem; margin-top: 4px; }}
  .good {{ color: var(--good); }}
  .bad {{ color: var(--bad); }}
  .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; min-width: 560px; }}
  thead th {{
    background: var(--panel2); color: var(--muted); font-weight: 600;
    text-align: right; padding: 10px 12px; white-space: nowrap; font-size: .8rem;
  }}
  thead th:first-child {{ text-align: left; }}
  tbody td {{ padding: 10px 12px; border-top: 1px solid var(--border); text-align: right; }}
  tbody td.name {{ text-align: left; font-weight: 600; }}
  tbody tr:nth-child(even) {{ background: rgba(255,255,255,.015); }}
  td.champ {{ display: flex; align-items: center; gap: 8px; }}
  td.champ img {{ width: 26px; height: 26px; border-radius: 6px; }}
  .bar {{ position: relative; height: 20px; background: var(--panel2); border-radius: 6px; overflow: hidden; min-width: 110px; }}
  .bar-fill {{ position: absolute; left: 0; top: 0; bottom: 0; opacity: .35; }}
  .bar-fill.good {{ background: var(--good); }}
  .bar-fill.bad {{ background: var(--bad); }}
  .bar-text {{ position: relative; display: block; text-align: center; font-size: .8rem; line-height: 20px; }}
  .form {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .dot {{ width: 20px; height: 20px; border-radius: 5px; }}
  .dot.win {{ background: var(--good); }}
  .dot.loss {{ background: var(--bad); }}
  .form-sub {{ color: var(--muted); font-size: .8rem; font-weight: 400; }}
  .matches {{ display: flex; flex-direction: column; gap: 8px; }}
  .match {{
    display: grid; grid-template-columns: 56px 1.6fr 1fr 1.2fr 1fr; align-items: center;
    gap: 10px; background: var(--panel); border: 1px solid var(--border);
    border-left-width: 4px; border-radius: 10px; padding: 10px 12px;
  }}
  .match.win {{ border-left-color: var(--good); }}
  .match.loss {{ border-left-color: var(--bad); }}
  .m-result {{ font-weight: 700; font-size: .78rem; }}
  .match.win .m-result {{ color: var(--good); }}
  .match.loss .m-result {{ color: var(--bad); }}
  .m-champ {{ display: flex; align-items: center; gap: 8px; }}
  .m-champ img {{ width: 34px; height: 34px; border-radius: 7px; }}
  .m-champ-name {{ font-weight: 600; }}
  .m-meta {{ color: var(--muted); font-size: .76rem; }}
  .m-kda {{ font-weight: 600; }}
  .m-stats, .m-date {{ color: var(--muted); font-size: .82rem; }}
  .m-date {{ text-align: right; }}
  footer {{ color: var(--muted); font-size: .78rem; text-align: center; margin-top: 40px; }}
  @media (max-width: 640px) {{
    .match {{ grid-template-columns: 48px 1.4fr 1fr; row-gap: 4px; }}
    .m-stats, .m-date {{ display: none; }}
  }}
{navigation_styles}
{match_history_styles}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <h1>{player}</h1>
      <div class="meta">
        分析対象 <b>{games}</b> 戦 &nbsp;·&nbsp; 最終試合 <b>{latest}</b>
        &nbsp;·&nbsp; データ更新 <b>{data_updated}</b> (JST)
        &nbsp;·&nbsp; サイト更新 <b>{now}</b> (JST)
      </div>
    </header>
    {navigation}
    {body}
    <footer>
      Riot API のデータを基に自動生成 · GitHub Actions + GitHub Pages<br>
      このサイトは Riot Games が承認・後援するものではありません。
    </footer>
  </div>
</body>
</html>
"""
