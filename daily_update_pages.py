"""Bounded, fail-closed build-only dispatch. Never persist GitHub output."""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from daily_update_observability import _SHA, append_event, check_pages_status

RUN_LIMIT = 20
ACTIVE = ('queued', 'in_progress', 'waiting', 'pending', 'requested')
RUN_FIELDS = 'databaseId,status,conclusion,headSha,displayTitle,event'


def publish(sha, repo='kenchi1209-hub/LoL-SUP-Tracker', *, data='UNKNOWN',
            fight='UNKNOWN', push='SKIPPED', unchanged=False, runner=subprocess.run,
            clock=time.monotonic, sleep=time.sleep, max_seconds=180, interval=10,
            preflight_seconds=30, dispatch_seconds=10, diagnostic=None):
    def result(state='UNKNOWN', reason='CONDITIONS_NOT_MET', trigger='SKIPPED', run_id=None):
        return dict(state=state, reason=reason, trigger=trigger, run_id=run_id)

    if data != 'SUCCESS' or fight != 'SUCCESS' or not (push == 'SUCCESS' or (push == 'SKIPPED' and unchanged)):
        return result()
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return result(reason='SHA_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        return result(reason='MALFORMED_RESPONSE')
    sha = sha.lower()
    deadline = clock() + preflight_seconds

    def record(stage, started, code):
        if diagnostic is not None:
            diagnostic(stage, max(0, int((clock() - started) * 1000)), code)

    def gh(stage, *args):
        started = clock()
        code = 'FAILED'
        remaining = deadline - clock()
        try:
            if remaining <= 0:
                raise subprocess.TimeoutExpired('gh', 0)
            response = runner(['gh', *args], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=min(remaining, 10), check=False)
            if response.returncode:
                raise OSError('GitHub command failed')
            code = 'SUCCESS'
            return response.stdout
        except subprocess.TimeoutExpired:
            code = 'API_TIMEOUT'
            raise
        finally:
            record(stage, started, code)

    prior_ids = set()

    def list_runs(stage, *filters):
        runs = json.loads(gh(stage, 'run', 'list', '--repo', repo, '--workflow', 'deploy.yml',
                             '--branch', 'build', '--limit', str(RUN_LIMIT), '--json', RUN_FIELDS, *filters))
        if not isinstance(runs, list) or len(runs) > RUN_LIMIT or any(
            not isinstance(run, dict) or type(run.get('databaseId')) is not int
            or not _SHA.fullmatch(str(run.get('headSha', '')))
            or run.get('status') not in (*ACTIVE, 'completed') for run in runs
        ):
            raise ValueError('Invalid run list')
        return runs

    def requested_sha(run):
            title = re.fullmatch(r'Pages PrivateData \| ([0-9a-fA-F]{40})', str(run.get('displayTitle', '')))
            return title.group(1).lower() if title and run.get('event') == 'workflow_dispatch' else None

    def verify(run, *, tracking):
        started = clock()
        evidence = verify_run(run, tracking=tracking)
        record('SHA_MATCH', started, evidence['reason'])
        return evidence

    def verify_run(run, *, tracking):
            if tracking and run.get('conclusion') in ('failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'):
                info = json.loads(gh('TRACKING', 'run', 'view', str(run['databaseId']), '--repo', repo,
                                     '--json', 'databaseId,headSha,status,conclusion,jobs'))
                if (info.get('databaseId') != run['databaseId'] or info.get('headSha') != run['headSha']
                        or info.get('status') != 'completed' or info.get('conclusion') != run['conclusion']):
                    return result(reason='EVIDENCE_MISMATCH', trigger='UNKNOWN')
                jobs = info.get('jobs')
                if not isinstance(jobs, list) or not any(j.get('name') == 'build' for j in jobs):
                    return result(reason='METADATA_MISSING', trigger='UNKNOWN')
                return result('FAILED', 'DEPLOY_FAILED', run_id=run['databaseId'])
            evidence = check_pages_status(sha, repo, runner=runner, clock=clock,
                                          max_seconds=min(20, max(0, deadline-clock())), expected_run=run)
            evidence.update(trigger='UNKNOWN', run_id=run['databaseId'])
            if evidence['state'] == 'UNKNOWN':
                return evidence
            if evidence['reason'] == 'NO_MATCH' and requested_sha(run) == sha:
                return result(reason='EVIDENCE_MISMATCH', trigger='UNKNOWN')
            evidence['trigger'] = {'SUCCESS': 'ALREADY_DEPLOYED', 'PENDING': 'ALREADY_RUNNING'}.get(evidence['state'], 'SKIPPED')
            return evidence

    def preflight():
        runs = list_runs('RUN_LIST')
        prior_ids.update(run['databaseId'] for run in runs)
        active = [run for run in runs if run['status'] != 'completed']
        if len(runs) == RUN_LIMIT:
            # Older active runs can outlive the recent history window.
            for status in ACTIVE:
                batch = list_runs('RUN_LIST', '--status', status)
                if len(batch) == RUN_LIMIT:
                    return result(reason='METADATA_MISSING', trigger='UNKNOWN')
                prior_ids.update(run['databaseId'] for run in batch)
                active.extend(run for run in batch if run['status'] != 'completed')
        for run in active:
            if requested_sha(run) == sha:
                return result('PENDING', 'RUN_PENDING', 'ALREADY_RUNNING', run['databaseId'])
        if any(requested_sha(run) is None for run in active):
            return result(reason='METADATA_MISSING', trigger='UNKNOWN')
        # Only the newest successful workflow can establish current publication.
        for run in runs:
            if run['status'] == 'completed' and run['conclusion'] == 'success':
                if requested_sha(run) in (None, sha):
                    evidence = verify(run, tracking=False)
                    if evidence['state'] in ('SUCCESS', 'UNKNOWN'):
                        return evidence
                break
        return result('PENDING', 'NO_MATCH')

    triggered = False
    run_id = None
    try:
        try:
            gh('AUTH', 'auth', 'status', '--hostname', 'github.com')
            permissions = json.loads(gh('PERMISSIONS', 'api', f'repos/{repo}')).get('permissions', {})
            workflow = json.loads(gh('WORKFLOW', 'api', f'repos/{repo}/actions/workflows/deploy.yml'))
            if not permissions.get('push') or workflow.get('state') != 'active':
                return result(reason='AUTH_FAILURE', trigger='UNKNOWN')
        except (OSError, ValueError, AttributeError):
            return result(reason='AUTH_FAILURE', trigger='UNKNOWN')
        current = preflight()
        if current['state'] in ('SUCCESS', 'UNKNOWN'):
            return current
        if current['trigger'] != 'ALREADY_RUNNING':
            deadline = clock() + dispatch_seconds
            try:
                gh('DISPATCH', 'workflow', 'run', 'deploy.yml', '--repo', repo, '--ref', 'build',
                   '-f', 'private_data_pushed=true', '-f', f'private_data_sha={sha}')
                triggered = True
            except (OSError, subprocess.TimeoutExpired):
                # Dispatch may have reached GitHub even if the response was lost.
                return result(reason='DISPATCH_UNKNOWN', trigger='UNKNOWN')
        else:
            run_id = current['run_id']
        deadline = clock() + max_seconds
        trigger = 'TRIGGERED' if triggered else 'ALREADY_RUNNING'
        while clock() < deadline:
            for run in list_runs('TRACKING'):
                if requested_sha(run) != sha or (run_id is not None and run['databaseId'] != run_id):
                    continue
                if run_id is None and run['databaseId'] in prior_ids:
                    continue
                run_id = run['databaseId']
                if run['status'] == 'completed':
                    current = verify(run, tracking=True)
                    if current['reason'] == 'API_TIMEOUT':
                        return result('PENDING', 'WAIT_TIMEOUT', trigger, run_id)
                    return dict(current, trigger=trigger)
                break
            sleep(min(interval, max(0, deadline-clock())))
        return result('PENDING', 'WAIT_TIMEOUT' if run_id else 'RUN_NOT_FOUND',
                      'TRIGGERED' if triggered else 'ALREADY_RUNNING', run_id)
    except subprocess.TimeoutExpired:
        if triggered or run_id is not None:
            return result('PENDING', 'WAIT_TIMEOUT', 'TRIGGERED' if triggered else 'ALREADY_RUNNING', run_id)
        return result(reason='API_TIMEOUT', trigger='UNKNOWN')
    except (OSError, ValueError, TypeError, AttributeError):
        return result(reason='API_FAILURE', trigger='TRIGGERED' if triggered else 'UNKNOWN', run_id=run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--fight', required=True)
    parser.add_argument('--push', required=True)
    parser.add_argument('--unchanged', action='store_true')
    parser.add_argument('--lock-directory', required=True)
    parser.add_argument('--log-file')
    args = parser.parse_args()

    def diagnostic(stage, elapsed_ms, code):
        if args.log_file:
            try:
                append_event(args.log_file, 'PAGES_DIAGNOSTIC', 'UNKNOWN', f'{stage} {elapsed_ms} {code}')
            except (ValueError, OSError):
                pass
    # OS lock is released on process exit, including interruption. Serialize
    # all local Daily Update dispatch checks, without stale lock cleanup races.
    try:
        directory = Path(args.lock_directory)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'pages-dispatch.lock').open('a+b') as lock:
            lock.seek(0)
            if __import__('os').name == 'nt':
                import msvcrt
                lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            output = publish(args.sha, data=args.data, fight=args.fight,
                             push=args.push, unchanged=args.unchanged, diagnostic=diagnostic)
    except OSError:
        output = dict(state='UNKNOWN', reason='API_FAILURE', trigger='UNKNOWN', run_id=None)
    print(json.dumps(output, separators=(',', ':')))


if __name__ == '__main__':
    main()
