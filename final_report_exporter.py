import csv
import os
from data_paths import CSV_ROOT

RESULT_REPORT_CSV_PATH = CSV_ROOT / "result_report.csv"
REVIEW_CSV_PATH = CSV_ROOT / "review.csv"
FINAL_REPORT_TXT_PATH = CSV_ROOT / "final_report.txt"

def load_result_reports(result_report_csv_path):
    if not os.path.exists(result_report_csv_path):
        print(f"result_report.csvが見つかりません: {result_report_csv_path}")
        return {}

    reports = {}

    with open(result_report_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reports[row["match_id"]] = row["report_text"]

    return reports

def load_reviews(review_csv_path):
    if not os.path.exists(review_csv_path):
        print(f"review.csvが見つかりません: {review_csv_path}")
        return []

    with open(review_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows

def build_final_report_block(review_row, base_report_text):
    game_flow = review_row.get("game_flow", "").strip()
    memo = review_row.get("memo", "").strip()
    good_point = review_row.get("good_point", "").strip()
    bad_point = review_row.get("bad_point", "").strip()
    next_theme = review_row.get("next_theme", "").strip()

    lines = [base_report_text]

    if game_flow:
        lines.append(f"試合状況： {game_flow}")

    if memo:
        lines.append(f"MEMO： {memo}")

    if good_point:
        lines.append(f"GOOD： {good_point}")

    if bad_point:
        lines.append(f"BAD： {bad_point}")

    if next_theme:
        lines.append(f"次回テーマ： {next_theme}")

    return "\n".join(lines)

def export_final_report(
    result_report_csv_path=RESULT_REPORT_CSV_PATH,
    review_csv_path=REVIEW_CSV_PATH,
    final_report_txt_path=FINAL_REPORT_TXT_PATH,
):
    reports = load_result_reports(result_report_csv_path)
    reviews = load_reviews(review_csv_path)

    if not reports or not reviews:
        print("final_report.txtを作成できませんでした")
        return

    blocks = []

    for review_row in reviews:
        match_id = review_row["match_id"]
        base_report_text = reports.get(match_id)

        if not base_report_text:
            continue

        blocks.append(build_final_report_block(review_row, base_report_text))

    os.makedirs(os.path.dirname(final_report_txt_path), exist_ok=True)

    with open(final_report_txt_path, "w", encoding="utf-8") as f:
        f.write("\n\n⸻\n\n".join(blocks))

    print(f"final_report.txt 出力完了: {len(blocks)} 件")
