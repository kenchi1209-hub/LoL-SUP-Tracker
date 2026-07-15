import json
import glob
from config import GAME_NAME, TAG_LINE
from riot_api import get_puuid

puuid = get_puuid(GAME_NAME, TAG_LINE)
allowed = {"400", "420", "440", "470"}

total = 0
allowed_count = 0
found = 0
missing = []

for path in glob.glob("data/raw/*.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total += 1
    queue_id = str(data["info"].get("queueId"))

    if queue_id not in allowed:
        continue

    allowed_count += 1
    match_id = data["metadata"]["matchId"]

    if any(p.get("puuid") == puuid for p in data["info"]["participants"]):
        found += 1
    else:
        missing.append(match_id)

print("current puuid:", puuid)
print("total raw:", total)
print("allowed:", allowed_count)
print("puuid found:", found)
print("puuid missing:", len(missing))
print("sample missing:", missing[:10])