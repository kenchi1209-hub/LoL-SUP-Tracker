"""my_matches.csv から GitHub Pages 用の静的サイト (public/) を生成する。

Riot APIには一切アクセスしない純粋なビルド処理。
data/csv/my_matches.csv を読み、Pythonで集計してから
自己完結した public/index.html を書き出す（チャンピオンアイコンのみ
Data Dragon CDN を参照）。
"""
import csv
import html
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from champion_map import CHAMPION_JA_MAP
from queue_map import queue_id_to_name

MATCHES_CSV = "data/csv/my_matches.csv"
LAST_UPDATED_TXT = "data/csv/last_updated.txt"
CURRENT_RANK_JSON = "data/csv/current_rank.json"
OUT_DIR = "public"

JST = timezone(timedelta(hours=9))

# 内部ロール名 -> 表示名
ROLE_LABEL = {
    "UTILITY": "SUP",
    "BOTTOM": "ADC",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "TOP": "TOP",
}
ROLE_ORDER = ["UTILITY", "MIDDLE", "BOTTOM", "JUNGLE", "TOP"]

DDRAGON_FALLBACK_VERSION = "15.13.1"


def get_ddragon_version():
    """Data Dragon の最新バージョンを取得（失敗時は固定値）。"""
    try:
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        with urllib.request.urlopen(url, timeout=10) as res:
            versions = json.load(res)
            if versions:
                return versions[0]
    except Exception as e:  # noqa: BLE001
        print(f"ddragonバージョン取得に失敗、固定値を使用します: {e}")
    return DDRAGON_FALLBACK_VERSION


def champ_icon_id(champion):
    """CSV上の英語チャンピオン名を Data Dragon の画像ID表記に寄せる。"""
    special = {
        "Fiddlesticks": "Fiddlesticks",
        "Wukong": "MonkeyKing",
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


def wr_class(winrate):
    return "good" if winrate >= 50 else "bad"

def is_ranked(row):
    return str(row.get("queue_id", "")) == "420"

def is_support(row):
    return row.get("role") == "UTILITY"

# ---------- HTML 生成 ----------

def esc(s):
    return html.escape(str(s))


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


def table_rows_for_groups(groups, label_fn, sort_key="games"):
    items = []
    for key, grp in groups.items():
        agg = aggregate(grp)
        agg["label"] = label_fn(key)
        agg["_key"] = key
        items.append(agg)
    items.sort(key=lambda x: x[sort_key], reverse=True)
    return items


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
    　　　　f'{esc(rank_name)} <span class="unit">{rank_lp}LP</span>',
    　　　　(
        　　　　f'{current_rank.get("wins", 0)}勝 {current_rank.get("losses", 0)}敗'
        　　　　if current_rank else "ランク情報なし"
   　　　　　),
　　　　　),
    ])

    return (
        '<section class="block"><h2>現在地</h2>'
        f'<div class="cards">{cards}</div></section>'
    )

def build_html(rows, version):
    all_agg = aggregate(rows)

    sup_rows = [r for r in rows if is_support(r)]
    sup_agg = aggregate(sup_rows)

    ranked_rows = [r for r in rows if is_ranked(r)]
    ranked_agg = aggregate(ranked_rows)

    ranked_sup_rows = [r for r in ranked_rows if is_support(r)]
    ranked_sup_agg = aggregate(ranked_sup_rows)

    # ロール別
    role_groups = group_by(rows, lambda r: r.get("role", ""))
    role_items = table_rows_for_groups(role_groups, lambda k: ROLE_LABEL.get(k, k))
    role_items.sort(key=lambda x: ROLE_ORDER.index(x["_key"]) if x["_key"] in ROLE_ORDER else 99)

    # キュー別
    queue_groups = group_by(rows, lambda r: r.get("queue_id", ""))
    queue_items = table_rows_for_groups(queue_groups, lambda k: queue_id_to_name(k))

    # チャンピオン別（3戦以上を上位表示、それ未満はまとめず全部だが試合数順）
    champ_groups = group_by(rows, lambda r: r.get("champion", ""))
    champ_items = table_rows_for_groups(champ_groups, lambda k: k)

    # ランク使用チャンピオン別
    ranked_champ_groups = group_by(ranked_rows, lambda r: r.get("champion", ""))
    ranked_champ_items = table_rows_for_groups(ranked_champ_groups, lambda k: k)

    game_name = os.getenv("RIOT_GAME_NAME", "")
    tag_line = os.getenv("RIOT_TAG_LINE", "")
    player = f"{game_name}#{tag_line}" if game_name else "LoL SUP Tracker"

    latest = rows[0].get("date", "")[:16] if rows else "-"
    data_updated = load_last_updated()
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    parts = [
        render_overview_cards(rows),
        render_form(rows),

        stat_block("全体成績", all_agg),
        stat_block("SUP成績", sup_agg),

        stat_block("ランク全体", ranked_agg),
        stat_block("ランクSUP戦績", ranked_sup_agg),
        render_champion_table(ranked_champ_items, version, "ランク使用チャンピオン別（全ロール）"),

        render_simple_table("ロール別成績", role_items),
        render_simple_table("キュー別成績", queue_items),
        render_champion_table(champ_items, version, "チャンピオン別成績（全ロール）"),
        render_recent(rows, version),
  ]

    return PAGE_TEMPLATE.format(
        player=esc(player),
        latest=esc(latest),
        data_updated=esc(data_updated),
        now=esc(now_jst),
        games=all_agg["games"] if all_agg else 0,
        body="".join(parts),
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
    {body}
    <footer>
      Riot API のデータを基に自動生成 · GitHub Actions + GitHub Pages<br>
      このサイトは Riot Games が承認・後援するものではありません。
    </footer>
  </div>
</body>
</html>
"""


def main():
    rows = load_matches()
    if not rows:
        print("警告: 試合データが空です。プレースホルダを生成します。")
    version = get_ddragon_version()
    print(f"Data Dragon version: {version}")
    os.makedirs(OUT_DIR, exist_ok=True)
    html_out = build_html(rows, version)
    out_path = os.path.join(OUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    # .nojekyll: GitHub Pages の Jekyll 処理を無効化（保険）
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"生成完了: {out_path} ({len(rows)}戦)")


if __name__ == "__main__":
    main()
