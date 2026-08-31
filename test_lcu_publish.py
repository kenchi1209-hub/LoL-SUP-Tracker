import subprocess
from pathlib import Path
import unittest

from lcu_publish import PrivateDataPublisher, PublishError, is_allowed_match_path


class Result:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class GitRunner:
    """A no-network git/gh model for the publish transaction tests."""

    def __init__(self, changed_paths=None, remote_state=(0, 0), fail_push=False, fail_trigger=False):
        self.changed_paths = list(changed_paths or [])
        self.remote_state = remote_state
        self.fail_push = fail_push
        self.fail_trigger = fail_trigger
        self.calls = []
        self.committed = False
        self.pushed = False
        self.changes_visible = False

    def __call__(self, command, **_kwargs):
        self.calls.append(command)
        if command[:3] == ["git", "branch", "--show-current"]:
            return Result(stdout="main\n")
        if command[:3] == ["git", "status", "--porcelain=v1"]:
            if self.changes_visible and not self.committed:
                return Result(stdout="".join(f" M {path}\n" for path in self.changed_paths))
            return Result()
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return Result(stdout="base-sha\n" if not self.committed else "commit-sha\n")
        if command[:3] == ["git", "rev-parse", "origin/main"]:
            return Result(stdout="base-sha\n" if not self.pushed else "commit-sha\n")
        if command[:4] == ["git", "rev-list", "--left-right", "--count"]:
            if not self.committed:
                counts = self.remote_state
            elif not self.pushed:
                counts = (1, 0)
            else:
                counts = (0, 0)
            return Result(stdout=f"{counts[0]}\t{counts[1]}\n")
        if command[:4] == ["git", "diff", "--cached", "--name-only"]:
            return Result(stdout="".join(f"{path}\n" for path in self.changed_paths))
        if command[:4] == ["git", "diff", "--cached", "--quiet"]:
            return Result(returncode=1)
        if command[:2] == ["git", "commit"]:
            self.committed = True
            return Result()
        if command[:2] == ["git", "push"]:
            if self.fail_push:
                return Result(returncode=1)
            self.pushed = True
            return Result()
        if command[:3] == ["gh", "workflow", "run"]:
            return Result(returncode=1 if self.fail_trigger else 0)
        return Result()


class PrivateDataPublisherTest(unittest.TestCase):
    match_id = "JP1_123"
    expected_paths = [
        "raw/JP1_123/match.json",
        "raw/JP1_123/timeline.json",
        "raw/JP1_123/combat_timeline.json",
        "raw/JP1_123/rank_snapshot.json",
        "raw/JP1_123/rank_after.json",
        "csv/my_matches.csv",
        "csv/lp_history.json",
        "csv/match_details.json",
        "excel/lol_report.xlsx",
    ]

    def publisher(self, runner):
        self.logs = []
        return PrivateDataPublisher(
            "/tmp/private-data", "owner/public", runner=runner, emit=self.logs.append,
        )

    def test_expected_paths_are_narrow_and_match_scoped(self):
        for path in self.expected_paths:
            self.assertTrue(is_allowed_match_path(path, self.match_id))
        for path in (
            "docs/note.md", "raw/JP1_OTHER/match.json", "raw/lp_progress/recovered/blitz.json",
            "csv/recovered.json", "data/raw/match.json",
        ):
            self.assertFalse(is_allowed_match_path(path, self.match_id))

    def test_normal_exact_transaction_commits_pushes_then_dispatches(self):
        runner = GitRunner(self.expected_paths)
        publisher = self.publisher(runner)
        publisher.preflight()
        runner.changes_visible = True
        self.assertEqual(publisher.publish(self.match_id), "commit-sha")
        commands = [" ".join(command) for command in runner.calls]
        self.assertIn("git add -- " + " ".join(self.expected_paths), commands)
        self.assertTrue(any(command.startswith("git push origin HEAD:main") for command in commands))
        trigger_index = next(i for i, command in enumerate(commands) if command.startswith("gh workflow run"))
        push_index = next(i for i, command in enumerate(commands) if command.startswith("git push origin"))
        self.assertGreater(trigger_index, push_index)
        self.assertIn("[GIT] pushed origin/main", self.logs)
        self.assertIn("[PAGES] deploy workflow triggered", self.logs)

    def test_unrelated_dirty_file_stops_before_main_changes_are_staged(self):
        runner = GitRunner(["docs/manual.md"])
        runner.changes_visible = True
        publisher = self.publisher(runner)
        with self.assertRaisesRegex(PublishError, "dirty"):
            publisher.preflight()
        self.assertFalse(any(command[:2] == ["git", "add"] for command in runner.calls))

    def test_remote_ahead_or_diverged_stops_before_staging(self):
        for counts in ((0, 1), (1, 1)):
            runner = GitRunner(remote_state=counts)
            publisher = self.publisher(runner)
            with self.assertRaisesRegex(PublishError, "remote main"):
                publisher.preflight()
            self.assertFalse(any(command[:2] == ["git", "add"] for command in runner.calls))

    def test_unexpected_post_update_path_never_reaches_git_add(self):
        runner = GitRunner(["raw/JP1_123/rank_after.json", "raw/lp_progress/recovered/blitz.json"])
        publisher = self.publisher(runner)
        publisher.preflight()
        runner.changes_visible = True
        with self.assertRaisesRegex(PublishError, "unexpected PrivateData path"):
            publisher.publish(self.match_id)
        self.assertFalse(any(command[:2] == ["git", "add"] for command in runner.calls))

    def test_push_failure_never_triggers_pages(self):
        runner = GitRunner(self.expected_paths, fail_push=True)
        publisher = self.publisher(runner)
        publisher.preflight()
        runner.changes_visible = True
        with self.assertRaises(PublishError):
            publisher.publish(self.match_id)
        self.assertFalse(any(command[:3] == ["gh", "workflow", "run"] for command in runner.calls))

    def test_trigger_failure_is_reported_after_verified_private_push(self):
        runner = GitRunner(self.expected_paths, fail_trigger=True)
        publisher = self.publisher(runner)
        publisher.preflight()
        runner.changes_visible = True
        with self.assertRaises(PublishError):
            publisher.publish(self.match_id)
        self.assertTrue(runner.pushed)
        self.assertFalse(any("token" in entry.lower() for entry in self.logs))

    def test_pages_dispatch_is_build_only_and_manual_dispatch_keeps_its_default(self):
        workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertIn("private_data_pushed:", workflow)
        self.assertIn("default: false", workflow)
        condition = "github.event_name == 'workflow_dispatch' && !inputs.private_data_pushed"
        self.assertGreaterEqual(workflow.count(condition), 6)


if __name__ == "__main__":
    unittest.main()
