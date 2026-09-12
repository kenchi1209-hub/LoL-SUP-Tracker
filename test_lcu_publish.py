import json
import subprocess
from pathlib import Path
import tempfile
import unittest

from lcu_publish import PrivateDataPublisher, PublishError, is_allowed_match_path


class Result:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class GitRunner:
    """A no-network git/gh model for the publish transaction tests."""

    def __init__(
        self, changed_paths=None, remote_state=(0, 0), fail_push=False,
        fail_trigger=False, head_files=None,
    ):
        self.changed_paths = list(changed_paths or [])
        self.remote_state = remote_state
        self.fail_push = fail_push
        self.fail_trigger = fail_trigger
        self.calls = []
        self.committed = False
        self.pushed = False
        self.changes_visible = False
        self.head_files = dict(head_files or {})

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
        if command[:3] == ["git", "--no-pager", "show"]:
            return Result(stdout=self.head_files.get(command[3], ""), returncode=0 if command[3] in self.head_files else 1)
        if command[:4] == ["git", "rev-list", "--left-right", "--count"]:
            if not self.committed:
                counts = self.remote_state
            elif not self.pushed:
                counts = (1, 0)
            else:
                counts = (0, 0)
            return Result(stdout=f"{counts[0]}\t{counts[1]}\n")
        if command[:5] == ["git", "--no-pager", "diff", "--cached", "--name-status"]:
            return Result(stdout="".join(f"M\t{path}\n" for path in self.changed_paths))
        if command[:5] == ["git", "--no-pager", "diff", "--cached", "--quiet"]:
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

    def test_only_a_declared_previous_rank_after_is_allowed_for_lp_correction(self):
        previous = "JP1_PREVIOUS"
        self.assertTrue(
            is_allowed_match_path(
                f"raw/{previous}/rank_after.json", self.match_id, previous,
            )
        )
        self.assertFalse(
            is_allowed_match_path(
                f"raw/{previous}/timeline.json", self.match_id, previous,
            )
        )
        self.assertFalse(
            is_allowed_match_path(
                "raw/JP1_OTHER/rank_after.json", self.match_id, previous,
            )
        )

    def test_only_a_verified_previous_rank_after_is_allowed_for_confirmation(self):
        previous = "JP1_PREVIOUS"
        self.assertTrue(
            is_allowed_match_path(
                f"raw/{previous}/rank_after.json", self.match_id,
                confirmation_match_id=previous,
            )
        )
        self.assertFalse(
            is_allowed_match_path(
                f"raw/{previous}/timeline.json", self.match_id,
                confirmation_match_id=previous,
            )
        )

    def test_confirmation_allows_only_a_status_transition_with_continuity(self):
        previous_id = "JP1_PREVIOUS"
        previous_path = f"raw/{previous_id}/rank_after.json"
        current_path = f"raw/{self.match_id}/rank_after.json"
        before = {"tier": "SILVER", "division": "IV", "lp": 62, "wins": 63, "losses": 78}
        previous = {
            "snapshot_type": "rank_after", "match_id": previous_id,
            "game_datetime_jst": "2026-09-12T18:00:00+09:00", "lp_status": "provisional",
            "before": {"tier": "SILVER", "division": "IV", "lp": 82, "wins": 63, "losses": 77},
            "after": before,
        }
        current = {
            "snapshot_type": "rank_after", "match_id": self.match_id,
            "game_datetime_jst": "2026-09-12T18:30:00+09:00", "lp_status": "provisional",
            "before": before, "after": {**before, "losses": 79},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, value in ((previous_path, {**previous, "lp_status": "confirmed"}), (current_path, current)):
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(value), encoding="utf-8")
            runner = GitRunner(
                [current_path, previous_path], head_files={f"base-sha:{previous_path}": json.dumps(previous)},
            )
            runner.changes_visible = True
            publisher = PrivateDataPublisher(root, "owner/public", runner=runner)
            publisher.base_sha = "base-sha"
            paths, confirmation = publisher._validate_changed_paths(self.match_id)
            self.assertEqual(paths, [current_path, previous_path])
            self.assertEqual(confirmation, previous_id)

    def test_normal_transaction_with_one_verified_confirmation_reaches_push(self):
        previous_id = "JP1_PREVIOUS"
        previous_path = f"raw/{previous_id}/rank_after.json"
        current_path = f"raw/{self.match_id}/rank_after.json"
        rank = {"tier": "SILVER", "division": "IV", "lp": 62, "wins": 63, "losses": 78}
        previous = {
            "snapshot_type": "rank_after", "match_id": previous_id,
            "game_datetime_jst": "2026-09-12T18:00:00+09:00", "lp_status": "provisional",
            "after": rank,
        }
        current = {
            "snapshot_type": "rank_after", "match_id": self.match_id,
            "game_datetime_jst": "2026-09-12T18:30:00+09:00", "lp_status": "provisional",
            "before": rank,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, value in ((previous_path, {**previous, "lp_status": "confirmed"}), (current_path, current)):
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(value), encoding="utf-8")
            runner = GitRunner(
                [current_path, previous_path], head_files={f"base-sha:{previous_path}": json.dumps(previous)},
            )
            publisher = PrivateDataPublisher(root, "owner/public", runner=runner)
            publisher.preflight()
            runner.changes_visible = True
            self.assertEqual(publisher.publish(self.match_id), "commit-sha")
            self.assertTrue(runner.pushed)

    def test_confirmation_rejects_rank_or_lp_changes_and_unrelated_predecessors(self):
        previous_id = "JP1_PREVIOUS"
        previous_path = f"raw/{previous_id}/rank_after.json"
        current_path = f"raw/{self.match_id}/rank_after.json"
        after = {"tier": "SILVER", "division": "IV", "lp": 62, "wins": 63, "losses": 78}
        previous = {
            "snapshot_type": "rank_after", "match_id": previous_id,
            "game_datetime_jst": "2026-09-12T18:00:00+09:00", "lp_status": "provisional",
            "after": after,
        }
        current = {
            "snapshot_type": "rank_after", "match_id": self.match_id,
            "game_datetime_jst": "2026-09-12T18:30:00+09:00", "lp_status": "provisional",
            "before": after,
        }
        for changed, message in (
            ({**previous, "lp_status": "confirmed", "lp_delta": 99}, "confirmation-only"),
            ({**previous, "lp_status": "confirmed", "after": {**after, "lp": 61}}, "confirmation-only"),
            ({**previous, "lp_status": "confirmed", "game_datetime_jst": "2026-09-12T19:00:00+09:00"}, "confirmation-only"),
        ):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for path, value in ((previous_path, changed), (current_path, current)):
                    destination = root / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(json.dumps(value), encoding="utf-8")
                runner = GitRunner(
                    [current_path, previous_path], head_files={f"base-sha:{previous_path}": json.dumps(previous)},
                )
                runner.changes_visible = True
                publisher = PrivateDataPublisher(root, "owner/public", runner=runner)
                publisher.base_sha = "base-sha"
                with self.assertRaisesRegex(PublishError, message):
                    publisher._validate_changed_paths(self.match_id)

    def test_unrelated_prior_rank_after_without_confirmation_transition_is_rejected(self):
        previous_id = "JP1_UNRELATED"
        previous_path = f"raw/{previous_id}/rank_after.json"
        current_path = f"raw/{self.match_id}/rank_after.json"
        rank = {"tier": "SILVER", "division": "IV", "lp": 62, "wins": 63, "losses": 78}
        previous = {
            "snapshot_type": "rank_after", "match_id": previous_id,
            "game_datetime_jst": "2026-09-12T18:00:00+09:00", "lp_status": "confirmed",
            "after": rank,
        }
        current = {
            "snapshot_type": "rank_after", "match_id": self.match_id,
            "game_datetime_jst": "2026-09-12T18:30:00+09:00", "lp_status": "provisional",
            "before": rank,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, value in ((previous_path, previous), (current_path, current)):
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(value), encoding="utf-8")
            runner = GitRunner(
                [current_path, previous_path], head_files={f"base-sha:{previous_path}": json.dumps(previous)},
            )
            runner.changes_visible = True
            publisher = PrivateDataPublisher(root, "owner/public", runner=runner)
            publisher.base_sha = "base-sha"
            with self.assertRaisesRegex(PublishError, "confirmation-only"):
                publisher._validate_changed_paths(self.match_id)

    def test_multiple_or_non_rank_after_unrelated_raw_changes_still_stop(self):
        runner = GitRunner([
            f"raw/{self.match_id}/rank_after.json",
            "raw/JP1_ONE/rank_after.json",
            "raw/JP1_TWO/rank_after.json",
        ])
        runner.changes_visible = True
        publisher = self.publisher(runner)
        publisher.base_sha = "base-sha"
        with self.assertRaisesRegex(PublishError, "prior rank_after"):
            publisher._validate_changed_paths(self.match_id)

    def test_normal_exact_transaction_commits_pushes_then_dispatches(self):
        runner = GitRunner(self.expected_paths)
        publisher = self.publisher(runner)
        publisher.preflight()
        runner.changes_visible = True
        self.assertEqual(publisher.publish(self.match_id), "commit-sha")
        commands = [" ".join(command) for command in runner.calls]
        self.assertIn("git add -- " + " ".join(self.expected_paths), commands)
        self.assertIn("git --no-pager diff --cached --name-status", commands)
        self.assertIn(
            "git -c core.whitespace=cr-at-eol --no-pager diff --cached --check", commands,
        )
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

    def test_staged_name_status_rejects_unknown_rename_and_delete_statuses(self):
        publisher = self.publisher(GitRunner())
        self.assertEqual(
            publisher._paths_from_name_status("A\traw/JP1_123/match.json\nM\tcsv/my_matches.csv\n"),
            ["raw/JP1_123/match.json", "csv/my_matches.csv"],
        )
        for output in (
            "D\traw/JP1_123/match.json\n",
            "R100\traw/JP1_123/match.json\traw/JP1_123/timeline.json\n",
            "C100\traw/JP1_123/match.json\traw/JP1_123/timeline.json\n",
            "M\n",
        ):
            with self.assertRaisesRegex(PublishError, "staged changes"):
                publisher._paths_from_name_status(output)

    def test_real_git_large_staged_crlf_data_uses_name_status_without_pager(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            csv_path = repo / "csv" / "my_matches.csv"
            json_path = repo / "raw" / self.match_id / "timeline.json"
            csv_path.parent.mkdir(parents=True)
            json_path.parent.mkdir(parents=True)
            csv_path.write_bytes(b"match_id,value\r\nJP1_123,1\r\n")
            json_path.write_bytes(b'{"events":"' + (b"x" * 1_000_000) + b'"}\r\n')
            subprocess.run(
                ["git", "-C", str(repo), "add", "--", "csv/my_matches.csv", "raw/JP1_123/timeline.json"],
                check=True,
                capture_output=True,
            )

            publisher = PrivateDataPublisher(repo, "owner/public")
            name_status = publisher._git(
                "--no-pager", "diff", "--cached", "--name-status",
            ).stdout
            self.assertEqual(
                sorted(publisher._paths_from_name_status(name_status)),
                ["csv/my_matches.csv", "raw/JP1_123/timeline.json"],
            )
            publisher._git(
                "-c", "core.whitespace=cr-at-eol", "--no-pager", "diff", "--cached", "--check",
            )

            dirty_path = repo / "csv" / "ordinary-trailing-whitespace.txt"
            dirty_path.write_bytes(b"must still fail \n")
            subprocess.run(
                ["git", "-C", str(repo), "add", "--", "csv/ordinary-trailing-whitespace.txt"],
                check=True,
                capture_output=True,
            )
            self.assertNotEqual(
                publisher._git(
                    "-c", "core.whitespace=cr-at-eol", "--no-pager", "diff", "--cached", "--check",
                    check=False,
                ).returncode,
                0,
            )


if __name__ == "__main__":
    unittest.main()
