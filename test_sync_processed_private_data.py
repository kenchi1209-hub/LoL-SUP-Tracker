import subprocess
import tempfile
import unittest
from pathlib import Path

from sync_processed_private_data import SyncError, build_plan, execute_plan, main


class ProcessedDataSyncTest(unittest.TestCase):
    def make_repositories(self, directory):
        root = Path(directory)
        data_root = root / "public-data"
        private = root / "private"
        (data_root / "csv/monthly").mkdir(parents=True)
        (data_root / "excel").mkdir(parents=True)
        private.mkdir()
        subprocess.run(["git", "init", "-q", private], check=True)
        (data_root / "csv/my_matches.csv").write_text("match_id\nJP1_TEST\n")
        (data_root / "csv/review.csv").write_text("match_id,memo\nJP1_TEST,keep\n")
        (data_root / "csv/monthly/2026-08_summary.txt").write_text("summary\n")
        (data_root / "excel/lol_report.xlsx").write_bytes(b"xlsx")
        (data_root / "csv/champion_registry.json").write_text("excluded")
        return data_root, private

    def test_preview_and_apply_copy_only_processed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root, private = self.make_repositories(directory)
            plan = build_plan(data_root, private)
            self.assertEqual([item.action for item in plan], ["COPY"] * 4)
            execute_plan(plan, apply=False)
            self.assertFalse((private / "csv/my_matches.csv").exists())
            execute_plan(plan, apply=True)
            self.assertTrue((private / "csv/my_matches.csv").is_file())
            self.assertTrue((private / "excel/lol_report.xlsx").is_file())
            self.assertFalse((private / "csv/champion_registry.json").exists())

    def test_identical_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root, private = self.make_repositories(directory)
            execute_plan(build_plan(data_root, private), apply=True)
            plan = build_plan(data_root, private)
            self.assertTrue(all(item.action == "SKIP" for item in plan))

    def test_conflict_prevents_all_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root, private = self.make_repositories(directory)
            (private / "csv").mkdir()
            (private / "csv/my_matches.csv").write_text("different\n")
            plan = build_plan(data_root, private)
            with self.assertRaises(SyncError):
                execute_plan(plan, apply=True)
            self.assertFalse((private / "excel/lol_report.xlsx").exists())

    def test_review_conflict_returns_nonzero_without_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root, private = self.make_repositories(directory)
            (private / "csv").mkdir()
            (private / "csv/review.csv").write_text("different review\n")
            result = main(
                [
                    "--data-root",
                    str(data_root),
                    "--private-data-dir",
                    str(private),
                    "--apply",
                ]
            )
            self.assertEqual(result, 1)
            self.assertFalse((private / "excel/lol_report.xlsx").exists())

    def test_destination_only_file_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root, private = self.make_repositories(directory)
            extra = private / "csv/private-only.txt"
            extra.parent.mkdir()
            extra.write_text("keep\n")
            execute_plan(build_plan(data_root, private), apply=True)
            self.assertEqual(extra.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main()
