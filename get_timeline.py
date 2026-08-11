import argparse

import requests

from config import API_KEY
from riot_api import get_match_timeline, save_match_timeline_json


DEFAULT_MATCH_ID = "JP1_596841033"


def main():
    parser = argparse.ArgumentParser(description="Riot Match Timelineを保存します")
    parser.add_argument("match_id", nargs="?", default=DEFAULT_MATCH_ID)
    args = parser.parse_args()

    if not API_KEY or not API_KEY.startswith("RGAPI-"):
        raise SystemExit(".envのRIOT_API_KEYに有効なRiot APIキーを設定してください")

    try:
        data = get_match_timeline(args.match_id)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        raise SystemExit(f"Timeline取得失敗 (status: {status})") from error

    print("status: 200")
    path = save_match_timeline_json(args.match_id, data)
    print(f"{path} を保存しました")


if __name__ == "__main__":
    main()
