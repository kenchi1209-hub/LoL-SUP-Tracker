import os
import requests
from dotenv import load_dotenv
from riot_api import save_match_json

load_dotenv()

API_KEY = os.getenv("RIOT_API_KEY")
MATCH_ID = "JP1_591434669"

url = f"https://asia.api.riotgames.com/lol/match/v5/matches/{MATCH_ID}"

headers = {
    "X-Riot-Token": API_KEY
}

response = requests.get(url, headers=headers)

print("Status Code:", response.status_code)

data = response.json()

# 画面にざっくり表示
print("matchId:", data["metadata"]["matchId"])
print("gameDuration:", data["info"]["gameDuration"])

for p in data["info"]["participants"]:
    print(
        p["riotIdGameName"],
        "#" + p["riotIdTagline"],
        p["teamPosition"],
        p["championName"],
        p["win"],
        f'{p["kills"]}/{p["deaths"]}/{p["assists"]}',
        "CS:", p["totalMinionsKilled"] + p["neutralMinionsKilled"],
        "VS:", p["visionScore"]
    )

# 生JSONを保存
path = save_match_json(MATCH_ID, data)
print(f"保存完了: {path}")
