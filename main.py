import os
from config import GAME_NAME, TAG_LINE, MATCH_COUNT, START_DATE, END_DATE
from riot_api import get_puuid, get_match_ids_by_date_range, get_match_detail, save_match_json
from csv_exporter import export_participants_from_raw
from my_exporter import export_my_matches_from_raw
from report_exporter import export_result_report
from review_exporter import create_review_template
from final_report_exporter import export_final_report
from summary_exporter import export_summary
from monthly_exporter import export_monthly_csvs
from yearly_exporter import export_yearly_summary

puuid = get_puuid(GAME_NAME, TAG_LINE)
print("PUUID")
print(puuid)
print(f"\n対象期間: {START_DATE} ～ {END_DATE}")
match_ids = get_match_ids_by_date_range(
    puuid,
    start_date=START_DATE,
    end_date=END_DATE,
    page_size=MATCH_COUNT,
)

print(f"\n取得したMatch ID: {len(match_ids)}件")
for m in match_ids:
    print(m)

print("\n試合詳細JSONを保存します")
for match_id in match_ids:
    raw_path = f"data/raw/{match_id}.json"

    if os.path.exists(raw_path):
        print(f"既存スキップ: {raw_path}")
        continue

    data = get_match_detail(match_id)
    path = save_match_json(match_id, data)
    print(f"保存完了: {path}")

print("\nparticipants.csvに出力します")
export_participants_from_raw()

print("\nmy_matches.csvに出力します")
export_my_matches_from_raw(puuid)

print("\nresult_report.csvに出力します")
export_result_report()

print("\nreview.csvテンプレートを作成します")
create_review_template()

print("\nfinal_report.txtに出力します")
export_final_report()

print("\nsummary.txtに出力します")
export_summary()

print("\n月別CSVに出力します")
export_monthly_csvs()

print("\n年間summary.txtに出力します")
export_yearly_summary("2026")