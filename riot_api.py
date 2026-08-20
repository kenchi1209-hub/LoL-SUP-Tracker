import requests
import json
import time
from datetime import timedelta
from config import HEADERS
from timezone_utils import parse_jst_date
from raw_paths import DEFAULT_RAW_ROOT, paths_for_match


def date_to_unix_seconds(date_text):
    dt = parse_jst_date(date_text)
    return int(dt.timestamp())


def get_match_ids_by_date_range(puuid, start_date, end_date, page_size=100):
    start_time = date_to_unix_seconds(start_date)
    # end_date当日いっぱいまで含めるため、翌日の0:00をendTimeにする
    end_dt = parse_jst_date(end_date) + timedelta(days=1)
    end_time = int(end_dt.timestamp())
    all_match_ids = []
    start = 0
    while True:
        url = (
            f"https://asia.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?startTime={start_time}&endTime={end_time}&start={start}&count={page_size}"
        )
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        match_ids = response.json()
        if not match_ids:
            break
        all_match_ids.extend(match_ids)
        print(f"Match ID取得中: {len(all_match_ids)}件")
        if len(match_ids) < page_size:
            break
        start += page_size
        time.sleep(1)
    return all_match_ids

def get_puuid(game_name, tag_line):
    url = f"https://asia.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()["puuid"]


def get_current_solo_rank(puuid):
    url = f"https://jp1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    entries = response.json()
    for entry in entries:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            return entry
    return None


def get_match_ids(puuid, count=10):
    url = f"https://asia.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def get_match_detail(match_id):
    url = f"https://asia.api.riotgames.com/lol/match/v5/matches/{match_id}"
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            print(f"429 Rate Limit: {retry_after}秒待機します: {match_id}")
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        return response.json()


def get_match_timeline(match_id):
    url = f"https://asia.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            print(f"429 Rate Limit: {retry_after}秒待機します {match_id}")
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        return response.json()


def save_match_json(match_id, data, raw_root=DEFAULT_RAW_ROOT):
    path = paths_for_match(match_id, raw_root).detail
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path)


def save_match_timeline_json(match_id, data, raw_root=DEFAULT_RAW_ROOT):
    path = paths_for_match(match_id, raw_root).timeline
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path)
