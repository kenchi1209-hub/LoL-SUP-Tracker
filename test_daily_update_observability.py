import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from daily_update_observability import append_event, check_pages_status, classify_pages_status, create_log, safe_child_output


class DailyUpdateObservabilityTests(unittest.TestCase):
    def test_pages_read_only_query_requires_verified_run_and_jobs(self):
        import json
        from types import SimpleNamespace
        sha, other, public = 'a' * 40, 'b' * 40, 'c' * 40
        def fixture(*, private=sha, status='completed', build='success', deploy='success',
                    run_conclusion='success', marker=True, marker_id=123, marker_public=public,
                    api_failure=False, timeout=False, malformed=False, empty=False):
            calls = []
            def runner(args, **kwargs):
                calls.append(args)
                if timeout: raise subprocess.TimeoutExpired('gh', 1)
                if api_failure: return SimpleNamespace(returncode=1, stdout='', stderr='token=secret')
                if args[1:3] == ['run', 'list']:
                    value = [] if empty else [{'databaseId': 123, 'status': status, 'conclusion': run_conclusion, 'headSha': public}]
                    return SimpleNamespace(returncode=0, stdout='not-json' if malformed else json.dumps(value))
                if '--log' in args:
                    text = f'PAGES_INPUT_PRIVATE_SHA={private} PUBLIC_SHA={marker_public} RUN_ID={marker_id}' if marker else 'no evidence'
                    return SimpleNamespace(returncode=0, stdout=text)
                jobs = [{'name': 'build', 'status': 'completed' if build else 'in_progress', 'conclusion': build}]
                if deploy is not None: jobs.append({'name': 'deploy', 'status': 'completed' if deploy else 'in_progress', 'conclusion': deploy})
                return SimpleNamespace(returncode=0, stdout=json.dumps({'databaseId': 123, 'headSha': public, 'status': status, 'conclusion': run_conclusion, 'jobs': jobs}))
            return runner, calls
        cases = [
            ({}, 'SUCCESS', 'DEPLOY_SUCCESS'),
            ({'deploy':'failure','run_conclusion':'failure'}, 'FAILED', 'DEPLOY_FAILED'),
            ({'build':'failure','deploy':None,'run_conclusion':'failure'}, 'FAILED', 'DEPLOY_FAILED'),
            ({'status':'in_progress','build':None,'deploy':None,'run_conclusion':None}, 'PENDING', 'RUN_PENDING'),
            ({'status':'in_progress','deploy':None,'run_conclusion':None}, 'PENDING', 'RUN_PENDING'),
            ({'status':'in_progress','deploy':None,'build':'success','run_conclusion':None}, 'PENDING', 'RUN_PENDING'),
            ({'status':'in_progress','deploy':None,'build':None,'run_conclusion':None}, 'PENDING', 'RUN_PENDING'),
            ({'status':'in_progress','deploy':'','run_conclusion':None}, 'PENDING', 'RUN_PENDING'),
            ({'empty':True}, 'PENDING', 'NO_MATCH'),
            ({'private':other}, 'PENDING', 'NO_MATCH'),
            ({'marker':False}, 'UNKNOWN', 'METADATA_MISSING'),
            ({'marker_id':999}, 'UNKNOWN', 'EVIDENCE_MISMATCH'),
            ({'marker_public':other}, 'UNKNOWN', 'EVIDENCE_MISMATCH'),
            ({'api_failure':True}, 'UNKNOWN', 'API_FAILURE'),
            ({'timeout':True}, 'UNKNOWN', 'API_TIMEOUT'),
            ({'malformed':True}, 'UNKNOWN', 'MALFORMED_RESPONSE'),
            ({'build':'failure','run_conclusion':'success'}, 'UNKNOWN', 'EVIDENCE_MISMATCH'),
        ]
        for options, expected, reason in cases:
            with self.subTest(options=options):
                runner, calls = fixture(**options)
                self.assertEqual(check_pages_status(sha, 'owner/repo', runner=runner), {'state': expected, 'reason': reason})
                self.assertTrue(all(call[1:3] in (['run','list'], ['run','view']) for call in calls))
        runner, calls = fixture()
        self.assertEqual(check_pages_status('invalid', 'owner/repo', runner=runner)['state'], 'UNKNOWN')
        self.assertEqual(calls, [])

    def test_sensitive_child_output_is_not_persisted(self):
        secrets = [
            "abc-puuid-secret-123", "RGAPI-secret-123", "Bearer secret-123",
            "Authorization: secret-123", "https://example.invalid/?token=secret-123",
        ]
        for secret in secrets:
            for stderr in (False, True):
                with self.subTest(secret=secret, stderr=stderr):
                    self.assertNotIn(secret, safe_child_output(secret, stderr=stderr))

    def test_only_strictly_allowlisted_facts_are_kept(self):
        self.assertEqual(safe_child_output("Fight Detail matches: 733"), "Fight Detail matches: 733")
        self.assertEqual(safe_child_output("JP1_12345"), "Match ID: JP1_12345")
        self.assertEqual(safe_child_output("JP1_12345 secret"), "[output omitted]")
        self.assertEqual(safe_child_output("HTTPError 403 URL https://example/?token=secret", stderr=True), "[stderr] HTTP status 403")

    def test_pages_requires_matching_private_sha_and_both_jobs(self):
        sha = "a" * 40
        other = "b" * 40
        run = {"private_sha": sha, "status": "completed", "build_conclusion": "success", "deploy_conclusion": "success"}
        self.assertEqual(classify_pages_status(sha, [run]), "SUCCESS")
        self.assertEqual(classify_pages_status(other, [run]), "PENDING")
        self.assertEqual(classify_pages_status(sha, [{**run, "deploy_conclusion": "failure"}]), "FAILED")
        self.assertEqual(classify_pages_status(sha, [{**run, "status": "in_progress"}]), "PENDING")
        self.assertEqual(classify_pages_status(sha, [{**run, "private_sha": None}]), "UNKNOWN")
        self.assertEqual(classify_pages_status(sha, [run], query_error=True), "UNKNOWN")
        self.assertEqual(classify_pages_status(sha, [run], timed_out=True), "UNKNOWN")
        self.assertEqual(classify_pages_status(sha, []), "PENDING")
        self.assertEqual(classify_pages_status(sha, [{**run, "private_sha": other}, run]), "PENDING")
        self.assertEqual(classify_pages_status(sha, [{**run, "private_sha": None}, run]), "UNKNOWN")
        self.assertEqual(classify_pages_status(sha, [{**run, "status": "in_progress"}, run]), "PENDING")

    def test_workflow_records_actual_inputs_before_build(self):
        workflow = (Path(__file__).parent / '.github' / 'workflows' / 'deploy.yml').read_text(encoding='utf-8')
        marker = workflow.index('name: Record Pages build inputs')
        self.assertLess(marker, workflow.index('name: Build static site from PrivateData'))
        self.assertIn('git -C private-data rev-parse HEAD', workflow[marker:])
        self.assertIn('git -C tracker rev-parse HEAD', workflow[marker:])
        self.assertIn('github.run_id', workflow[marker:])

    def test_log_is_unique_jst_and_rotation_stays_in_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "daily_update"
            logs.mkdir()
            old = logs / "2020-01-01_00-00-00.log"
            recent = logs / "2026-11-17_00-00-00.log"
            keep = logs / "important.txt"
            outside = root / "2020-01-01_00-00-00.log"
            for path in (old, recent, keep, outside): path.write_text("preserve", encoding="utf-8")
            os.utime(old, (1, 1))
            now = datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)
            os.utime(recent, (now.timestamp(), now.timestamp()))
            one = create_log(logs, now)
            two = create_log(logs, now)
            self.assertEqual(one.name, "2026-11-18_00-00-00.log")
            self.assertEqual(two.name, "2026-11-18_00-00-00_1.log")
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(keep.exists())
            self.assertTrue(outside.exists())
            self.assertIn("+09:00 START STARTED", one.read_text(encoding="utf-8"))

    def test_events_reject_untrusted_output_and_log_failure_is_raised(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = create_log(temporary)
            append_event(log, "DATA_UPDATE", "SUCCESS", "0")
            for secret in ("PUUID-SECRET", "RGAPI-secret", "Bearer secret", "Authorization: secret", "https://x/?token=secret"):
                with self.assertRaises(ValueError): append_event(log, "PUSH", "SUCCESS", secret)
                self.assertNotIn(secret, log.read_text(encoding="utf-8"))
            with patch.object(Path, "open", side_effect=OSError("unwritable")):
                with self.assertRaises(OSError): append_event(log, "PUSH", "SUCCESS")

    def test_log_directory_is_git_ignored(self):
        root = Path(__file__).resolve().parent
        result = subprocess.run(["git", "check-ignore", "logs/daily_update/2026-11-17_00-00-00.log"], cwd=root, capture_output=True)
        self.assertEqual(result.returncode, 0)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell fixture")
    def test_checked_native_exit_and_stderr(self):
        script = Path(__file__).with_name("daily_update.ps1")
        preamble = r'''
$script:ActiveStage = ''
function Write-Audit { param($Event,$State,$Value) }
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:FIXTURE_SCRIPT,[ref]$tokens,[ref]$errors)
if ($errors.Count) { exit 90 }
$function=$ast.FindAll({param($x) $x -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $x.Name -eq 'Invoke-Checked'},$true)[0]
Invoke-Expression $function.Extent.Text
$ErrorActionPreference='Stop'
try { Invoke-Checked -Command $env:FIXTURE_PYTHON -CommandArguments @('-c', $env:FIXTURE_CHILD); exit 0 }
catch { [Console]::Error.WriteLine($_.Exception.Message); exit 7 }
'''
        for child, expected in (("print('ok')", 0), ("import sys; sys.stderr.write('diagnostic\\n')", 0), ("import sys; sys.exit(5)", 7)):
            env = dict(os.environ, FIXTURE_SCRIPT=str(script), FIXTURE_PYTHON=sys.executable, FIXTURE_CHILD=child)
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", preamble], env=env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, expected, result.stderr.decode(errors="replace"))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell fixture")
    def test_powershell_nonterminating_error_is_caught(self):
        script = Path(__file__).with_name("daily_update.ps1")
        code = r'''
$script:ActiveStage = ''
function Write-Audit { param($Event,$State,$Value) }
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:FIXTURE_SCRIPT,[ref]$tokens,[ref]$errors)
$function=$ast.FindAll({param($x) $x -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $x.Name -eq 'Invoke-Checked'},$true)[0]
Invoke-Expression $function.Extent.Text
function FixtureNonterminating { Write-Error 'fixture' }
$ErrorActionPreference='Stop'; $global:LASTEXITCODE=0
try { Invoke-Checked FixtureNonterminating; exit 1 } catch { exit 0 }
'''
        env = dict(os.environ, FIXTURE_SCRIPT=str(script))
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", code], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell fixture")
    def test_failed_preflight_writes_safe_log_and_summary_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(Path(__file__).with_name("daily_update.ps1")),
                "-PublicRepo", str(root), "-PrivateRepo", str(root / "missing"),
                "-PythonCommand", sys.executable,
            ], capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            stdout = result.stdout.decode(errors="replace")
            self.assertIn("Daily Update Result", stdout)
            self.assertIn("Pages Deploy     : UNKNOWN", stdout)
            logs = list((root / "logs" / "daily_update").glob("*.log"))
            self.assertEqual(len(logs), 1)
            content = logs[0].read_text(encoding="utf-8")
            self.assertIn("DATA_UPDATE UNKNOWN", content)
            self.assertIn("PUSH SKIPPED", content)
            self.assertIn("PAGES UNKNOWN", content)
            self.assertIn("END FAILED 1", content)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell fixture")
    def test_log_write_failure_is_warning_not_raw_fallback(self):
        script = Path(__file__).with_name("daily_update.ps1")
        code = r'''
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:FIXTURE_SCRIPT,[ref]$tokens,[ref]$errors)
$f=$ast.FindAll({param($x) $x -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $x.Name -eq 'Write-Audit'},$true)[0]
Invoke-Expression $f.Extent.Text
$PythonCommand=$env:FIXTURE_PYTHON; $script:AuditHelper='not-an-existing-helper.py'; $script:AuditLog='not-a-real-log.log'
Write-Audit 'DATA_UPDATE' 'SUCCESS'
'''
        env = dict(os.environ, FIXTURE_SCRIPT=str(script), FIXTURE_PYTHON=sys.executable)
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", code], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertIn("log write failed", result.stdout.decode(errors="replace"))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell fixture")
    def test_mocked_daily_update_success_and_stage_failures(self):
        script = Path(__file__).with_name("daily_update.ps1")
        code = r'''
function global:git {
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'rev-parse') {
        if ($args[1] -eq 'HEAD') {
            $global:fixtureHeadCount++
            if ($env:FIXTURE_FAILURE -eq 'sha' -and $global:fixtureHeadCount -gt 1) { $global:LASTEXITCODE=1; return }
        }
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; return
    }
    if ($args[0] -eq 'diff' -and $args -contains '--cached' -and $args -contains '--quiet') { $global:LASTEXITCODE=1; return }
    if ($args[0] -eq 'commit' -and $env:FIXTURE_FAILURE -eq 'commit') { $global:LASTEXITCODE=3; return }
    if ($args[0] -eq 'push' -and $env:FIXTURE_FAILURE -eq 'push') { $global:LASTEXITCODE=4; return }
}
function global:FixturePython {
    if ($args[0] -like '*daily_update_observability.py' -and $args[1] -eq 'pages') {
        Write-Host 'FIXTURE_PAGES_QUERY'
        switch ($env:FIXTURE_FAILURE) {
            'pages-success' { '{"state":"SUCCESS","reason":"DEPLOY_SUCCESS"}' }
            'pages-pending' { '{"state":"PENDING","reason":"RUN_PENDING"}' }
            'pages-failed' { '{"state":"FAILED","reason":"DEPLOY_FAILED"}' }
            default { '{"state":"UNKNOWN","reason":"API_FAILURE"}' }
        }
        $global:LASTEXITCODE=0; return
    }
    if ($args[0] -like '*daily_update_observability.py') { & $env:FIXTURE_PYTHON @args; return }
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'main.py') {
        'PUUID-SECRET RGAPI-secret Bearer-secret https://example.invalid/?token=secret'
        if ($env:FIXTURE_FAILURE -eq 'main') { $global:LASTEXITCODE=5 }
    }
    if ($args[0] -eq 'verify_fight_raw_completeness.py' -and $env:FIXTURE_FAILURE -eq 'fight') { $global:LASTEXITCODE=6 }
}
$global:fixtureHeadCount=0
& $env:FIXTURE_SCRIPT -PublicRepo $env:FIXTURE_PUBLIC -PrivateRepo $env:FIXTURE_PRIVATE -PythonCommand FixturePython
'''
        for failure in ("", "main", "fight", "commit", "push", "sha", "pages-success", "pages-pending", "pages-failed"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                private = root / "private"
                private.mkdir()
                env = dict(os.environ, FIXTURE_SCRIPT=str(script), FIXTURE_PYTHON=sys.executable,
                           FIXTURE_PUBLIC=str(root), FIXTURE_PRIVATE=str(private), FIXTURE_FAILURE=failure)
                result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code], env=env, capture_output=True, timeout=60)
                failed = failure in ("main", "fight", "commit", "push")
                self.assertEqual(result.returncode, 1 if failed else 0, (result.stdout + result.stderr).decode(errors="replace"))
                self.assertEqual(b'FIXTURE_PAGES_QUERY' in result.stdout, not failed and failure != 'sha')
                logs = list((root / "logs" / "daily_update").glob("*.log"))
                self.assertEqual(len(logs), 1)
                content = logs[0].read_text(encoding="utf-8")
                for secret in ("PUUID-SECRET", "RGAPI-secret", "Bearer-secret", "token=secret"):
                    self.assertNotIn(secret, content)
                stage = {"main": "DATA_UPDATE", "fight": "FIGHT_VALIDATION", "commit": "COMMIT", "push": "PUSH"}.get(failure)
                if stage: self.assertIn(stage + " FAILED", content, (result.stdout + result.stderr).decode(errors="replace"))
                else:
                    self.assertIn("DATA_UPDATE SUCCESS", content)
                    self.assertIn("FIGHT_VALIDATION SUCCESS", content)
                    self.assertIn("PUSH SUCCESS", content)
                    if failure == 'sha': self.assertIn("PRIVATE_SHA UNKNOWN", content)
                    else: self.assertIn("PRIVATE_SHA SUCCESS " + "a" * 40, content)
                pages_state = {'pages-success':'SUCCESS', 'pages-pending':'PENDING', 'pages-failed':'FAILED'}.get(failure, 'UNKNOWN')
                self.assertIn("PAGES " + pages_state, content)


if __name__ == "__main__":
    unittest.main()
