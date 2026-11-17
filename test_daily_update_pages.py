import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from daily_update_pages import publish
from daily_update_observability import check_pages_status

SHA, OTHER, PUBLIC = 'a'*40, 'b'*40, 'c'*40


class Fixture:
    def __init__(self, before=None, after='success', fail=None):
        self.before, self.after, self.fail = before, after, fail
        self.calls = []
        self.dispatched = False
        self.now = 0

    def clock(self): return self.now
    def sleep(self, seconds): self.now += seconds

    def runner(self, args, **kwargs):
        self.calls.append(args)
        kind = ' '.join(args[1:3])
        if kind == self.fail:
            return SimpleNamespace(returncode=1, stdout='Bearer SECRET', stderr='RGAPI-secret')
        if kind == 'auth status': value = ''
        elif args[1] == 'api':
            value = json.dumps({'state':'active'} if 'workflows' in args[2] else {'permissions':{'push':True}})
        elif kind == 'workflow run':
            self.dispatched = True
            value = ''
        elif kind == 'run list':
            state = self.after if self.dispatched else self.before
            completed = state not in ('running', 'other-running')
            value = json.dumps([] if state is None else [dict(databaseId=124 if self.dispatched else 123, headSha=PUBLIC,
                displayTitle='Pages PrivateData | '+(OTHER if state in ('other','other-running') else SHA),
                event='workflow_dispatch', status='completed' if completed else 'in_progress',
                conclusion='failure' if state == 'failure' else 'success' if completed else None)])
        elif '--log' in args:
            value = f'PAGES_INPUT_PRIVATE_SHA={SHA} PUBLIC_SHA={PUBLIC} RUN_ID={124 if self.dispatched else 123}'
        else:
            state = self.after if self.dispatched else self.before
            value = json.dumps(dict(databaseId=124 if self.dispatched else 123, headSha=PUBLIC, status='completed',
                conclusion='failure' if state == 'failure' else 'success', jobs=[
                dict(name='build',status='completed',conclusion='success'),
                dict(name='deploy',status='completed',conclusion='failure' if state == 'failure' else 'success')]))
        return SimpleNamespace(returncode=0,stdout=value,stderr='')

    def publish(self, **kwargs):
        opts = dict(data='SUCCESS',fight='SUCCESS',push='SUCCESS',runner=self.runner,
                    clock=self.clock,sleep=self.sleep,max_seconds=30,interval=10)
        opts.update(kwargs)
        return publish(opts.pop('sha',SHA), **opts)


