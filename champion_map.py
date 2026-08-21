"""Champion Registry移行後の後方互換API。"""

from champion_registry import champion_name_ja, champion_name_map


CHAMPION_JA_MAP = champion_name_map()


def champion_to_ja(champion):
    return champion_name_ja(champion)
