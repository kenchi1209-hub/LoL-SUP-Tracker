import csv
import os
from collections import defaultdict
from summary_exporter import export_summary

MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"
PARTICIPANTS_CSV_PATH = "data/csv/participants.csv"
MONTHLY_DIR = "data/csv/monthly"


def read_csv_rows(csv_path):
    if not os.path.exists(csv_path):
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


def get_month_key(date_text):
    # date例: 2026-07-10 23:12:34
    if not date_text:
        return None

    return date_text[:7]


def clear_old_monthly_outputs():
    if not os.path.exists(MONTHLY_DIR):
        os.makedirs(MONTHLY_DIR, exist_ok=True)
        return

    for filename in os.listdir(MONTHLY_DIR):
        if filename.endswith(".csv") or filename.endswith(".txt"):
            os.remove(os.path.join(MONTHLY_DIR, filename))


def export_my_matches_monthly():
    rows, fieldnames = read_csv_rows(MY_MATCHES_CSV_PATH)

    grouped = defaultdict(list)

    for row in rows:
        month_key = get_month_key(row.get("date", ""))
        if not month_key:
            continue

        grouped[month_key].append(row)

    for month_key, month_rows in grouped.items():
        month_rows.sort(key=lambda r: r.get("date", ""), reverse=True)

        output_path = f"{MONTHLY_DIR}/{month_key}_my_matches.csv"
        write_csv_rows(output_path, month_rows, fieldnames)

    print(f"月別my_matches.csv 出力完了: {len(grouped)}か月分")

    return grouped


def build_match_id_to_month(my_match_rows):
    match_id_to_month = {}

    for row in my_match_rows:
        match_id = row.get("match_id")
        month_key = get_month_key(row.get("date", ""))

        if not match_id or not month_key:
            continue

        match_id_to_month[match_id] = month_key

    return match_id_to_month


def export_participants_monthly():
    my_match_rows, _ = read_csv_rows(MY_MATCHES_CSV_PATH)
    participant_rows, participant_fieldnames = read_csv_rows(PARTICIPANTS_CSV_PATH)

    match_id_to_month = build_match_id_to_month(my_match_rows)

    grouped = defaultdict(list)

    for row in participant_rows:
        match_id = row.get("match_id")
        month_key = match_id_to_month.get(match_id)

        if not month_key:
            continue

        grouped[month_key].append(row)

    for month_key, month_rows in grouped.items():
        output_path = f"{MONTHLY_DIR}/{month_key}_participants.csv"
        write_csv_rows(output_path, month_rows, participant_fieldnames)

    print(f"月別participants.csv 出力完了: {len(grouped)}か月分")

    return grouped


def export_monthly_summaries():
    count = 0

    for filename in os.listdir(MONTHLY_DIR):
        if not filename.endswith("_my_matches.csv"):
            continue

        month_key = filename.replace("_my_matches.csv", "")
        my_matches_path = f"{MONTHLY_DIR}/{filename}"
        summary_path = f"{MONTHLY_DIR}/{month_key}_summary.txt"

        export_summary(
            my_matches_csv_path=my_matches_path,
            summary_txt_path=summary_path,
        )

        count += 1

    print(f"月別summary.txt 出力完了: {count}か月分")


def export_monthly_csvs():
    clear_old_monthly_outputs()
    export_my_matches_monthly()
    export_participants_monthly()
    export_monthly_summaries()