import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fight_detail_shards import ShardError, ShardReader, validate_data_root, validate_shards, week_for_match, write_shards
from lcu_publish import PrivateDataPublisher, PublishError, is_weekly_fight_path


class FightDetailShardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw"
        self.output = self.root / "all_fight_details"

    def match(self, match_id, iso_time, creation=None):
        path = self.raw / match_id
        path.mkdir(parents=True, exist_ok=True)
        start = int(datetime.fromisoformat(iso_time).timestamp() * 1000)
        (path / "match.json").write_text(json.dumps({
            "metadata": {"matchId": match_id},
            "info": {"gameStartTimestamp": start, "gameCreation": creation or start},
        }), encoding="utf-8")

    def test_iso_year_jst_boundary_and_creation_ignored(self):
        self.match("JP1_A", "2021-01-03T23:59:59+09:00")
        self.match("JP1_B", "2021-01-04T00:00:00+09:00", 1609685999000)
        self.match("JP1_C", "2020-12-31T16:00:00+00:00")
        self.assertEqual(week_for_match(self.raw, "JP1_A"), "2020-W53.json")
        self.assertEqual(week_for_match(self.raw, "JP1_B"), "2021-W01.json")
        self.assertEqual(week_for_match(self.raw, "JP1_C"), "2020-W53.json")

    def test_roundtrip_empty_fights_and_idempotence(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        self.match("JP1_B", "2026-11-10T00:00:00+09:00")
        details = {"JP1_A": [], "JP1_B": [{"events": [1, 2], "position": {"x": 1}}]}
        write_shards(details, self.raw, self.output)
        before = {x.name: (x.read_bytes(), x.stat().st_mtime_ns) for x in self.output.iterdir()}
        reader = ShardReader(self.output)
        self.assertEqual({mid: reader.get(mid) for mid in details}, details)
        write_shards(details, self.raw, self.output)
        self.assertEqual(before, {x.name: (x.read_bytes(), x.stat().st_mtime_ns) for x in self.output.iterdir()})

    def test_missing_corrupt_duplicate_and_stale_fail_closed(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        write_shards({"JP1_A": []}, self.raw, self.output)
        shard = self.output / "2026-W45.json"
        original = shard.read_bytes()
        shard.unlink()
        with self.assertRaises(ShardError): validate_shards(self.output)
        shard.write_bytes(b'{"JP1_A":[],"JP1_A":[]}')
        with self.assertRaises(ShardError): validate_shards(self.output)
        shard.write_bytes(original)
        (self.output / "2026-W44.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ShardError): validate_shards(self.output)

    def test_duplicate_match_across_valid_checksummed_weeks_is_rejected(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        write_shards({"JP1_A": []}, self.raw, self.output)
        copied = (self.output / "2026-W45.json").read_bytes()
        (self.output / "2026-W44.json").write_bytes(copied)
        path = self.output / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["weeks"]["2026-W44.json"] = hashlib.sha256(copied).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ShardError): validate_shards(self.output)

    def test_manifest_must_assign_each_match_to_its_real_start_week(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        write_shards({"JP1_A": []}, self.raw, self.output)
        source = self.output / "2026-W45.json"
        content = source.read_bytes()
        source.rename(self.output / "2026-W44.json")
        manifest = {"schema_version": 1, "matches": {"JP1_A": "2026-W44.json"}, "weeks": {"2026-W44.json": hashlib.sha256(content).hexdigest()}}
        (self.output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ShardError): validate_shards(self.output, self.raw)

    def test_failure_rolls_back_existing_bytes(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        write_shards({"JP1_A": [1]}, self.raw, self.output)
        before = {x.name: x.read_bytes() for x in self.output.iterdir()}
        import fight_detail_shards as shards
        original = shards._atomic_write
        count = [0]
        def fail_once(path, content):
            count[0] += 1
            if count[0] == 2:
                raise OSError("simulated failure")
            return original(path, content)
        with patch.object(shards, "_atomic_write", side_effect=fail_once):
            with self.assertRaises(OSError): write_shards({"JP1_A": [2]}, self.raw, self.output)
        self.assertEqual(before, {x.name: x.read_bytes() for x in self.output.iterdir()})
        validate_shards(self.output)

    def test_add_late_update_and_move_existing_match(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        write_shards({"JP1_A": [1]}, self.raw, self.output)
        self.match("JP1_B", "2026-10-26T00:00:00+09:00")
        write_shards({"JP1_A": [2], "JP1_B": []}, self.raw, self.output)
        self.assertEqual(ShardReader(self.output).get("JP1_A"), [2])
        self.assertEqual(ShardReader(self.output).get("JP1_B"), [])
        self.match("JP1_A", "2026-11-09T00:00:00+09:00")
        write_shards({"JP1_A": [2], "JP1_B": []}, self.raw, self.output)
        self.assertFalse((self.output / "2026-W45.json").exists())
        self.assertTrue((self.output / "2026-W46.json").exists())
        with self.assertRaises(ShardError):
            write_shards({"JP1_A": [2]}, self.raw, self.output)
        self.assertEqual(set(validate_shards(self.output)["matches"]), {"JP1_A", "JP1_B"})

    def test_publisher_path_rejects_traversal_and_other_files(self):
        for name in ("csv/all_fight_details/2026-W45.json", "csv\\all_fight_details\\2026-W45.json", "csv/all_fight_details/manifest.json"):
            self.assertTrue(is_weekly_fight_path(name))
        for name in ("csv/all_fight_details/../lp_history.json", "csv/all_fight_details/evil.json", "csv/all_fight_details/2026-W99.json"):
            self.assertFalse(is_weekly_fight_path(name))

    def test_deletion_only_accepts_unreferenced_week_and_complete_data(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        directory = self.root / "csv" / "all_fight_details"
        write_shards({"JP1_A": []}, self.raw, directory)
        (self.root / "csv" / "fight_details.json").write_text('{"JP1_A":[]}', encoding="utf-8")
        validate_data_root(self.root, ["csv/all_fight_details/2026-W44.json"])
        for name in ("csv/lp_history.json", "csv/all_fight_details/manifest.json", "csv/all_fight_details/2026-W45.json"):
            with self.assertRaises(ShardError): validate_data_root(self.root, [name])
        self.assertEqual(PrivateDataPublisher._paths_from_status(" D csv/all_fight_details/2026-W44.json\n"), ["csv/all_fight_details/2026-W44.json"])
        with self.assertRaises(PublishError): PrivateDataPublisher._paths_from_status(" D csv/lp_history.json\n")

    def test_publisher_checks_weekly_data_before_allowing_changed_paths(self):
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        directory = self.root / "csv" / "all_fight_details"
        write_shards({"JP1_A": []}, self.raw, directory)
        (self.root / "csv" / "fight_details.json").write_text('{"JP1_A":[]}', encoding="utf-8")
        publisher = PrivateDataPublisher(self.root, "owner/repo")
        class Result:
            stdout = " M csv/all_fight_details/2026-W45.json\n"
        with patch.object(publisher, "_git", return_value=Result()):
            self.assertEqual(publisher._status_paths(), ["csv/all_fight_details/2026-W45.json"])
            (directory / "2026-W45.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(PublishError): publisher._status_paths()

    def test_site_uses_legacy_only_when_weekly_directory_is_absent(self):
        from site_builder import render
        self.match("JP1_A", "2026-11-02T00:00:00+09:00")
        csv_root = self.root / "csv"
        csv_root.mkdir()
        (csv_root / "fight_details.json").write_text('{"JP1_A":[]}', encoding="utf-8")
        (csv_root / "all_fight_details.json").write_text('{"JP1_A":[{"source":"legacy"}]}', encoding="utf-8")
        try:
            render.configure_data_root(self.root)
            self.assertEqual(render.load_all_fights("JP1_A"), [{"source": "legacy"}])
            write_shards({"JP1_A": [{"source": "weekly"}]}, self.raw, csv_root / "all_fight_details")
            render.configure_data_root(self.root)
            self.assertEqual(render.load_all_fights("JP1_A"), [{"source": "weekly"}])
            (csv_root / "all_fight_details" / "2026-W45.json").unlink()
            render.configure_data_root(self.root)
            with self.assertRaises(ShardError): render.load_all_fights("JP1_A")
        finally:
            render.configure_data_root(None)


if __name__ == "__main__":
    unittest.main()
