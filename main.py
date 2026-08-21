import json
import os
from raw_paths import paths_for_match

from config import (
    GAME_NAME,
    TAG_LINE,
    MATCH_COUNT,
    START_DATE,
    END_DATE,
)

from riot_api import (
    get_puuid,
    get_match_ids_by_date_range,
    get_match_detail,
    save_match_json,
    get_current_solo_rank,
    get_match_timeline,
    save_match_timeline_json,
)

from analyze_timeline import analyze_match_timeline
from csv_exporter import export_participants_from_raw
from my_exporter import export_my_matches_from_raw
from report_exporter import export_result_report
from review_exporter import create_review_template
from final_report_exporter import export_final_report
from summary_exporter import export_summary
from monthly_exporter import export_monthly_csvs
from yearly_exporter import export_yearly_summary
from excel_exporter import export_excel_report
from timezone_utils import now_jst
from timeline_summary_exporter import export_timeline_summary
from fight_detail_exporter import export_fight_details
from match_detail_exporter import export_match_details


def write_last_updated():
    os.makedirs(
        "data/csv",
        exist_ok=True,
    )

    updated_at = now_jst().strftime(
        "%Y-%m-%d %H:%M"
    )

    with open(
        "data/csv/last_updated.txt",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(updated_at)

    print(
        f"データ更新日時 出力完了: {updated_at}"
    )


def write_current_rank(puuid):
    rank = get_current_solo_rank(puuid)

    os.makedirs(
        "data/csv",
        exist_ok=True,
    )

    with open(
        "data/csv/current_rank.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            rank,
            f,
            ensure_ascii=False,
            indent=2,
        )

    if rank:
        print(
            f'現在ランク: '
            f'{rank["tier"]} '
            f'{rank["rank"]} '
            f'{rank["leaguePoints"]}LP'
        )
    else:
        print(
            "現在ランク: Unranked"
        )


# ============================================================
# PUUID
# ============================================================

puuid = get_puuid(
    GAME_NAME,
    TAG_LINE,
)

print("PUUID")
print(puuid)


# ============================================================
# Match ID
# ============================================================

print(
    f"\n対象期間: "
    f"{START_DATE} ～ {END_DATE}"
)

match_ids = get_match_ids_by_date_range(
    puuid,
    start_date=START_DATE,
    end_date=END_DATE,
    page_size=MATCH_COUNT,
)

print(
    f"\n取得したMatch ID: "
    f"{len(match_ids)}件"
)

for match_id in match_ids:
    print(match_id)


# ============================================================
# Match Detail JSON
# ============================================================

print(
    "\n試合詳細JSONを保存します"
)

for match_id in match_ids:
    raw_path = paths_for_match(match_id).detail

    if os.path.exists(raw_path):
        print(
            f"既存スキップ: {raw_path}"
        )
        continue

    data = get_match_detail(
        match_id
    )

    path = save_match_json(
        match_id,
        data,
    )

    print(
        f"保存完了: {path}"
    )


# ============================================================
# Timeline JSON
# ============================================================

print(
    "\nTimeline JSONを保存します"
)

for match_id in match_ids:
    timeline_path = paths_for_match(match_id).timeline

    if os.path.exists(
        timeline_path
    ):
        print(
            f"既存スキップ: "
            f"{timeline_path}"
        )
        continue

    timeline_data = get_match_timeline(
        match_id
    )

    path = save_match_timeline_json(
        match_id,
        timeline_data,
    )

    print(
        f"保存完了: {path}"
    )


# ============================================================
# Timeline Analysis
# ============================================================

print(
    "\nTimeline解析を実行します"
)

timeline_success = 0
timeline_failed = 0

for match_id in match_ids:
    try:
        result = analyze_match_timeline(
            match_id,
            puuid=puuid,
        )

        timeline_success += 1

        print(
            f"解析完了: "
            f"{match_id} "
            f"| {result['champion']} "
            f"| K/D/A "
            f"{result['kills']}/"
            f"{result['deaths']}/"
            f"{result['assists']} "
            f"| My Fights "
            f"{result['my_fights']}"
        )

    except Exception as error:
        timeline_failed += 1

        print(
            f"解析失敗: "
            f"{match_id} "
            f"| {error}"
        )


print(
    "\nTimeline解析結果: "
    f"成功 {timeline_success}件 "
    f"/ 失敗 {timeline_failed}件"
)

print(
    "\nTimeline Summary CSVに出力します"
)
export_timeline_summary()

print("\nExporting Fight Detail JSON")
export_fight_details()

print("\nExporting public Match Detail JSON")
export_match_details(puuid)

# ============================================================
# Existing exports
# ============================================================

print(
    "\nparticipants.csvに出力します"
)
export_participants_from_raw()


print(
    "\nmy_matches.csvに出力します"
)
export_my_matches_from_raw(
    puuid
)


print(
    "\nresult_report.csvに出力します"
)
export_result_report()


print(
    "\nreview.csvテンプレートを作成します"
)
create_review_template()


print(
    "\nfinal_report.txtに出力します"
)
export_final_report()


print(
    "\nsummary.txtに出力します"
)
export_summary()


print(
    "\n月別CSVに出力します"
)
export_monthly_csvs()


print(
    "\n年間summary.txtに出力します"
)
export_yearly_summary(
    now_jst().strftime("%Y")
)


print(
    "\nExcelレポートに出力します"
)
export_excel_report()


print(
    "\nデータ更新日時を出力します"
)
write_last_updated()


print(
    "\n現在ランクを出力します"
)
write_current_rank(
    puuid
)


# ============================================================
# Complete
# ============================================================

print(
    "\n=============================="
)

print(
    "全処理完了"
)

print(
    f"Match: {len(match_ids)}件"
)

print(
    f"Timeline解析: "
    f"成功 {timeline_success}件 "
    f"/ 失敗 {timeline_failed}件"
)

print(
    "=============================="
)
