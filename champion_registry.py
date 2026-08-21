"""Data Dragon由来のGit管理済みChampion Registryを扱う。"""

import argparse
import json
import os
import re
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path


REGISTRY_PATH = Path("data/csv/champion_registry.json")
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPION_DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/ja_JP/champion.json"

# Match-V5の表示名とData Dragon IDが異なるものだけを管理する。
DISPLAY_NAME_ALIASES = {
    "Wukong": "MonkeyKing", "Kai'Sa": "Kaisa", "Vel'Koz": "Velkoz",
    "Cho'Gath": "Chogath", "LeBlanc": "Leblanc", "Bel'Veth": "Belveth",
    "Nunu & Willump": "Nunu", "Dr. Mundo": "DrMundo", "K'Sante": "KSante",
    "Kha'Zix": "Khazix", "Kog'Maw": "KogMaw", "Rek'Sai": "RekSai",
    "Renata Glasc": "Renata", "Aurelion Sol": "AurelionSol",
    "Jarvan IV": "JarvanIV", "Lee Sin": "LeeSin", "Master Yi": "MasterYi",
    "Miss Fortune": "MissFortune", "Tahm Kench": "TahmKench",
    "Twisted Fate": "TwistedFate", "Xin Zhao": "XinZhao",
}

# Data Dragon表記変更後も既存サイトの表示を維持する最小限の例外。
DISPLAY_NAME_OVERRIDES = {
    "JarvanIV": "ジャーヴァンIV",
}


class ChampionRegistryError(RuntimeError):
    pass


def _lookup_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def validate_registry(registry, required_ids=()):
    if not isinstance(registry, dict):
        raise ChampionRegistryError("Registry root must be an object")
    version = str(registry.get("version") or "").strip()
    champions = registry.get("champions")
    if not version:
        raise ChampionRegistryError("Registry version is empty")
    if not isinstance(champions, dict) or not champions:
        raise ChampionRegistryError("Registry champions are empty")

    ids = []
    keys = []
    for source_id, champion in champions.items():
        if not isinstance(champion, dict):
            raise ChampionRegistryError(f"Invalid champion entry: {source_id}")
        champion_id = str(champion.get("id") or "").strip()
        numeric_key = str(champion.get("key") or "").strip()
        name_ja = str(champion.get("name_ja") or "").strip()
        if not champion_id or champion_id != source_id:
            raise ChampionRegistryError(f"Invalid champion id: {source_id}")
        if not numeric_key:
            raise ChampionRegistryError(f"Champion key is empty: {source_id}")
        if not name_ja:
            raise ChampionRegistryError(f"Champion name_ja is empty: {source_id}")
        ids.append(champion_id)
        keys.append(numeric_key)
    if len(ids) != len(set(ids)):
        raise ChampionRegistryError("Champion id is duplicated")
    if len(keys) != len(set(keys)):
        raise ChampionRegistryError("Champion key is duplicated")
    missing = sorted(set(required_ids) - set(ids))
    if missing:
        raise ChampionRegistryError(f"Required champions are missing: {', '.join(missing)}")
    return registry


@lru_cache(maxsize=None)
def load_registry(path=REGISTRY_PATH):
    registry_path = Path(path)
    try:
        with registry_path.open("r", encoding="utf-8") as file:
            registry = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ChampionRegistryError(
            f"Champion Registryを読み込めません: {registry_path} | {error}"
        ) from error
    return validate_registry(registry)


def registry_version(registry=None):
    return (registry or load_registry())["version"]


def _id_lookup(registry):
    champions = registry["champions"]
    lookup = {_lookup_key(champion_id): champion_id for champion_id in champions}
    lookup.update({_lookup_key(alias): champion_id for alias, champion_id in DISPLAY_NAME_ALIASES.items() if champion_id in champions})
    return lookup


@lru_cache(maxsize=1)
def _default_id_lookup():
    return _id_lookup(load_registry())


