"""my_matches.csv から GitHub Pages 用の静的サイト (public/) を生成する。

Riot APIには一切アクセスしない純粋なビルド処理。
data/csv/my_matches.csv を読み、Pythonで集計してから
自己完結した public/index.html を書き出す（チャンピオンアイコンのみ
Data Dragon CDN を参照）。
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from queue_map import queue_id_to_name
from site_builder.data import (
    aggregate,
    group_by,
    is_ranked,
    is_support,
    load_last_updated,
    load_matches,
    table_rows_for_groups,
)
from site_builder.render import (
    PAGE_TEMPLATE,
    ROLE_LABEL,
    ROLE_ORDER,
    esc,
    render_champion_table,
    render_form,
    render_overview_cards,
    render_recent,
    render_simple_table,
    stat_block,
)

OUT_DIR = "public"

JST = timezone(timedelta(hours=9))

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
