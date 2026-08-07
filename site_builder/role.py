"""ロール詳細ページの共通プレースホルダを生成する。"""

from collections import Counter

from champion_map import CHAMPION_JA_MAP
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
