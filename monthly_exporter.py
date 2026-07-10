import csv
import os
from collections import defaultdict
from summary_exporter import export_summary

MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"
PARTICIPANTS_CSV_PATH = "data/csv/participants.csv"
MONTHLY_DIR = "data/csv/monthly"

def get_month_key(date_text):
    # date例：2026-07-06 02:03:51
    return date_text[:7]

def read_csv_rows(csv_path):
    if not os.path.exists(csv_path):
        print(f"CSVが見つかりません: {csv_path}")
        return [], []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    return rows, fieldnames

def write_csv_rows(csv_path, rows, fieldnames):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def export_my_matches_monthly(
    my_matches_csv_path=MY_MATCHES_CSV_PATH,
    monthly_dir=MONTHLY_DIR,
):
    rows, fieldnames = read_csv_rows(my_matches_csv_path)

    if not rows:
        print("月別my_matches.csvを作成できませんでした")
        return

    grouped = defaultdict(list)

    for row in rows:
        month_key = get_month_key(row["date"])
        grouped[month_key].append(row)

    for month_key, month_rows in grouped.items():
        month_rows.sort(key=lambda r: r["date"], reverse=True)
        output_path = f"{monthly_dir}/{month_key}_my_matches.csv"
        write_csv_rows(output_path, month_rows, fieldnames)

    print(f"月別my_matches.csv 出力完了: {len(grouped)}か月分")

def export_participants_monthly(
    my_matches_csv_path=MY_MATCHES_CSV_PATH,
    participants_csv_path=PARTICIPANTS_CSV_PATH,
    monthly_dir=MONTHLY_DIR,
):
    my_rows, _ = read_csv_rows(my_matches_csv_path)
    participant_rows, participant_fieldnames = read_csv_rows(participants_csv_path)

    if not my_rows or not participant_rows:
        print("月別participants.csvを作成できませんでした")
        return

    match_id_to_month = {
        row["match_id"]: get_month_key(row["date"])
        for row in my_rows
    }

    grouped = defaultdict(list)

    for row in participant_rows:
        match_id = row["match_id"]
        month_key = match_id_to_month.get(match_id)

        if not month_key:
            continue

        grouped[month_key].append(row)

    for month_key, month_rows in grouped.items():
        output_path = f"{monthly_dir}/{month_key}_participants.csv"
        write_csv_rows(output_path, month_rows, participant_fieldnames)

    print(f"月別participants.csv 出力完了: {len(grouped)}か月分")

def export_monthly_summaries(monthly_dir=MONTHLY_DIR):
    if not os.path.exists(monthly_dir):
        print(f"monthlyフォルダが見つかりません: {monthly_dir}")
        return
    files = os.listdir(monthly_dir)
    my_match_files = [
        f for f in files
        if f.endswith("_my_matches.csv")
    ]
    if not my_match_files:
        print("月別summary.txtを作成できませんでした")
        return
    count = 0
    for filename in sorted(my_match_files):
        month_key = filename.replace("_my_matches.csv", "")
        my_matches_path = f"{monthly_dir}/{filename}"
        summary_path = f"{monthly_dir}/{month_key}_summary.txt"
        export_summary(
            my_matches_csv_path=my_matches_path,
            summary_txt_path=summary_path,
        )
        count += 1
    print(f"月別summary.txt 出力完了: {count}か月分")

def export_monthly_csvs():
    export_my_matches_monthly()
    export_participants_monthly()
    export_monthly_summaries()

