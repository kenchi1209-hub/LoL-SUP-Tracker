import os
import requests
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("RIOT_API_KEY")
GAME_NAME = os.getenv("RIOT_GAME_NAME")
TAG_LINE = os.getenv("RIOT_TAG_LINE")

print(API_KEY)
print(GAME_NAME, TAG_LINE)
url = f"https://asia.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{GAME_NAME}/{TAG_LINE}"
headers = {
    "X-Riot-Token": API_KEY
}
response = requests.get(url, headers=headers)
print("Status Code:", response.status_code)
print(response.json())