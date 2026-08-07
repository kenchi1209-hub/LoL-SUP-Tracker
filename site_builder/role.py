"""ロール詳細ページの共通プレースホルダを生成する。"""

import json
from collections import Counter

from champion_map import CHAMPION_JA_MAP
from site_builder.render import NAV_STYLES, esc, render_navigation


ROLE_PAGES = (
    ("support", "SUP", "UTILITY", "support.html"),
    ("mid", "MID", "MIDDLE", "mid.html"),
    ("top", "TOP", "TOP", "top.html"),
    ("adc", "ADC", "BOTTOM", "adc.html"),
    ("jungle", "JG", "JUNGLE", "jungle.html"),
)


ROLE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title} · LoL 実績</title>
<style>
  :root {{
    --bg: #0f1420; --panel: #171d2b; --panel2: #1e2635; --border: #2a3346;
    --text: #e7ecf4; --muted: #8a94a7; --accent: #5b8cff;
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
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; margin-bottom: 24px;
  }}
  .hero h1 {{ margin: 0; font-size: 1.7rem; }}
  .role-placeholder {{
    border: 1px solid var(--border); border-radius: 12px; padding: 24px;
    background: var(--panel);
  }}
  .role-placeholder h2 {{ margin: 0 0 12px; }}
  .filters {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 14px; margin: 20px 0;
  }}
  .filter-field {{ display: flex; flex-direction: column; gap: 6px; }}
  .filter-field label {{ color: var(--muted); font-size: .78rem; }}
  .filter-field select, .filter-field input {{
    width: 100%; color: var(--text); background: var(--panel2);
    border: 1px solid var(--border); border-radius: 8px; padding: 9px 10px;
    font: inherit;
  }}
  .custom-period {{
    display: grid; grid-template-columns: repeat(2, minmax(130px, 1fr));
    gap: 14px; grid-column: 1 / -1;
  }}
  .custom-period[hidden] {{ display: none; }}
  .filter-result {{ margin: 16px 0; color: var(--muted); }}
  .filter-result strong {{ color: var(--text); font-size: 1.2rem; }}
  .overview {{ margin: 28px 0; }}
  .overview h2 {{ margin: 0 0 14px; }}
  .cards {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
  }}
  .card {{
    background: var(--panel2); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 16px;
  }}
  .stat-label {{ color: var(--muted); font-size: .78rem; margin-bottom: 6px; }}
  .stat-value {{ font-size: 1.35rem; font-weight: 700; }}
  .stat-sub {{ color: var(--muted); font-size: .78rem; margin-top: 4px; }}
  .good {{ color: #38d39f; }}
  .bad {{ color: #ff6b81; }}
{navigation_styles}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero"><h1>{page_title}</h1></header>
    {navigation}
    <main class="role-placeholder">
      <h2>対象ロール: {role_name}</h2>
      <div class="filters" aria-label="試合フィルター">
        <div class="filter-field">
          <label for="period-filter">期間</label>
          <select id="period-filter">
            <option value="season">シーズン</option>
            <option value="two_months">直近2か月</option>
            <option value="current_month">今月</option>
            <option value="previous_month">前月</option>
            <option value="recent20">直近20戦</option>
            <option value="custom">カスタム期間</option>
          </select>
        </div>
        <div class="filter-field">
          <label for="champ-filter">チャンピオン</label>
          <select id="champ-filter">
            <option value="ALL">ALL</option>
            {champion_options}
          </select>
        </div>
        <div class="filter-field">
          <label for="queue-filter">キュー</label>
          <select id="queue-filter">
            <option value="all">全体（ドラフト＋ランク）</option>
            <option value="ranked">ランク</option>
            <option value="draft">ドラフト</option>
          </select>
        </div>
        <div id="custom-period" class="custom-period" hidden>
          <div class="filter-field">
            <label for="custom-start">開始日</label>
            <input id="custom-start" type="date">
          </div>
          <div class="filter-field">
            <label for="custom-end">終了日</label>
            <input id="custom-end" type="date">
          </div>
        </div>
      </div>
      <p class="filter-result">対象試合数: <strong id="filtered-match-count">{match_count}</strong></p>
      <section class="overview" aria-labelledby="overview-heading">
        <h2 id="overview-heading">Overview</h2>
        <div class="cards">
          <div class="card">
            <div class="stat-label">試合数</div>
            <div class="stat-value" data-overview="games">0戦</div>
          </div>
          <div class="card">
            <div class="stat-label">勝率</div>
            <div class="stat-value" data-overview="winrate">-</div>
            <div class="stat-sub" data-overview="record">0勝 0敗</div>
          </div>
          <div class="card">
            <div class="stat-label">平均K / D / A</div>
            <div class="stat-value" data-overview="avg-kda">-</div>
          </div>
          <div class="card">
            <div class="stat-label">KDA</div>
            <div class="stat-value" data-overview="kda">-</div>
          </div>
          <div class="card">
            <div class="stat-label">CS/m</div>
            <div class="stat-value" data-overview="cspm">-</div>
          </div>
          <div class="card">
            <div class="stat-label">VS/m</div>
            <div class="stat-value" data-overview="vspm">-</div>
          </div>
          <div class="card">
            <div class="stat-label">平均ゲーム時間</div>
            <div class="stat-value" data-overview="duration">-</div>
          </div>
        </div>
      </section>
      <section class="overview role-overview" data-role-overview="{role_code}">
        <h2>Overview - {role_name}</h2>
        <div id="role-overview-cards" class="cards"></div>
      </section>
      <a href="index.html">TOPへ戻る</a>
    </main>
  </div>
  <script id="role-match-data" type="application/json" data-role="{role_code}">{match_data}</script>
  <script src="assets/role-filter.js" defer></script>
  <script src="assets/role-metrics.js" defer></script>
  <script src="assets/role-overview.js" defer></script>
  <script src="assets/role-specific-overview.js" defer></script>
</body>
</html>
"""


def champion_options(rows):
    counts = Counter(row.get("champion", "") for row in rows)
    champions = sorted(counts, key=lambda champion: (-counts[champion], champion))
    return "".join(
        f'<option value="{esc(champion)}">'
        f'{esc(CHAMPION_JA_MAP.get(champion, champion))} ({counts[champion]})'
        "</option>"
        for champion in champions
        if champion
    )


def role_match_data(rows):
    matches = [
        {
            "date": row.get("date", ""),
            "champion": row.get("champion", ""),
            "queue_id": str(row.get("queue_id", "")),
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


def build_role_html(page_id, role_name, role_code, rows):
    page_title = f"{role_name} 詳細"
    role_rows = [
        row
        for row in rows
        if row.get("role") == role_code
        and str(row.get("queue_id", "")) in {"400", "420"}
    ]
    return ROLE_PAGE_TEMPLATE.format(
        page_title=esc(page_title),
        role_name=esc(role_name),
        navigation=render_navigation(page_id),
        navigation_styles=NAV_STYLES,
        champion_options=champion_options(role_rows),
        match_count=len(role_rows),
        match_data=role_match_data(role_rows),
        role_code=esc(role_code),
    )


def build_role_pages(rows):
    return {
        filename: build_role_html(page_id, role_name, role_code, rows)
        for page_id, role_name, role_code, filename in ROLE_PAGES
    }
