import json
import tempfile
import unittest
from pathlib import Path

from champion_registry import (
    ChampionRegistryError,
    champion_icon_id,
    champion_name_ja,
    load_registry,
    update_registry,
    validate_registry,
)


def registry(version="1.0.0", champions=None):
    champions = champions or {
        "Locke": {"id": "Locke", "key": "805", "name_ja": "ロック"},
        "Yunara": {"id": "Yunara", "key": "804", "name_ja": "ユナラ"},
    }
    return {"version": version, "champions": champions}


class ChampionRegistryTest(unittest.TestCase):
    def setUp(self):
        load_registry.cache_clear()

    def test_validation_rejects_empty_and_duplicate_keys(self):
        with self.assertRaises(ChampionRegistryError):
            validate_registry({"version": "1", "champions": {}})
        duplicated = registry(champions={
            "Locke": {"id": "Locke", "key": "805", "name_ja": "ロック"},
            "Yunara": {"id": "Yunara", "key": "805", "name_ja": "ユナラ"},
        })
        with self.assertRaises(ChampionRegistryError):
            validate_registry(duplicated)

    def test_failed_fetch_keeps_existing_registry_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            original = json.dumps(registry(), ensure_ascii=False, indent=2) + "\n"
            path.write_text(original, encoding="utf-8")

            def fail(_url):
                raise OSError("simulated network failure")

            with self.assertRaises(OSError):
                update_registry(path, fetcher=fail)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_partial_fetch_does_not_replace_larger_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            original = json.dumps(registry(), ensure_ascii=False, indent=2) + "\n"
            path.write_text(original, encoding="utf-8")
            responses = iter([
                ["2.0.0"],
                {"data": {"Locke": {"id": "Locke", "key": "805", "name": "ロック"}}},
            ])
            with self.assertRaises(ChampionRegistryError):
                update_registry(path, fetcher=lambda _url: next(responses))
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_fetch_cannot_replace_existing_ids_with_different_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            original = json.dumps(registry(), ensure_ascii=False, indent=2) + "\n"
            path.write_text(original, encoding="utf-8")
            responses = iter([
                ["2.0.0"],
                {"data": {
                    "Locke": {"id": "Locke", "key": "805", "name": "ロック"},
                    "Other": {"id": "Other", "key": "999", "name": "その他"},
                }},
            ])
            with self.assertRaises(ChampionRegistryError):
                update_registry(path, fetcher=lambda _url: next(responses))
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_registry_resolves_name_icon_and_alias(self):
        current = load_registry()
        self.assertEqual(champion_name_ja("Locke", current), "ロック")
        self.assertEqual(champion_icon_id("Locke", current), "Locke")
        self.assertEqual(champion_icon_id("Wukong", current), "MonkeyKing")


if __name__ == "__main__":
    unittest.main()