class DispatchTests(unittest.TestCase):
    def test_success_dispatch_and_verified_completion(self):
        f=Fixture(); out=f.publish()
        self.assertEqual((out['state'],out['trigger'],out['run_id']),('SUCCESS','TRIGGERED',124))
        dispatch=next(c for c in f.calls if c[1:3]==['workflow','run'])
        self.assertEqual(dispatch, ['gh','workflow','run','deploy.yml','--repo','kenchi1209-hub/LoL-SUP-Tracker','--ref','build','-f','private_data_pushed=true','-f','private_data_sha='+SHA])
        self.assertTrue(all(k in str(f.calls) for k in ('private_data_pushed=true',SHA)))

    def test_conditions_fail_without_any_github_calls(self):
        for opts in ({'data':'FAILED'},{'fight':'FAILED'},{'push':'FAILED'},{'push':'SKIPPED'}, {'sha':'UNKNOWN'}):
            with self.subTest(opts=opts):
                f=Fixture(); out=f.publish(**opts)
                self.assertEqual(out['trigger'],'SKIPPED'); self.assertFalse(f.calls)

    def test_no_change_published_or_unpublished(self):
        f=Fixture(before='success'); out=f.publish(push='SKIPPED',unchanged=True)
        self.assertEqual(out['trigger'],'ALREADY_DEPLOYED'); self.assertFalse(f.dispatched)
        f=Fixture(); out=f.publish(push='SKIPPED',unchanged=True)
        self.assertEqual(out['trigger'],'TRIGGERED'); self.assertTrue(f.dispatched)

    def test_existing_running_and_success_do_not_dispatch(self):
        for state, expected in [('running','ALREADY_RUNNING'),('success','ALREADY_DEPLOYED')]:
            f=Fixture(before=state); out=f.publish()
            self.assertEqual(out['trigger'],expected); self.assertFalse(f.dispatched)

    def test_api_auth_dispatch_failure_fail_closed(self):
        for command, reason in [('auth status','AUTH_FAILURE'),('api repos/kenchi1209-hub/LoL-SUP-Tracker','AUTH_FAILURE'),('run list','API_FAILURE'),('workflow run','DISPATCH_FAILED')]:
            with self.subTest(command=command):
                f=Fixture(fail=command); out=f.publish()
                self.assertEqual(out['state'],'UNKNOWN'); self.assertEqual(out['reason'],reason)
                self.assertFalse(f.dispatched)
                self.assertNotIn('SECRET',str(out))

    def test_dispatch_success_run_not_found_and_running_timeout(self):
        for after,reason,run_id in [(None,'RUN_NOT_FOUND',None),('running','WAIT_TIMEOUT',124)]:
            f=Fixture(after=after); out=f.publish()
            self.assertEqual(out,dict(state='PENDING',reason=reason,trigger='TRIGGERED',run_id=run_id))
            self.assertEqual(f.now,30)

    def test_previous_failure_does_not_hide_new_dispatch(self):
        f=Fixture(before='failure'); out=f.publish()
        self.assertEqual((out['state'],out['run_id']),('SUCCESS',124))

    def test_deploy_failure_preserves_dispatch_result(self):
        f=Fixture(after='failure'); out=f.publish()
        self.assertEqual((out['state'],out['trigger']),('FAILED','TRIGGERED'))

    def test_other_sha_not_reused(self):
        for before in ('other','other-running'):
            f=Fixture(before=before); out=f.publish()
            self.assertTrue(f.dispatched); self.assertEqual(out['trigger'],'TRIGGERED')

    def test_missing_evidence_blocks_dispatch(self):
        f=Fixture(before='success')
        original=f.runner
        def runner(args,**kwargs):
            if '--log' in args: return SimpleNamespace(returncode=0,stdout='no evidence')
            return original(args,**kwargs)
        out=f.publish(runner=runner)
        self.assertEqual(out['state'],'UNKNOWN'); self.assertFalse(f.dispatched)

    def test_api_timeout_and_invalid_evidence(self):
        f=Fixture()
        def timeout(args, **kwargs): raise subprocess.TimeoutExpired('gh', 1)
        self.assertEqual(f.publish(runner=timeout)['reason'],'API_TIMEOUT')
        f=Fixture(before='success'); original=f.runner
        def mismatch(args, **kwargs):
            if '--log' in args:
                return SimpleNamespace(returncode=0,stdout=f'PAGES_INPUT_PRIVATE_SHA={OTHER} PUBLIC_SHA={PUBLIC} RUN_ID=123')
            return original(args, **kwargs)
        out=f.publish(runner=mismatch)
        self.assertEqual(out['reason'],'EVIDENCE_MISMATCH'); self.assertFalse(f.dispatched)

    def test_legacy_running_without_evidence_blocks_dispatch(self):
        f=Fixture(before='running'); original=f.runner
        def legacy(args, **kwargs):
            response=original(args,**kwargs)
            if args[1:3]==['run','list']:
                runs=json.loads(response.stdout); runs[0]['displayTitle']='manual run'
                response.stdout=json.dumps(runs)
            if '--log' in args: response.returncode=1
            return response
        out=f.publish(runner=legacy)
        self.assertEqual(out['state'],'UNKNOWN'); self.assertFalse(f.dispatched)

    def test_poll_api_failure_unknown(self):
        f=Fixture()
        original=f.runner
        def runner(args,**kwargs):
            if f.dispatched and args[1:3]==['run','list']: raise OSError('token secret')
            return original(args,**kwargs)
        out=f.publish(runner=runner)
        self.assertEqual((out['state'],out['trigger']),('UNKNOWN','TRIGGERED'))
        self.assertNotIn('secret',str(out))

    def test_workflow_sha_validation_and_build_only_guards(self):
        workflow=yaml.safe_load(Path('.github/workflows/deploy.yml').read_text())
        steps=workflow['jobs']['build']['steps']
        by_name={s['name']:s for s in steps}
        self.assertIn('inputs.private_data_sha',by_name['Checkout PrivateData']['with']['ref'])
        script=by_name['Verify requested PrivateData SHA']['run']
        # Execute actual workflow shell validation with an isolated fake git.
        with __import__('tempfile').TemporaryDirectory() as directory:
            root=Path(directory); git=root/'git'
            git.write_text('#!/bin/sh\nprintf "%s\\n" "'+SHA+'"\n')
            git.chmod(0o755)
            # Git for Windows bash consumes the same workflow script.
            bash=Path('C:/Program Files/Git/bin/bash.exe')
            if bash.exists():
                import os
                for requested,expected in [(SHA,0),(OTHER,1),('',0)]:
                    env=dict(os.environ,REQUESTED_SHA=requested)
                    runnable=script.replace('git -C private-data rev-parse HEAD', 'printf '+SHA)
                    proc=subprocess.run([str(bash),'-c',runnable],env=env,capture_output=True)
                    self.assertEqual(proc.returncode,expected)
        self.assertLess(steps.index(by_name['Verify requested PrivateData SHA']),steps.index(by_name['Build static site from PrivateData']))
        for name in ('Refresh Champion Registry','Fetch latest match data into PrivateData','Verify PrivateData completeness','Commit refreshed PrivateData','Commit Champion Registry only'):
            self.assertIn('!inputs.private_data_pushed',by_name[name]['if'])


if __name__=='__main__': unittest.main()
