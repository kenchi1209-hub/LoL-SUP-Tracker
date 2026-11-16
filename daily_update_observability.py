"""Fail-closed helpers for local Daily Update observability.

Only structured allowlisted output is eligible for persistence.  This module
does not write logs, invoke Riot, trigger deploys, or modify repositories.
"""

import argparse
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path


JST = timezone(timedelta(hours=9))
LOG_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d+)?\.log$")
ALLOWED_EVENTS = {"START", "DATA_UPDATE", "FIGHT_VALIDATION", "COMMIT", "PUSH", "PRIVATE_SHA", "PAGES", "DURATION_SECONDS", "END"}
ALLOWED_STATES = {"STARTED", "SUCCESS", "FAILED", "SKIPPED", "PENDING", "UNKNOWN"}
PAGE_REASONS = {"DEPLOY_SUCCESS", "DEPLOY_FAILED", "RUN_PENDING", "NO_MATCH", "SHA_INVALID", "API_FAILURE", "API_TIMEOUT", "METADATA_MISSING", "MALFORMED_RESPONSE", "EVIDENCE_MISMATCH", "PUSH_NOT_SUCCESS"}


def create_log(directory, now=None):
    """Create an exclusive JST log and remove only matching logs older than 30 days."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    now = (now or datetime.now(JST)).astimezone(JST)
    cutoff = now.timestamp() - 30 * 24 * 60 * 60
    for entry in directory.iterdir():
        if LOG_NAME.fullmatch(entry.name) and not entry.is_symlink() and entry.is_file() and entry.stat().st_mtime < cutoff:
            entry.unlink()
    stem = now.strftime("%Y-%m-%d_%H-%M-%S")
    for number in range(10000):
        name = f"{stem}{'_' + str(number) if number else ''}.log"
        try:
            with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(f"{now.isoformat(timespec='seconds')} START STARTED\n")
            return directory / name
        except FileExistsError:
            continue
    raise OSError("cannot create unique log")


def append_event(log_file, event, state, value=None, now=None):
    """Persist only predefined facts, never child output or arbitrary errors."""
    if event not in ALLOWED_EVENTS or state not in ALLOWED_STATES:
        raise ValueError("event or state is not allowlisted")
    if value is not None:
        if event == "PRIVATE_SHA":
            if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
                raise ValueError("invalid SHA")
        elif event == "PAGES":
            if value not in PAGE_REASONS:
                raise ValueError("invalid Pages reason")
        elif event in {"DATA_UPDATE", "FIGHT_VALIDATION", "COMMIT", "PUSH", "END", "DURATION_SECONDS"}:
            if not re.fullmatch(r"-?\d{1,10}", value):
                raise ValueError("invalid exit code")
        else:
            raise ValueError("event does not accept a value")
    path = Path(log_file)
    if not LOG_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file():
        raise ValueError("invalid log file")
    timestamp = (now or datetime.now(JST)).astimezone(JST).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{timestamp} {event} {state}{' ' + value if value is not None else ''}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "append", "pages"))
    parser.add_argument("--directory")
    parser.add_argument("--log-file")
    parser.add_argument("--event")
    parser.add_argument("--state")
    parser.add_argument("--value")
    parser.add_argument("--sha")
    parser.add_argument("--repo", default="kenchi1209-hub/LoL-SUP-Tracker")
    args = parser.parse_args()
    try:
        if args.action == "init":
            print(create_log(args.directory))
        elif args.action == "append":
            append_event(args.log_file, args.event, args.state, args.value)
        else:
            print(json.dumps(check_pages_status(args.sha, args.repo), separators=(",", ":")))
    except (OSError, ValueError, TypeError):
        parser.exit(1, "Daily Update log operation failed; no raw output was saved.\n")


_COUNTS = re.compile(r"^\s*(?:Fight Detail matches|Combat timelines|Missing combat timelines|Extra combat timelines|Missing required raw files|Incomplete Match directories):\s*(\d+)\s*$")
_MATCH_ID = re.compile(r"^\s*(JP1_\d+)\s*$")
_HTTP_STATUS = re.compile(r"\b(?:HTTP(?:Error)?|status(?: code)?)\s*[:=]?\s*(\d{3})\b", re.IGNORECASE)


def safe_child_output(line, *, stderr=False):
    """Return only known-safe facts, never untrusted raw subprocess output."""
    if not isinstance(line, str):
        return "[output omitted]"
    if stderr:
        match = _HTTP_STATUS.search(line)
        return f"[stderr] HTTP status {match.group(1)}" if match else "[stderr omitted]"
    match = _COUNTS.fullmatch(line)
    if match:
        label = line.strip().split(":", 1)[0]
        return f"{label}: {match.group(1)}"
    match = _MATCH_ID.fullmatch(line)
    if match:
        return f"Match ID: {match.group(1)}"
    return "[output omitted]"


def classify_pages_status(target_sha, runs, *, query_error=False, timed_out=False):
    """Classify only a run whose PrivateData SHA is explicitly evidenced.

    Each supplied run has private_sha, status, build_conclusion and
    deploy_conclusion.  A public-repository head SHA must not be used here.
    """
    if query_error or timed_out or not re.fullmatch(r"[0-9a-fA-F]{40}", str(target_sha or "")):
        return "UNKNOWN"
    if not isinstance(runs, list):
        return "UNKNOWN"
    uncertain = False
    for run in runs:
        if not isinstance(run, dict):
            uncertain = True
            continue
        private_sha = run.get("private_sha")
        if not isinstance(private_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", private_sha):
            uncertain = True
            continue
        if private_sha.lower() != target_sha.lower():
            return "UNKNOWN" if uncertain else "PENDING"
        if uncertain:
            return "UNKNOWN"
        if run.get("status") != "completed":
            return "PENDING"
        build, deploy = run.get("build_conclusion"), run.get("deploy_conclusion")
        if build == "success" and deploy == "success":
            return "SUCCESS"
        if build == "failure" or deploy == "failure":
            return "FAILED"
        return "UNKNOWN"
    return "UNKNOWN" if uncertain else "PENDING"


_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_PAGES_MARKER = re.compile(
    r"PAGES_INPUT_PRIVATE_SHA=([0-9a-fA-F]{40}) PUBLIC_SHA=([0-9a-fA-F]{40}) RUN_ID=(\d+)"
)


def check_pages_status(target_sha, repo, *, runner=subprocess.run, clock=time.monotonic, max_seconds=20):
    """Read GH run logs and jobs; never persist or expose the API response.

    Completed logs provide the build-input marker. If a newer run's evidence
    cannot be read, do not promote an older matching success to SUCCESS.
    """
    def result(state, reason):
        return {"state": state, "reason": reason}

    if not isinstance(target_sha, str) or not _SHA.fullmatch(target_sha):
        return result("UNKNOWN", "SHA_INVALID")
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return result("UNKNOWN", "MALFORMED_RESPONSE")
    deadline = clock() + max_seconds

    def gh(*args):
        remaining = deadline - clock()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("gh", max_seconds)
        response = runner(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=min(remaining, 6), check=False)
        if response.returncode != 0:
            raise OSError("GitHub query failed")
        return response.stdout

    try:
        runs = json.loads(gh("run", "list", "--repo", repo, "--workflow", "deploy.yml", "--branch", "build", "--limit", "5", "--json", "databaseId,status,conclusion,headSha"))
        if not isinstance(runs, list) or any(not isinstance(x, dict) for x in runs):
            return result("UNKNOWN", "MALFORMED_RESPONSE")
        for run in runs:
            run_id, public_sha = run.get("databaseId"), run.get("headSha")
            if not isinstance(run_id, int) or isinstance(run_id, bool) or not isinstance(public_sha, str) or not _SHA.fullmatch(public_sha):
                return result("UNKNOWN", "MALFORMED_RESPONSE")
            # GH may not expose logs before a job completes; lack of evidence
            # is not proof that the current run corresponds to our target.
            try:
                output = gh("run", "view", str(run_id), "--repo", repo, "--log")
            except OSError:
                if run.get("status") != "completed":
                    return result("UNKNOWN", "METADATA_MISSING")
                raise
            markers = _PAGES_MARKER.findall(output)
            if len(markers) != 1:
                return result("UNKNOWN", "METADATA_MISSING")
            private_sha, marker_public_sha, marker_run_id = markers[0]
            if marker_run_id != str(run_id) or marker_public_sha.lower() != public_sha.lower():
                return result("UNKNOWN", "EVIDENCE_MISMATCH")
            if private_sha.lower() != target_sha.lower():
                # A newer deployment for another SHA cannot prove our SHA is
                # currently published, even if an older run once succeeded.
                return result("PENDING", "NO_MATCH")
            info = json.loads(gh("run", "view", str(run_id), "--repo", repo, "--json", "databaseId,status,conclusion,headSha,jobs"))
            if not isinstance(info, dict) or info.get("databaseId") != run_id or info.get("headSha", "").lower() != public_sha.lower():
                return result("UNKNOWN", "EVIDENCE_MISMATCH")
            if run.get("status") == "completed" and (info.get("status") != "completed" or run.get("conclusion") != info.get("conclusion")):
                return result("UNKNOWN", "EVIDENCE_MISMATCH")
            jobs = info.get("jobs")
            if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
                return result("UNKNOWN", "MALFORMED_RESPONSE")
            build = [j for j in jobs if j.get("name") == "build"]
            deploy = [j for j in jobs if j.get("name") == "deploy"]
            if len(build) != 1 or len(deploy) > 1:
                return result("UNKNOWN", "MALFORMED_RESPONSE")
            if build[0].get("conclusion") == "failure" and info.get("conclusion") == "success":
                return result("UNKNOWN", "EVIDENCE_MISMATCH")
            if build[0].get("conclusion") == "failure":
                return result("FAILED", "DEPLOY_FAILED")
            if not deploy or build[0].get("status") != "completed" or deploy[0].get("status") != "completed":
                return result("PENDING", "RUN_PENDING")
            if deploy[0].get("conclusion") == "failure" and info.get("conclusion") == "success":
                return result("UNKNOWN", "EVIDENCE_MISMATCH")
            if deploy[0].get("conclusion") == "failure":
                return result("FAILED", "DEPLOY_FAILED")
            if (build[0].get("conclusion") == "success" and deploy[0].get("conclusion") == "success"
                    and info.get("status") == "completed" and info.get("conclusion") == "success"):
                return result("SUCCESS", "DEPLOY_SUCCESS")
            return result("UNKNOWN", "EVIDENCE_MISMATCH")
        return result("PENDING", "NO_MATCH")
    except subprocess.TimeoutExpired:
        return result("UNKNOWN", "API_TIMEOUT")
    except json.JSONDecodeError:
        return result("UNKNOWN", "MALFORMED_RESPONSE")
    except (OSError, ValueError, TypeError, AttributeError):
        return result("UNKNOWN", "API_FAILURE")


if __name__ == "__main__":
    main()
