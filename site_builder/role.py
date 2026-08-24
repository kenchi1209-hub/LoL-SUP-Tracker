"""ロール詳細ページの共通プレースホルダを生成する。"""

from collections import Counter

from champion_registry import champion_name_ja
from site_builder.render import (
    esc,
    load_template,
    match_history_data,
    render_match_history,
    render_navigation,
)


ROLE_PAGES = (
    ("support", "SUP", "UTILITY", "support.html"),
    ("mid", "MID", "MIDDLE", "mid.html"),
    ("top", "TOP", "TOP", "top.html"),
    ("adc", "ADC", "BOTTOM", "adc.html"),
    ("jungle", "JG", "JUNGLE", "jungle.html"),
)


ROLE_PAGE_TEMPLATE = load_template("role.html")


DEFAULT_OVERVIEW_CONTENT = """
<div class="cards">
  <div class="card"><div class="stat-label">試合数</div><div class="stat-value" data-overview="games">0戦</div></div>
  <div class="card"><div class="stat-label">勝率</div><div class="stat-value" data-overview="winrate">-</div><div class="stat-sub" data-overview="record">0勝 0敗</div></div>
  <div class="card"><div class="stat-label">平均K / D / A</div><div class="stat-value" data-overview="avg-kda">-</div></div>
  <div class="card"><div class="stat-label">KDA</div><div class="stat-value" data-overview="kda">-</div></div>
  <div class="card"><div class="stat-label">CS/m</div><div class="stat-value" data-overview="cspm">-</div></div>
  <div class="card"><div class="stat-label">VS/m</div><div class="stat-value" data-overview="vspm">-</div></div>
  <div class="card"><div class="stat-label">平均ゲーム時間</div><div class="stat-value" data-overview="duration">-</div></div>
</div>
"""


SUP_OVERVIEW_CONTENT = """
<div class="sup-overview-grid">
  <article class="card sup-overview-block">
    <h3>試合概要</h3>
    <div class="sup-overview-summary">
      <div class="sup-overview-stat">
        <div class="stat-label">試合数</div>
        <div class="stat-value" data-overview="games">0戦</div>
        <div class="stat-sub" data-overview="record">0勝 0敗</div>
      </div>
      <div class="sup-overview-stat">
        <div class="stat-label">勝率</div>
        <div class="stat-value" data-overview="winrate">-</div>
      </div>
      <div class="sup-overview-stat">
        <div class="stat-label">平均ゲーム時間</div>
        <div class="stat-value" data-overview="duration">-</div>
      </div>
    </div>
  </article>
  <article class="card sup-overview-block">
    <h3>平均パフォーマンス</h3>
    <div class="sup-overview-performance">
      <div class="sup-overview-stat sup-overview-kda">
        <div class="stat-label">K/D/A (KDA)</div>
        <div class="stat-value">
          <span data-overview="avg-kda">-</span>
          <span class="sup-overview-kda-ratio">(<span data-overview="kda">-</span>)</span>
        </div>
      </div>
      <div class="sup-overview-stat">
        <div class="stat-label">CS/m</div>
        <div class="stat-value" data-overview="cspm">-</div>
      </div>
    </div>
  </article>
</div>
"""


def champion_options(rows):
    counts = Counter(row.get("champion", "") for row in rows)
    champions = sorted(counts, key=lambda champion: (-counts[champion], champion))
    return "".join(
        f'<option value="{esc(champion)}">'
        f'{esc(champion_name_ja(champion))} ({counts[champion]})'
        "</option>"
        for champion in champions
        if champion
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
        champion_options=champion_options(role_rows),
        match_count=len(role_rows),
        overview_content=(
            SUP_OVERVIEW_CONTENT if role_name == "SUP" else DEFAULT_OVERVIEW_CONTENT
        ),
        match_data=match_history_data(role_rows),
        match_history=render_match_history(role_rows, ddragon_version, "role"),
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
