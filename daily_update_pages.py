"""Bounded, fail-closed build-only dispatch. Never persist GitHub output."""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from daily_update_observability import _SHA, check_pages_status


def publish(sha, repo='kenchi1209-hub/LoL-SUP-Tracker', *, data='UNKNOWN',
            fight='UNKNOWN', push='SKIPPED', unchanged=False, runner=subprocess.run,
            clock=time.monotonic, sleep=time.sleep, max_seconds=180, interval=10):
    def result(state='UNKNOWN', reason='CONDITIONS_NOT_MET', trigger='SKIPPED', run_id=None):
        return dict(state=state, reason=reason, trigger=trigger, run_id=run_id)

    if data != 'SUCCESS' or fight != 'SUCCESS' or not (push == 'SUCCESS' or (push == 'SKIPPED' and unchanged)):
        return result()
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return result(reason='SHA_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        return result(reason='MALFORMED_RESPONSE')
    sha = sha.lower()
    deadline = clock() + max_seconds

    def gh(*args):
        remaining = deadline - clock()
        if remaining <= 0:
            raise subprocess.TimeoutExpired('gh', max_seconds)
        response = runner(['gh', *args], capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=min(remaining, 10), check=False)
        if response.returncode:
            raise OSError('GitHub command failed')
        return response.stdout

    prior_ids = set()

    def discover():
        runs = json.loads(gh('run', 'list', '--repo', repo, '--workflow', 'deploy.yml',
                             '--branch', 'build', '--limit', '1000', '--json',
                             'databaseId,status,conclusion,headSha,displayTitle,event'))
        if not isinstance(runs, list) or len(runs) >= 1000:
            return result(reason='METADATA_MISSING', trigger='UNKNOWN')
        if not triggered:
            prior_ids.update(run.get('databaseId') for run in runs if isinstance(run, dict) and type(run.get('databaseId')) is int)
        for run in runs:
            if (not isinstance(run, dict) or type(run.get('databaseId')) is not int
                    or not _SHA.fullmatch(str(run.get('headSha', '')))):
                return result(reason='MALFORMED_RESPONSE', trigger='UNKNOWN')
            if triggered and run['databaseId'] in prior_ids:
                continue
            if run.get('status') not in ('queued', 'in_progress', 'completed', 'waiting', 'pending', 'requested'):
                return result(reason='MALFORMED_RESPONSE', trigger='UNKNOWN')
            title = re.fullmatch(r'Pages PrivateData \| ([0-9a-fA-F]{40})', str(run.get('displayTitle', '')))
            # Only workflow_dispatch titles carry a requested PrivateData SHA.
            requested = title.group(1).lower() if title and run.get('event') == 'workflow_dispatch' else None
            if requested and requested != sha:
                continue
            if requested == sha and run.get('status') != 'completed':
                return result('PENDING', 'RUN_PENDING', 'ALREADY_RUNNING', run['databaseId'])
            if requested == sha and run.get('status') == 'completed' and run.get('conclusion') in ('failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'):
                info = json.loads(gh('run', 'view', str(run['databaseId']), '--repo', repo,
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
            if evidence['reason'] == 'NO_MATCH':
                # A requested SHA must agree with actual checkout evidence.
                if requested == sha:
                    return result(reason='EVIDENCE_MISMATCH', trigger='UNKNOWN')
                continue
            evidence['trigger'] = {'SUCCESS': 'ALREADY_DEPLOYED', 'PENDING': 'ALREADY_RUNNING'}.get(evidence['state'], 'SKIPPED')
            return evidence
        return result('PENDING', 'NO_MATCH')

    triggered = False
    run_id = None
    try:
        try:
            gh('auth', 'status', '--hostname', 'github.com')
            permissions = json.loads(gh('api', f'repos/{repo}')).get('permissions', {})
            workflow = json.loads(gh('api', f'repos/{repo}/actions/workflows/deploy.yml'))
            if not permissions.get('push') or workflow.get('state') != 'active':
                return result(reason='AUTH_FAILURE', trigger='UNKNOWN')
        except (OSError, ValueError, AttributeError):
            return result(reason='AUTH_FAILURE', trigger='UNKNOWN')
        current = discover()
        if current['state'] in ('SUCCESS', 'UNKNOWN'):
            return current
        if current['trigger'] != 'ALREADY_RUNNING':
            try:
                gh('workflow', 'run', 'deploy.yml', '--repo', repo, '--ref', 'build',
                   '-f', 'private_data_pushed=true', '-f', f'private_data_sha={sha}')
                triggered = True
            except (OSError, subprocess.TimeoutExpired):
                # Dispatch may have reached GitHub even if the response was lost.
                return result(reason='DISPATCH_FAILED', trigger='UNKNOWN')
        else:
            run_id = current['run_id']
        while clock() < deadline:
            current = discover()
            if current['run_id'] is not None:
                run_id = current['run_id']
            current['trigger'] = 'TRIGGERED' if triggered else 'ALREADY_RUNNING'
            if current['state'] in ('SUCCESS', 'FAILED', 'UNKNOWN'):
                return current
            sleep(min(interval, max(0, deadline-clock())))
        return result('PENDING', 'WAIT_TIMEOUT' if run_id else 'RUN_NOT_FOUND',
                      'TRIGGERED' if triggered else 'ALREADY_RUNNING', run_id)
    except subprocess.TimeoutExpired:
        return result(reason='API_TIMEOUT', trigger='TRIGGERED' if triggered else 'UNKNOWN', run_id=run_id)
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
    args = parser.parse_args()
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
                             push=args.push, unchanged=args.unchanged)
    except OSError:
        output = dict(state='UNKNOWN', reason='API_FAILURE', trigger='UNKNOWN', run_id=None)
    print(json.dumps(output, separators=(',', ':')))


if __name__ == '__main__':
    main()
