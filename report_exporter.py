import csv
import os
from champion_registry import champion_name_ja
from queue_map import queue_id_to_name

MY_MATCHES_CSV_PATH = "data/csv/my_matches.csv"
RESULT_REPORT_CSV_PATH = "data/csv/result_report.csv"

RESULT_REPORT_COLUMNS = [
    "match_id",
    "report_text",
]


ROLE_NAME_MAP = {
    "TOP": "TOP",
    "JUNGLE": "JG",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
    "UTILITY": "SUP",
    "": "",
    None: "",
}

def seconds_to_mmss(seconds):
    seconds = int(float(seconds))
    minutes = seconds // 60
    rest_seconds = seconds % 60
    return f"{minutes}:{rest_seconds:02d}"

def win_to_wl(win_value):
    return "W" if str(win_value).lower() == "true" else "L"

def role_to_name(role):
    return ROLE_NAME_MAP.get(role, role)

def format_one_decimal(value):
    try:
        return f"{float(value):.1f}"
    except (ValueError, TypeError):
        return value
    
def format_two_decimal(value):
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return value

def build_report_text(row):
    queue_name = queue_id_to_name(row["queue_id"])
    wl = win_to_wl(row["win"])
    duration = seconds_to_mmss(row["game_duration_seconds"])

    role = role_to_name(row["role"])
    champion = champion_name_ja(row["champion"])

    kills = row["kills"]
    deaths = row["deaths"]
    assists = row["assists"]

    team_kills = row["team_kills"]
    team_deaths = row["team_deaths"]
    team_assists = row["team_assists"]

    cs_per_min = format_one_decimal(row["cs_per_min"])
    cs = row["cs"]

    vision_score = row["vision_score"]
    vision_score_per_min = format_two_decimal(row.get("vision_score_per_min", 0))

    wards_placed = row.get("wards_placed", 0)
    wards_killed = row.get("wards_killed", 0)
    control_wards_bought = row.get("control_wards_bought", 0)

    return (
        f"{queue_name} / {wl} / {duration}\n"
        f"{role} / {champion}\n"
        f"{kills} / {deaths} / {assists} "
        f"({team_kills} / {team_deaths} / {team_assists}), "
        f"{cs_per_min} , {cs}\n"
        f"{vision_score} , {vision_score_per_min} , "
        f"{wards_placed} , {wards_killed} , {control_wards_bought}"
    )

def export_result_report(
    my_matches_csv_path=MY_MATCHES_CSV_PATH,
    result_report_csv_path=RESULT_REPORT_CSV_PATH,
):
    if not os.path.exists(my_matches_csv_path):
        print(f"my_matches.csvが見つかりません: {my_matches_csv_path}")
        return

    os.makedirs(os.path.dirname(result_report_csv_path), exist_ok=True)

    with open(my_matches_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda r: r["date"], reverse=True)

    with open(result_report_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_REPORT_COLUMNS)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "match_id": row["match_id"],
                "report_text": build_report_text(row),
            })

    print(f"result_report.csv 出力完了: {len(rows)} 件")
