"""Data Dragon の正式チャンピオンIDを解決する。"""

import re

from champion_map import CHAMPION_JA_MAP


# CHAMPION_JA_MAP のキーは Data Dragon champion.json の正式IDで管理されている。
OFFICIAL_CHAMPION_IDS = frozenset(CHAMPION_JA_MAP)

DISPLAY_NAME_ALIASES = {
    "Wukong": "MonkeyKing",
    "Kai'Sa": "Kaisa",
    "Vel'Koz": "Velkoz",
    "Cho'Gath": "Chogath",
    "LeBlanc": "Leblanc",
    "Bel'Veth": "Belveth",
    "Nunu & Willump": "Nunu",
    "Dr. Mundo": "DrMundo",
    "K'Sante": "KSante",
    "Kha'Zix": "Khazix",
    "Kog'Maw": "KogMaw",
    "Rek'Sai": "RekSai",
    "Renata Glasc": "Renata",
    "Aurelion Sol": "AurelionSol",
    "Jarvan IV": "JarvanIV",
    "Lee Sin": "LeeSin",
    "Master Yi": "MasterYi",
    "Miss Fortune": "MissFortune",
    "Tahm Kench": "TahmKench",
    "Twisted Fate": "TwistedFate",
    "Xin Zhao": "XinZhao",
}


def _lookup_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


_ID_BY_LOOKUP_KEY = {
    _lookup_key(champion_id): champion_id for champion_id in OFFICIAL_CHAMPION_IDS
}
_ID_BY_LOOKUP_KEY.update(
    {_lookup_key(name): champion_id for name, champion_id in DISPLAY_NAME_ALIASES.items()}
)


def champion_icon_id(champion):
    """表示名・CSV名をData Dragonの正式IDへ変換し、不明値は安全にfallbackする。"""
    value = str(champion or "").strip()
    if not value:
        return ""
    resolved = _ID_BY_LOOKUP_KEY.get(_lookup_key(value))
    if resolved:
        return resolved
    fallback = re.sub(r"[^A-Za-z0-9]", "", value)
    return fallback or value
