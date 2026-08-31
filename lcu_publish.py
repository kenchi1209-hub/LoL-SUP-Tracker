"""Safe, opt-in publishing for one exact LCU-ranked match update.

This module deliberately stages individual validated paths instead of whole data
directories.  It is only invoked by ``lcu_watcher --live --auto-publish``.
"""

from __future__ import annotations

from pathlib import Path
import subprocess


class PublishError(RuntimeError):
    """The automatic publish safety checks refused to continue."""


GENERATED_SHARED_PATHS = frozenset({
    "csv/all_fight_details.json",
    "csv/current_rank.json",
    "csv/fight_details.json",
    "csv/final_report.txt",
    "csv/last_updated.txt",
    "csv/lp_history.json",
    "csv/match_details.json",
    "csv/my_matches.csv",
    "csv/participants.csv",
    "csv/result_report.csv",
    "csv/review.csv",
    "csv/summary.txt",
    "csv/timeline_summary.csv",
    "excel/lol_report.xlsx",
})
GENERATED_DIRECTORY_PREFIXES = ("csv/monthly/", "csv/yearly/")
RAW_MATCH_FILENAMES = frozenset({
    "match.json",
    "timeline.json",
    "combat_timeline.json",
    "fight_context.txt",
    "fight_review_context.txt",
    "rank_snapshot.json",
    "rank_after.json",
})


def is_allowed_match_path(path, match_id):
    """Allow only known exports and known raw files for this match ID."""
    if path in GENERATED_SHARED_PATHS or path.startswith(GENERATED_DIRECTORY_PREFIXES):
        return True
    raw_prefix = f"raw/{match_id}/"
    if not path.startswith(raw_prefix):
        return False
    return path[len(raw_prefix):] in RAW_MATCH_FILENAMES


class PrivateDataPublisher:
    """Validate, commit, push, and request one Pages-only workflow dispatch."""

    def __init__(
        self, private_root, public_repo, runner=subprocess.run, emit=print,
        workflow_file="deploy.yml", public_branch="build",
    ):
        self.private_root = Path(private_root).expanduser().resolve()
        self.public_repo = public_repo
        self.runner = runner
        self.emit = emit
        self.workflow_file = workflow_file
        self.public_branch = public_branch
        self.base_sha = None

    def _run(self, command, *, cwd=None, check=True):
        try:
            result = self.runner(
                command,
                cwd=str(cwd or self.private_root),
                shell=False,
                timeout=60,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PublishError(f"command unavailable or timed out: {command[0]}") from error
        if check and result.returncode != 0:
            raise PublishError(f"command failed: {' '.join(command[:3])}")
        return result

    def _git(self, *arguments, check=True):
        return self._run(["git", *arguments], check=check)

    @staticmethod
    def _paths_from_status(output):
        """Read ordinary porcelain v1 status, rejecting risky rename/copy states."""
        paths = []
        for line in output.splitlines():
            if not line:
                continue
            if len(line) < 4:
                raise PublishError("unreadable PrivateData git status")
            status, path = line[:2], line[3:]
            if "R" in status or "C" in status or "D" in status or path.startswith("../"):
                raise PublishError("PrivateData has rename, copy, or deletion; publish stopped")
            paths.append(path)
        return paths

    def _status_paths(self):
        result = self._git("status", "--porcelain=v1", "--untracked-files=all")
        return self._paths_from_status(result.stdout)

    def _remote_state(self):
        self._git("fetch", "origin", "main")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        remote = self._git("rev-parse", "origin/main").stdout.strip()
        counts = self._git("rev-list", "--left-right", "--count", "HEAD...origin/main").stdout.split()
        if len(counts) != 2:
            raise PublishError("could not determine PrivateData ahead/behind state")
        return head, remote, tuple(int(value) for value in counts)

    def preflight(self):
        """Require a clean, synchronized PrivateData repository before any writes."""
        branch = self._git("branch", "--show-current").stdout.strip()
        if branch != "main":
            raise PublishError("PrivateData is not on main; publish stopped")
        if self._status_paths():
            raise PublishError("PrivateData is dirty; publish stopped")
        head, remote, counts = self._remote_state()
        if head != remote or counts != (0, 0):
            raise PublishError("remote main is ahead or diverged; publish stopped")
        self.base_sha = head
        self.emit("[GIT] PrivateData preflight verified")

    def _validate_changed_paths(self, match_id):
        paths = self._status_paths()
        if not paths:
            raise PublishError("no PrivateData changes found after exact capture")
        unexpected = [path for path in paths if not is_allowed_match_path(path, match_id)]
        if unexpected:
            raise PublishError("unexpected PrivateData path changed; publish stopped")
        return paths

    def publish(self, match_id):
        """Commit one validated match update and dispatch a Pages-only public build."""
        if not self.base_sha:
            raise PublishError("publish preflight was not completed")
        paths = self._validate_changed_paths(match_id)

        head, remote, counts = self._remote_state()
        if head != self.base_sha or remote != self.base_sha or counts != (0, 0):
            raise PublishError("remote main advanced during update; publish stopped")

        self._git("add", "--", *paths)
        staged = self._git("diff", "--cached", "--name-only").stdout.splitlines()
        if sorted(staged) != sorted(paths) or any(
            not is_allowed_match_path(path, match_id) for path in staged
        ):
            raise PublishError("staged paths failed validation; publish stopped")
        self._git("diff", "--cached", "--check")
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            raise PublishError("no staged PrivateData changes found")

        self._git("config", "user.name", "LoL LCU watcher")
        self._git("config", "user.email", "lcu-watcher@users.noreply.github.com")
        self._git("commit", "-m", f"Update match {match_id}")
        commit_sha = self._git("rev-parse", "HEAD").stdout.strip()
        ahead, behind = self._remote_state()[2]
        if (ahead, behind) != (1, 0):
            raise PublishError("PrivateData changed unexpectedly before push; publish stopped")
        self._git("push", "origin", "HEAD:main")
        head, remote, counts = self._remote_state()
        if head != remote or counts != (0, 0):
            raise PublishError("PrivateData push could not be verified")
        self.emit(f"[GIT] committed {commit_sha[:12]}")
        self.emit("[GIT] pushed origin/main")

        # This dispatch is intentionally build-only: deploy.yml skips Riot/main.py writes.
        self._run(
            [
                "gh", "workflow", "run", self.workflow_file,
                "--repo", self.public_repo,
                "--ref", self.public_branch,
                "-f", "private_data_pushed=true",
            ],
            cwd=self.private_root,
        )
        self.emit("[PAGES] deploy workflow triggered")
        return commit_sha
