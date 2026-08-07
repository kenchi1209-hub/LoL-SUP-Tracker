"""ロール詳細ページの共通プレースホルダを生成する。"""

import json
from collections import Counter

from champion_map import CHAMPION_JA_MAP
from site_builder.render import NAV_STYLES, champ_icon_id, esc, render_navigation


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
  .form-panel {{
    margin-top: 12px; padding: 16px; background: var(--panel2);
    border: 1px solid var(--border); border-radius: 12px;
  }}
  .form {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
  .dot {{ width: 20px; height: 20px; border-radius: 5px; }}
  .dot.win {{ background: #38d39f; }}
  .dot.loss {{ background: #ff6b81; }}
  .form-summary {{ color: var(--muted); font-size: .82rem; margin-top: 8px; }}
  .trend-controls {{
    display: grid; grid-template-columns: repeat(2, minmax(150px, 220px));
    gap: 12px; margin-bottom: 12px;
  }}
  .trend-panel {{
    padding: 16px; background: var(--panel2); border: 1px solid var(--border);
    border-radius: 12px;
  }}
  .trend-summary {{ display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 10px; }}
  .trend-summary strong {{ display: block; font-size: 1.2rem; }}
  .trend-chart {{ width: 100%; min-height: 280px; overflow: hidden; }}
  .trend-chart svg {{ display: block; width: 100%; height: auto; }}
  .trend-empty {{
    min-height: 280px; display: grid; place-items: center; color: var(--muted);
  }}
  .neutral {{ color: var(--muted); }}
  .comparison-panel {{
    overflow-x: auto; background: var(--panel2); border: 1px solid var(--border);
    border-radius: 12px;
  }}
  .comparison-counts {{ color: var(--muted); margin: 0 0 10px; }}
  .comparison-table {{ width: 100%; min-width: 560px; border-collapse: collapse; }}
  .comparison-table th, .comparison-table td {{
    padding: 11px 14px; border-bottom: 1px solid var(--border); text-align: right;
    white-space: nowrap;
  }}
  .comparison-table th {{ color: var(--muted); font-size: .78rem; font-weight: 600; }}
  .comparison-table th:first-child, .comparison-table td:first-child {{ text-align: left; }}
  .comparison-table tbody tr:last-child td {{ border-bottom: 0; }}
  .comparison-table td:not(:first-child) {{ font-variant-numeric: tabular-nums; }}
  .patch-table {{ min-width: 900px; }}
  .patch-table .patch-label {{ white-space: normal; min-width: 210px; }}
  .patch-reference {{ background: rgba(246, 200, 95, .07); }}
  .patch-reference .patch-label::after {{
    content: "参考"; display: inline-block; margin-left: 7px; padding: 1px 5px;
    border: 1px solid #f6c85f; border-radius: 4px; color: #f6c85f;
    font-size: .68rem; vertical-align: 1px;
  }}
  .patch-champions {{ display: flex; justify-content: flex-end; gap: 8px; }}
  .patch-champion {{ position: relative; display: inline-flex; }}
  .patch-champion img {{
    width: 34px; height: 34px; border-radius: 7px; border: 1px solid var(--border);
  }}
  .patch-champion-count {{
    position: absolute; right: -4px; bottom: -4px; min-width: 17px; padding: 0 4px;
    border-radius: 8px; background: var(--bg); color: var(--text); font-size: .65rem;
    line-height: 17px; text-align: center; border: 1px solid var(--border);
  }}
  .patch-empty {{ padding: 24px; color: var(--muted); text-align: center; }}
  @media (max-width: 520px) {{
    .trend-controls {{ grid-template-columns: 1fr; }}
  }}
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
      <section class="overview form-streak" aria-labelledby="form-streak-heading">
        <h2 id="form-streak-heading">Form &amp; Streak</h2>
        <div id="form-streak-cards" class="cards"></div>
        <div class="form-panel">
          <div class="stat-label">直近20戦フォーム</div>
          <div id="recent-form" class="form"></div>
          <div id="recent-form-summary" class="form-summary">-</div>
        </div>
      </section>
      <section class="overview performance-trend" aria-labelledby="performance-trend-heading">
        <h2 id="performance-trend-heading">Performance Trend</h2>
        <div class="trend-controls">
          <div class="filter-field">
            <label for="trend-metric">指標</label>
            <select id="trend-metric">
              <option value="winrate">勝率</option>
              <option value="kda">KDA</option>
              <option value="avgDeaths">Death</option>
              <option value="cspm">CS/m</option>
              <option value="vspm">VS/m</option>
              <option value="damagePerMinute">Damage/m</option>
            </select>
          </div>
          <div class="filter-field">
            <label for="trend-grouping">集計</label>
            <select id="trend-grouping">
              <option value="moving5">5試合移動平均</option>
              <option value="moving10">10試合移動平均</option>
              <option value="monthly">月別</option>
            </select>
          </div>
        </div>
        <div class="trend-panel">
          <div class="trend-summary">
            <div><span class="stat-label" id="trend-current-label">現在</span><strong id="trend-current">-</strong></div>
            <div><span class="stat-label">平均との差</span><strong id="trend-difference">-</strong></div>
          </div>
          <div id="trend-chart" class="trend-chart" role="img" aria-label="成績推移"></div>
        </div>
      </section>
      <section class="overview win-loss-comparison" aria-labelledby="win-loss-heading" data-win-loss-role="{role_code}">
        <h2 id="win-loss-heading">Win / Loss Comparison</h2>
        <p id="win-loss-counts" class="comparison-counts">勝利時 0戦 / 敗北時 0戦</p>
        <div class="comparison-panel">
          <table class="comparison-table">
            <thead><tr><th scope="col">指標</th><th scope="col">勝利時</th><th scope="col">敗北時</th><th scope="col">差分</th></tr></thead>
            <tbody id="win-loss-body"></tbody>
          </table>
        </div>
      </section>
      <section class="overview patch-analysis" aria-labelledby="patch-analysis-heading" data-ddragon-version="{ddragon_version}">
        <h2 id="patch-analysis-heading">Patch Analysis</h2>
        <div class="comparison-panel">
          <table class="comparison-table patch-table">
            <thead><tr><th scope="col">Patch</th><th scope="col">Games</th><th scope="col">Winrate</th><th scope="col">KDA</th><th scope="col">CS/m</th><th scope="col">VS/m</th><th scope="col">Damage/m</th><th scope="col">主な使用チャンピオン</th></tr></thead>
            <tbody id="patch-analysis-body"></tbody>
          </table>
          <div id="patch-analysis-empty" class="patch-empty" hidden>対象試合がありません</div>
        </div>
      </section>
      <a href="index.html">TOPへ戻る</a>
    </main>
  </div>
  <script id="role-match-data" type="application/json" data-role="{role_code}">{match_data}</script>
  <script src="assets/role-filter.js" defer></script>
  <script src="assets/role-metrics.js" defer></script>
  <script src="assets/role-overview.js" defer></script>
  <script src="assets/role-specific-overview.js" defer></script>
  <script src="assets/role-streaks.js" defer></script>
  <script src="assets/role-form-streak.js" defer></script>
  <script src="assets/role-trend-metrics.js" defer></script>
  <script src="assets/role-performance-trend.js" defer></script>
  <script src="assets/role-win-loss-metrics.js" defer></script>
  <script src="assets/role-win-loss.js" defer></script>
  <script src="assets/role-patch-metrics.js" defer></script>
  <script src="assets/role-patch-analysis.js" defer></script>
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
            "patch": row.get("patch", row.get("gameVersion", "")),
            "champion": row.get("champion", ""),
            "champion_icon_id": champ_icon_id(row.get("champion", "")),
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


def build_role_html(page_id, role_name, role_code, rows, ddragon_version):
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
        ddragon_version=esc(ddragon_version),
    )


def build_role_pages(rows, ddragon_version):
    return {
        filename: build_role_html(
            page_id, role_name, role_code, rows, ddragon_version
        )
        for page_id, role_name, role_code, filename in ROLE_PAGES
    }