def champion_icon_id(champion, registry=None):
    value = str(champion or "").strip()
    if not value:
        return ""
    if registry is None:
        registry = load_registry()
        lookup = _default_id_lookup()
    else:
        lookup = _id_lookup(registry)
    resolved = lookup.get(_lookup_key(value))
    if resolved:
        return registry["champions"][resolved]["id"]
    fallback = re.sub(r"[^A-Za-z0-9]", "", value)
    return fallback or value


def champion_name_ja(champion, registry=None):
    value = str(champion or "").strip()
    if not value:
        return value
    if registry is None:
        registry = load_registry()
        lookup = _default_id_lookup()
    else:
        lookup = _id_lookup(registry)
    resolved = lookup.get(_lookup_key(value))
    if not resolved:
        return value
    return DISPLAY_NAME_OVERRIDES.get(
        resolved, registry["champions"][resolved]["name_ja"]
    )


def champion_name_map(registry=None):
    registry = registry or load_registry()
    return {
        champion_id: champion_name_ja(champion_id, registry)
        for champion_id in registry["champions"]
    }


def fetch_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def fetch_registry(fetcher=fetch_json, required_ids=()):
    versions = fetcher(VERSIONS_URL)
    if not isinstance(versions, list) or not versions:
        raise ChampionRegistryError("Data Dragon versions.json is empty")
    version = str(versions[0] or "").strip()
    if not version:
        raise ChampionRegistryError("Data Dragon latest version is empty")
    payload = fetcher(CHAMPION_DATA_URL.format(version=version))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data:
        raise ChampionRegistryError("Data Dragon champion data is empty")
    champions = {}
    for source_id in sorted(data):
        champion = data[source_id]
        champion_id = str(champion.get("id") or "").strip()
        if champion_id in champions:
            raise ChampionRegistryError(f"Champion id is duplicated: {champion_id}")
        champions[champion_id] = {
            "id": champion_id,
            "key": str(champion.get("key") or "").strip(),
            "name_ja": str(champion.get("name") or "").strip(),
        }
    return validate_registry({"version": version, "champions": champions}, required_ids=required_ids)


def write_registry_atomic(registry, path=REGISTRY_PATH):
    registry = validate_registry(registry)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(registry, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, destination)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
    load_registry.cache_clear()
    _default_id_lookup.cache_clear()


def update_registry(path=REGISTRY_PATH, fetcher=fetch_json, required_ids=()):
    registry = fetch_registry(fetcher=fetcher, required_ids=required_ids)
    try:
        existing = load_registry(Path(path))
    except ChampionRegistryError:
        existing = None
    if existing:
        missing_existing = sorted(
            set(existing["champions"]) - set(registry["champions"])
        )
        if missing_existing:
            raise ChampionRegistryError(
                "Fetched Champion Registry is missing existing champions: "
                f"{', '.join(missing_existing)}"
            )
    write_registry_atomic(registry, path=path)
    return registry


def main():
    parser = argparse.ArgumentParser(description="Champion Registryを更新する")
    parser.add_argument("update", nargs="?", default="update", choices=["update"])
    parser.add_argument("--output", default=str(REGISTRY_PATH))
    parser.add_argument("--require", action="append", default=[])
    args = parser.parse_args()
    output = Path(args.output)
    try:
        registry = update_registry(output, required_ids=args.require)
    except Exception as error:  # noqa: BLE001
        try:
            existing = load_registry(output)
        except Exception:  # noqa: BLE001
            print(f"Champion Registry更新失敗、利用可能な既存Registryなし: {error}")
            raise SystemExit(1) from error
        print(f"Champion Registry更新失敗、既存Registryを維持: version {existing['version']} / {len(existing['champions'])} champions | {error}")
        return
    print(f"Champion Registry更新完了: version {registry['version']} / {len(registry['champions'])} champions")


if __name__ == "__main__":
    main()
