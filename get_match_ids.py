import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RIOT_API_KEY")
PUUID = "vzAqIeueWsbi6QrYsnjBe4CZ9Cs3nJNLACpgTA4jlu_8sQERtnn_3BdIkmhbChKv5fi14SZHruBs4Q"

url = f"https://asia.api.riotgames.com/lol/match/v5/matches/by-puuid/{PUUID}/ids?start=0&count=10"

headers = {
    "X-Riot-Token": API_KEY
}

response = requests.get(url, headers=headers)

print("Status Code:", response.status_code)
print(response.json())