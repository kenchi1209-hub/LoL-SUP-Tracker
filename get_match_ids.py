"""Print the latest Match IDs for the configured Riot ID.

This is a manual utility only; the normal update flow uses ``main.py``.
"""

from config import GAME_NAME, TAG_LINE
from riot_api import get_match_ids, get_puuid


def configured_puuid():
    """Resolve the configured Riot ID without logging or falling back to a PUUID."""
    if not isinstance(GAME_NAME, str) or not GAME_NAME.strip():
        raise RuntimeError("RIOT_GAME_NAME is required")
    if not isinstance(TAG_LINE, str) or not TAG_LINE.strip():
        raise RuntimeError("RIOT_TAG_LINE is required")
    return get_puuid(GAME_NAME.strip(), TAG_LINE.strip())


def main():
    match_ids = get_match_ids(configured_puuid(), count=10)
    print(f"Match IDs: {len(match_ids)}")
    for match_id in match_ids:
        print(match_id)


if __name__ == "__main__":
    main()
