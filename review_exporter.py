import csv
import os
from champion_registry import champion_name_ja
from queue_map import queue_id_to_name

REVIEW_CSV_PATH = "data/csv/review.csv"
MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"

REVIEW_COLUMNS = [
    "match_id",
    "date",
    "queue",
    "win",
    "role",
    "champion",
    "kills",
    "deaths",
    "assists",
    "team_kills",
    "team_deaths",
    "team_assists",
    "cs",
    "vision_score",
    "game_flow",
    "memo",
    "good_point",
    "bad_point",
    "next_theme",
]

QUEUE_NAME_MAP = {
    "400": "ドラフト",
    "420": "ランク",
    "430": "ブラインド",
    "440": "フレックス",
    "450": "ARAM",
    "700": "Clash",
    "1700": "アリーナ",
}

ROLE_NAME_MAP = {
    "TOP": "TOP",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
    "UTILITY": "SUP",
    "": "",
    None: "",
}

def queue_id_to_name(queue_id):
    return QUEUE_NAME_MAP.get(str(queue_id), f"Queue{queue_id}")

def role_to_name(role):
    return ROLE_NAME_MAP.get(role, role)

def win_to_wl(win_value):
    return "W" if str(win_value).lower() == "true" else "L"

def load_existing_reviews(review_csv_path):
    if not os.path.exists(review_csv_path):
        return {}

    reviews = {}

    with open(review_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reviews[row["match_id"]] = row

    return reviews

def load_my_match_rows(my_matches_csv_path):
    if not os.path.exists(my_matches_csv_path):
        print(f"my_matches.csvが見つかりません: {my_matches_csv_path}")
        return []

    with open(my_matches_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows

def build_review_row(my_match_row, existing_review=None):
    existing_review = existing_review or {}

    return {
        "match_id": my_match_row["match_id"],
        "date": my_match_row["date"],
        "queue": queue_id_to_name(my_match_row["queue_id"]),
        "win": win_to_wl(my_match_row["win"]),
        "role": role_to_name(my_match_row["role"]),
        "champion": champion_name_ja(my_match_row["champion"]),
        "kills": my_match_row["kills"],
        "deaths": my_match_row["deaths"],
        "assists": my_match_row["assists"],
        "team_kills": my_match_row["team_kills"],
        "team_deaths": my_match_row["team_deaths"],
        "team_assists": my_match_row["team_assists"],
        "cs": my_match_row["cs"],
        "vision_score": my_match_row["vision_score"],
        "game_flow": existing_review.get("game_flow", ""),
        "memo": existing_review.get("memo", ""),
        "good_point": existing_review.get("good_point", ""),
        "bad_point": existing_review.get("bad_point", ""),
        "next_theme": existing_review.get("next_theme", ""),
    }

def create_review_template(
    my_matches_csv_path=MY_MATCHES_CSV_PATH,
    review_csv_path=REVIEW_CSV_PATH,
):
    os.makedirs(os.path.dirname(review_csv_path), exist_ok=True)

    existing_reviews = load_existing_reviews(review_csv_path)
    my_match_rows = load_my_match_rows(my_matches_csv_path)

    # 手入力したレビュー（memo/GOOD/BAD等）を自動実行で消さないための保護
    if not my_match_rows:
        print("my_matches.csvが空のため、review.csvは更新しません（既存レビューを保持）")
        return

    output_rows = []
    added_count = 0
    updated_count = 0

    for my_match_row in my_match_rows:
        match_id = my_match_row["match_id"]
        existing_review = existing_reviews.get(match_id)

        output_rows.append(build_review_row(my_match_row, existing_review))

        if existing_review:
            updated_count += 1
        else:
            added_count += 1

    with open(review_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"review.csv テンプレート更新完了: 追加 {added_count} 行 / 既存維持 {updated_count} 行")
