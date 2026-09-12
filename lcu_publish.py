"""Safe, opt-in publishing for one exact LCU-ranked match update.

This module deliberately stages individual validated paths instead of whole data
directories.  It is only invoked by ``lcu_watcher --live --auto-publish``.
"""

from __future__ import annotations

import json
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
UNRESOLVED_RAW_MATCH_FILENAMES = RAW_MATCH_FILENAMES - {"rank_after.json"}
UNRESOLVED_SHARED_PATHS = GENERATED_SHARED_PATHS - {"csv/lp_history.json"}


def is_allowed_match_path(
    path, match_id, correction_match_id=None, confirmation_match_id=None,
):
    """Allow generated exports, this match, and explicitly verified predecessors."""
    if path in GENERATED_SHARED_PATHS or path.startswith(GENERATED_DIRECTORY_PREFIXES):
        return True
    raw_prefix = f"raw/{match_id}/"
    if path.startswith(raw_prefix):
        return path[len(raw_prefix):] in RAW_MATCH_FILENAMES
    predecessor_ids = {candidate for candidate in (
        correction_match_id, confirmation_match_id,
    ) if candidate}
    return path in {
        f"raw/{candidate}/rank_after.json" for candidate in predecessor_ids
    }


def is_allowed_unresolved_match_path(path, match_id):
    """Allow one normal match update, but never allocate or revise LP data."""
    if path in UNRESOLVED_SHARED_PATHS or path.startswith(GENERATED_DIRECTORY_PREFIXES):
        return True
    raw_prefix = f"raw/{match_id}/"
    return path.startswith(raw_prefix) and path[len(raw_prefix):] in UNRESOLVED_RAW_MATCH_FILENAMES


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
    def _paths_from_name_status(output):
        """Read staged name-status output without materializing any file diff."""
        paths = []
        for line in output.splitlines():
            if not line:
                continue
            fields = line.split("\t")
            status = fields[0]
            if status not in {"A", "M"} or len(fields) != 2 or not fields[1]:
                raise PublishError("staged changes include rename, copy, deletion, or unreadable status")
            paths.append(fields[1])
        return paths

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

    def _head_json(self, path):
        """Load a small committed JSON file without reading a textual diff."""
        try:
            value = self._git("--no-pager", "show", f"{self.base_sha}:{path}").stdout
            parsed = json.loads(value)
        except (json.JSONDecodeError, PublishError) as error:
            raise PublishError("could not verify prior rank_after confirmation") from error
        if not isinstance(parsed, dict):
            raise PublishError("could not verify prior rank_after confirmation")
        return parsed

    def _worktree_json(self, path):
        try:
            with (self.private_root / path).open("r", encoding="utf-8") as file:
                parsed = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise PublishError("could not verify prior rank_after confirmation") from error
        if not isinstance(parsed, dict):
            raise PublishError("could not verify prior rank_after confirmation")
        return parsed

    def _confirmation_match_id(self, paths, match_id, correction_match_id=None):
        """Return one capture-confirmed predecessor, or reject every other raw change.

        A capture may only confirm the immediately preceding snapshot by changing
        its status from ``provisional`` to ``confirmed``.  Every other field,
        including rank, LP, and W/L, must remain byte-for-byte equivalent in
        parsed JSON.  The confirmed after-state must also be the current
        match's before-state, so an unrelated historical snapshot cannot gain
        allow-list access merely because its path ends in ``rank_after.json``.
        """
        prefix = "raw/"
        suffix = "/rank_after.json"
        candidates = [
            path for path in paths
            if path.startswith(prefix)
            and path.endswith(suffix)
            and path != f"raw/{match_id}/rank_after.json"
            and path != f"raw/{correction_match_id}/rank_after.json"
        ]
        if not candidates:
            return None
        if len(candidates) != 1:
            raise PublishError("unexpected prior rank_after changes; publish stopped")

        path = candidates[0]
        parts = path.split("/")
        if len(parts) != 3 or not parts[1]:
            raise PublishError("could not verify prior rank_after confirmation")
        confirmation_match_id = parts[1]
        previous = self._head_json(path)
        confirmed = self._worktree_json(path)
        current = self._worktree_json(f"raw/{match_id}/rank_after.json")

        unchanged_previous = dict(previous)
        unchanged_confirmed = dict(confirmed)
        previous_status = unchanged_previous.pop("lp_status", None)
        confirmed_status = unchanged_confirmed.pop("lp_status", None)
        previous_time = previous.get("game_datetime_jst")
        current_time = current.get("game_datetime_jst")
        if not (
            previous.get("snapshot_type") == "rank_after"
            and confirmed.get("snapshot_type") == "rank_after"
            and current.get("snapshot_type") == "rank_after"
            and previous.get("match_id") == confirmation_match_id
            and confirmed.get("match_id") == confirmation_match_id
            and current.get("match_id") == match_id
            and previous_status == "provisional"
            and confirmed_status == "confirmed"
            and unchanged_previous == unchanged_confirmed
            and isinstance(previous_time, str)
            and isinstance(current_time, str)
            and previous_time < current_time
            and confirmed.get("after") == current.get("before")
        ):
            raise PublishError("prior rank_after is not a confirmation-only change; publish stopped")
        return confirmation_match_id

    def _validate_changed_paths(self, match_id, correction_match_id=None):
        paths = self._status_paths()
        if not paths:
            raise PublishError("no PrivateData changes found after exact capture")
        confirmation_match_id = self._confirmation_match_id(
            paths, match_id, correction_match_id,
        )
        unexpected = [
            path for path in paths
            if not is_allowed_match_path(
                path, match_id, correction_match_id, confirmation_match_id,
            )
        ]
        if unexpected:
            raise PublishError("unexpected PrivateData path changed; publish stopped")
        return paths, confirmation_match_id

    def _validate_unresolved_changed_paths(self, match_id):
        """Validate a checkpoint-stopped update without permitting LP writes."""
        paths = self._status_paths()
        if not paths:
            raise PublishError("no PrivateData changes found after checkpoint")
        unexpected = [
            path for path in paths
            if not is_allowed_unresolved_match_path(path, match_id)
        ]
        if unexpected:
            raise PublishError("unexpected PrivateData path changed for unresolved publish; publish stopped")
        return paths

    def _commit_push_and_dispatch(self, match_id, paths, allowed_path):
        """Stage an already validated path set, then commit, push, and dispatch."""
        self._git("add", "--", *paths)
        staged = self._paths_from_name_status(
            self._git("--no-pager", "diff", "--cached", "--name-status").stdout
        )
        if sorted(staged) != sorted(paths) or any(not allowed_path(path) for path in staged):
            raise PublishError("staged paths failed validation; publish stopped")
        # Accept CRLF line endings from Windows CSV exporters, but retain all
        # other whitespace checks.  --no-pager also makes this safe for the
        # non-interactive watcher subprocess on Git for Windows.
        self._git(
            "-c", "core.whitespace=cr-at-eol", "--no-pager", "diff", "--cached", "--check",
        )
        if self._git("--no-pager", "diff", "--cached", "--quiet", check=False).returncode == 0:
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

    def publish(self, match_id, correction_match_id=None):
        """Commit one validated match update and dispatch a Pages-only public build."""
        if not self.base_sha:
            raise PublishError("publish preflight was not completed")
        paths, confirmation_match_id = self._validate_changed_paths(
            match_id, correction_match_id,
        )

        head, remote, counts = self._remote_state()
        if head != self.base_sha or remote != self.base_sha or counts != (0, 0):
            raise PublishError("remote main advanced during update; publish stopped")

        return self._commit_push_and_dispatch(
            match_id,
            paths,
            lambda path: is_allowed_match_path(
                path, match_id, correction_match_id, confirmation_match_id,
            ),
        )

    def publish_unresolved_match_update(self, match_id):
        """Publish one checkpoint-stopped Match-V5 update without LP allocation."""
        if not self.base_sha:
            raise PublishError("publish preflight was not completed")
        paths = self._validate_unresolved_changed_paths(match_id)

        head, remote, counts = self._remote_state()
        if head != self.base_sha or remote != self.base_sha or counts != (0, 0):
            raise PublishError("remote main advanced during update; publish stopped")

        return self._commit_push_and_dispatch(
            match_id,
            paths,
            lambda path: is_allowed_unresolved_match_path(path, match_id),
        )
