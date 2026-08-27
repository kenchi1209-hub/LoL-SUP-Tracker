import csv
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_site
import main
from champion_registry import registry_version
from data_paths import DEFAULT_DATA_ROOT, get_data_paths, resolve_data_root
from review_exporter import REVIEW_COLUMNS, create_review_template
from report_exporter import export_result_report


REPOSITORY_ROOT = Path(__file__).resolve().parent


class DataPathsTest(unittest.TestCase):
    def test_default_data_root_is_public_repository_data(self):
        self.assertEqual(resolve_data_root(environ={}), REPOSITORY_ROOT / "data")

    def test_environment_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "private-data"
            paths = get_data_paths(environ={"LOL_DATA_ROOT": str(root)})
            self.assertEqual(paths.root, root.resolve())
            self.assertEqual(paths.raw, root.resolve() / "raw")
            self.assertEqual(paths.csv, root.resolve() / "csv")
            self.assertEqual(paths.excel, root.resolve() / "excel")

    def test_explicit_data_root_has_priority_over_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            explicit = Path(directory) / "cli"
            environment = Path(directory) / "environment"
            self.assertEqual(
                resolve_data_root(
                    explicit, {"LOL_DATA_ROOT": str(environment)}
                ),
                explicit.resolve(),
            )

    def test_main_and_build_cli_accept_data_root(self):
        self.assertEqual(main.parse_args(["--data-root", "/tmp/main-data"]).data_root, "/tmp/main-data")
        self.assertEqual(
            build_site.parse_args(["--data-root", "/tmp/build-data"]).data_root,
            "/tmp/build-data",
        )

    def test_main_noop_does_not_touch_custom_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            csv_root = root / "csv"
            csv_root.mkdir(parents=True)
            sentinel = csv_root / "my_matches.csv"
            sentinel.write_text("match_id\n", encoding="utf-8")
            before = sentinel.read_bytes()
            with patch.object(main, "get_puuid", return_value="puuid"), patch.object(
                main, "get_match_ids_by_date_range", return_value=[]
            ), patch.object(main, "write_last_updated") as timestamp_writer:
                self.assertEqual(main.run(root), 0)
            self.assertEqual(sentinel.read_bytes(), before)
            timestamp_writer.assert_not_called()

    def test_review_manual_fields_are_preserved_in_custom_root(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_root = Path(directory) / "csv"
            csv_root.mkdir(parents=True)
            matches = csv_root / "my_matches.csv"
            review = csv_root / "review.csv"
            match_row = {
                "match_id": "JP1_TEST",
                "date": "2026-08-27 12:00:00",
                "queue_id": "420",
                "win": "True",
                "role": "UTILITY",
                "champion": "Leona",
                "kills": "1",
                "deaths": "2",
                "assists": "3",
                "team_kills": "10",
                "team_deaths": "8",
                "team_assists": "20",
                "cs": "30",
                "vision_score": "70",
            }
            with matches.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(match_row))
                writer.writeheader()
                writer.writerow(match_row)
            review_row = {column: "" for column in REVIEW_COLUMNS}
            review_row.update(
                {"match_id": "JP1_TEST", "memo": "keep me", "good_point": "ward"}
            )
            with review.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS)
                writer.writeheader()
                writer.writerow(review_row)

            create_review_template(matches, review)

            with review.open("r", encoding="utf-8-sig", newline="") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["memo"], "keep me")
            self.assertEqual(row["good_point"], "ward")

    def test_exporter_writes_only_to_explicit_custom_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_root = Path(directory) / "csv"
            csv_root.mkdir(parents=True)
            source = csv_root / "my_matches.csv"
            output = csv_root / "result_report.csv"
            row = {
                "match_id": "JP1_TEST",
                "date": "2026-08-27 12:00:00",
                "queue_id": "420",
                "win": "True",
                "game_duration_seconds": "1800",
                "role": "UTILITY",
                "champion": "Leona",
                "kills": "1",
                "deaths": "2",
                "assists": "3",
                "team_kills": "10",
                "team_deaths": "8",
                "team_assists": "20",
                "cs_per_min": "1.0",
                "cs": "30",
                "vision_score": "70",
                "vision_score_per_min": "2.33",
                "wards_placed": "20",
                "wards_killed": "5",
                "control_wards_bought": "4",
            }
            with source.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)

            export_result_report(source, output)

            self.assertTrue(output.is_file())
            self.assertIn("JP1_TEST", output.read_text(encoding="utf-8-sig"))

    def test_custom_site_build_uses_custom_csv_without_copying_source_data(self):
        with tempfile.TemporaryDirectory() as directory:
            public_registry_version = registry_version()
            temporary = Path(directory)
            root = temporary / "data"
            shutil.copytree(DEFAULT_DATA_ROOT / "csv", root / "csv")
            marker = "2099-12-31 23:59"
            (root / "csv" / "last_updated.txt").write_text(marker, encoding="utf-8")
            output = temporary / "public"

            with patch.dict(
                os.environ, {"LOL_DATA_ROOT": str(temporary / "wrong-root")}
            ), patch.object(build_site, "OUT_DIR", output):
                build_site.main(root)

            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "history.html").is_file())
            self.assertIn(marker, (output / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(registry_version(), public_registry_version)
            self.assertFalse(any(path.name == "raw" for path in output.rglob("raw")))
            self.assertFalse(any(path.suffix in {".csv", ".json"} for path in output.rglob("*")))

    def test_site_build_uses_environment_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "data"
            shutil.copytree(DEFAULT_DATA_ROOT / "csv", root / "csv")
            marker = "2098-01-02 03:04"
            (root / "csv" / "last_updated.txt").write_text(marker, encoding="utf-8")
            output = temporary / "public"
            try:
                with patch.dict(os.environ, {"LOL_DATA_ROOT": str(root)}), patch.object(
                    build_site, "OUT_DIR", output
                ):
                    build_site.main()
                self.assertIn(
                    marker, (output / "index.html").read_text(encoding="utf-8")
                )
            finally:
                build_site.configure_site_data(DEFAULT_DATA_ROOT)
                build_site.configure_render_data(DEFAULT_DATA_ROOT)


if __name__ == "__main__":
    unittest.main()
