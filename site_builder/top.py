"""TOP ページの集計構成と HTML 組み立てを扱う。"""

from queue_map import queue_id_to_name
from site_builder.data import (
    aggregate,
    group_by,
    is_ranked,
    table_rows_for_groups,
)
from site_builder.render import (
    PAGE_TEMPLATE,
    ROLE_LABEL,
    ROLE_ORDER,
    page_header_context,
    render_champion_table,
    render_form,
    render_navigation,
    render_simple_table,
    stat_block,
)


def build_html(rows, version):
    all_agg = aggregate(rows)

    ranked_rows = [r for r in rows if is_ranked(r)]
    ranked_agg = aggregate(ranked_rows)

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

    parts = [
        render_form(rows),

        stat_block("全体成績", all_agg),

        stat_block("ランク全体", ranked_agg),

        render_simple_table("ロール別成績", role_items),
        render_simple_table("キュー別成績", queue_items),
        render_champion_table(ranked_champ_items, version, "ランク使用チャンピオン別（全ロール）"),
        render_champion_table(champ_items, version, "チャンピオン別成績（全ロール）"),
    ]

    return PAGE_TEMPLATE.format(
        **page_header_context(rows),
        navigation=render_navigation("overview"),
        body="".join(parts),
    )
