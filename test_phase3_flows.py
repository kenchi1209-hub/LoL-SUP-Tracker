import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = ROOT / ".github/workflows/deploy.yml"
WINDOWS_PATH = ROOT / "daily_update.ps1"


class Phase3FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.workflow_text)
        cls.windows_text = WINDOWS_PATH.read_text(encoding="utf-8-sig")

    def workflow_step(self, name):
        steps = self.workflow["jobs"]["build"]["steps"]
        return next(step for step in steps if step.get("name") == name)

    def test_private_data_is_checked_out_for_every_event(self):
        checkout = self.workflow_step("Checkout PrivateData")
        self.assertNotIn("if", checkout)
        self.assertEqual(checkout["with"]["path"], "private-data")
        self.assertIn("PRIVATE_DATA_TOKEN", checkout["with"]["token"])

    def test_update_steps_write_directly_to_private_data(self):
        update = self.workflow_step("Fetch latest match data into PrivateData")
        verify = self.workflow_step("Verify PrivateData completeness")
        self.assertIn("--data-root", update["run"])
        self.assertIn("private-data", update["run"])
        self.assertIn("--data-root", verify["run"])
        self.assertIn("private-data", verify["run"])
        self.assertIn("schedule", update["if"])
        self.assertIn("workflow_dispatch", update["if"])

    def test_update_safety_order_precedes_build_and_deploy(self):
        names = [
            step.get("name") for step in self.workflow["jobs"]["build"]["steps"]
        ]
        self.assertLess(
            names.index("Fetch latest match data into PrivateData"),
            names.index("Verify PrivateData completeness"),
        )
        self.assertLess(
            names.index("Verify PrivateData completeness"),
            names.index("Commit refreshed PrivateData"),
        )
        self.assertLess(
            names.index("Commit refreshed PrivateData"),
            names.index("Build static site from PrivateData"),
        )
        self.assertNotIn("continue-on-error", self.workflow_text)
        self.assertNotIn("|| true", self.workflow_text)

    def test_public_push_builds_from_private_without_update_or_push(self):
        build = self.workflow_step("Build static site from PrivateData")
        self.assertNotIn("if", build)
        self.assertIn("--data-root", build["run"])
        self.assertIn("private-data", build["run"])
        self.assertNotIn("sync_private_data.py", self.workflow_text)
        self.assertNotIn("sync_processed_private_data.py", self.workflow_text)

    def test_private_commit_is_limited_and_remote_advance_is_fatal(self):
        script = self.workflow_step("Commit refreshed PrivateData")["run"]
        self.assertIn("git add -- raw csv excel", script)
        self.assertIn("remote_sha", script)
        self.assertIn("PRIVATE_BASE_SHA", script)
        self.assertNotIn("--force", script)
        self.assertNotIn("rebase", script)
        self.assertNotIn(" merge ", script)
        self.assertIn("--diff-filter=D", script)

    def test_public_commit_is_champion_registry_only(self):
        script = self.workflow_step("Commit Champion Registry only")["run"]
        self.assertIn("git add -- data/csv/champion_registry.json", script)
        self.assertNotIn("git add -- data\n", script)
        self.assertNotIn("raw csv excel", script)

    def test_windows_flow_writes_only_private_data(self):
        self.assertIn("main.py --data-root $PrivateRepo", self.windows_text)
        self.assertIn(
            "verify_fight_raw_completeness.py --data-root $PrivateRepo",
            self.windows_text,
        )
        self.assertIn("git add -- raw csv excel", self.windows_text)
        self.assertNotIn("sync_private_data.py", self.windows_text)
        self.assertNotIn("sync_processed_private_data.py", self.windows_text)
        self.assertNotIn("git push origin build", self.windows_text)
        self.assertNotIn("git add .", self.windows_text)


if __name__ == "__main__":
    unittest.main()
