import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("RIOT_API_KEY")
GAME_NAME = os.getenv("RIOT_GAME_NAME")
TAG_LINE = os.getenv("RIOT_TAG_LINE")
MATCH_COUNT = int(os.getenv("MATCH_COUNT", "100"))
START_DATE = os.getenv("START_DATE", "2026-01-01")
END_DATE = os.getenv("END_DATE", "2026-12-31")
HEADERS = {
    "X-Riot-Token": API_KEY
}