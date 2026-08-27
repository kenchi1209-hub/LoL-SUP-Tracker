import argparse
import csv
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
from queue_map import is_allowed_queue_id
from data_paths import get_data_paths


def write_last_updated(csv_root=None):
    csv_root = get_data_paths().csv if csv_root is None else csv_root
    os.makedirs(csv_root, exist_ok=True)

    updated_at = now_jst().strftime(
        "%Y-%m-%d %H:%M"
    )

    with open(
        csv_root / "last_updated.txt",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(updated_at)

    print(
        f"データ更新日時 出力完了: {updated_at}"
    )


def write_current_rank(puuid, csv_root=None):
    csv_root = get_data_paths().csv if csv_root is None else csv_root
    rank = get_current_solo_rank(puuid)

    os.makedirs(
        csv_root,
        exist_ok=True,
    )

    with open(
        csv_root / "current_rank.json",
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


def load_published_match_ids(csv_path=None):
    csv_path = csv_path or get_data_paths().csv / "my_matches.csv"
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        return {
            row["match_id"]
            for row in csv.DictReader(file)
            if row.get("match_id")
        }


def discover_new_eligible_matches(match_ids, published_ids=None, raw_root=None):
    """Return eligible matches not yet present in the public match dataset."""
    published_ids = (
        published_ids
        if published_ids is not None
        else load_published_match_ids()
    )
    eligible = {}
    ineligible = []

    for match_id in dict.fromkeys(match_ids):
        if match_id in published_ids:
            continue

        detail_path = paths_for_match(match_id, raw_root).detail
        if detail_path.exists():
            with detail_path.open("r", encoding="utf-8") as file:
                detail = json.load(file)
        else:
            detail = get_match_detail(match_id)
        queue_id = detail.get("info", {}).get("queueId")
        if is_allowed_queue_id(queue_id):
            eligible[match_id] = detail
        else:
            ineligible.append(match_id)
            print(f"対象外Queueスキップ: {match_id} | queueId={queue_id}")

    return eligible, ineligible


def run(data_root=None):
    paths = get_data_paths(data_root)
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
    for match_id in match_ids:
        print(match_id)

    published_ids = load_published_match_ids(paths.csv / "my_matches.csv")
    new_matches, ineligible_ids = discover_new_eligible_matches(
        match_ids, published_ids, paths.raw
    )
    print(
        "\n新規Match確認: "
        f"eligible {len(new_matches)}件 / 対象外Queue {len(ineligible_ids)}件"
    )
    if not new_matches:
        print("[INFO] No new eligible matches; nothing to update.")
        return 0

    new_match_ids = list(new_matches)
    print("\n試合詳細JSONを保存します")
    for match_id, data in new_matches.items():
        if paths_for_match(match_id, paths.raw).detail.exists():
            print(f"既存スキップ: {paths_for_match(match_id, paths.raw).detail}")
            continue
        path = save_match_json(match_id, data, raw_root=paths.raw)
        print(f"保存完了: {path}")

    print("\nTimeline JSONを保存します")
    for match_id in new_match_ids:
        if paths_for_match(match_id, paths.raw).timeline.exists():
            print(f"既存スキップ: {paths_for_match(match_id, paths.raw).timeline}")
            continue
        timeline_data = get_match_timeline(match_id)
        path = save_match_timeline_json(match_id, timeline_data, raw_root=paths.raw)
        print(f"保存完了: {path}")

    print("\nTimeline解析を実行します")
    timeline_success = 0
    timeline_errors = []
    for match_id in new_match_ids:
        if paths_for_match(match_id, paths.raw).combat.exists():
            timeline_success += 1
            print(f"既存解析スキップ: {paths_for_match(match_id, paths.raw).combat}")
            continue
        try:
            result = analyze_match_timeline(match_id, puuid=puuid, raw_root=paths.raw)
            timeline_success += 1
            print(
                f"解析完了: {match_id} | {result['champion']} "
                f"| K/D/A {result['kills']}/{result['deaths']}/{result['assists']} "
                f"| My Fights {result['my_fights']}"
            )
        except Exception as error:
            timeline_errors.append((match_id, error))
            print(f"解析失敗: {match_id} | {error}")

    print(
        "\nTimeline解析結果: "
        f"成功 {timeline_success}件 / 失敗 {len(timeline_errors)}件"
    )
    if timeline_errors:
        failed_ids = ", ".join(match_id for match_id, _ in timeline_errors)
        raise RuntimeError(f"Timeline解析に失敗しました: {failed_ids}")

    print("\nTimeline Summary CSVに出力します")
    export_timeline_summary(paths.raw, paths.csv / "timeline_summary.csv")
    print("\nExporting Fight Detail JSON")
    export_fight_details(output_path=paths.csv / "fight_details.json", raw_root=paths.raw)
    print("\nExporting public Match Detail JSON")
    export_match_details(puuid, paths.raw, paths.csv / "match_details.json")
    print("\nparticipants.csvに出力します")
    export_participants_from_raw(paths.raw, paths.csv / "participants.csv")
    print("\nmy_matches.csvに出力します")
    export_my_matches_from_raw(
        puuid, paths.raw, paths.csv / "my_matches.csv", paths.csv / "timeline_summary.csv"
    )
    print("\nresult_report.csvに出力します")
    export_result_report(paths.csv / "my_matches.csv", paths.csv / "result_report.csv")
    print("\nreview.csvテンプレートを作成します")
    create_review_template(paths.csv / "my_matches.csv", paths.csv / "review.csv")
    print("\nfinal_report.txtに出力します")
    export_final_report(
        paths.csv / "result_report.csv", paths.csv / "review.csv", paths.csv / "final_report.txt"
    )
    print("\nsummary.txtに出力します")
    export_summary(paths.csv / "my_matches.csv", paths.csv / "summary.txt")
    print("\n月別CSVに出力します")
    export_monthly_csvs(paths.csv)
    print("\n年間summary.txtに出力します")
    export_yearly_summary(now_jst().strftime("%Y"), paths.csv)
    print("\nExcelレポートに出力します")
    export_excel_report(
        paths.csv / "my_matches.csv", paths.csv / "review.csv", paths.excel / "lol_report.xlsx"
    )
    print("\nデータ更新日時を出力します")
    write_last_updated(paths.csv)
    print("\n現在ランクを出力します")
    write_current_rank(puuid, paths.csv)

    print("\n==============================")
    print("全処理完了")
    print(f"新規eligible Match: {len(new_match_ids)}件")
    print(f"Timeline解析: 成功 {timeline_success}件 / 失敗 0件")
    print("==============================")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(run(args.data_root))
