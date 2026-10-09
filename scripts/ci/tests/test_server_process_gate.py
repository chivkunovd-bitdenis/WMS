"""WMS-652 direct server deployment cannot reach Docker without exact process CI."""
import copy
import importlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.ci.tests.test_verify_ci import REPO, SHA, Fixture
from scripts.ci.verify_ci import GateError

ROOT = Path(__file__).resolve().parents[3]


class ServerFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.artifacts = [{'id': 90, 'name': f'process-proof-{SHA}-10-1', 'expired': False,
                           'size_in_bytes': 2000, 'workflow_run': {'id': 10, 'head_sha': SHA}}]
        self.change_after_artifact = False

    def get(self, path):
        if '/artifacts?' in path:
            self.paths.append(path)
            data = copy.deepcopy({'total_count': len(self.artifacts), 'artifacts': self.artifacts})
            if self.change_after_artifact:
                self.run['run_attempt'] = 2
            return data
        return super().get(path)


class ServerGateTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.verify_server_process_ci')
        self.f = ServerFixture()

    def verify(self):
        return self.m.verify_server_ci(self.f.get, REPO, SHA)

    def test_exact_push_sha_and_successful_jobs_accept_without_process_artifacts(self):
        result = self.verify()
        self.assertEqual(result['sha'], SHA)
        self.assertGreaterEqual(self.f.run_reads, 4)
        self.assertTrue(any('/attempts/1/jobs?' in path for path in self.f.paths))
        # WMS-735 R10: per-attempt process artifacts are no longer required by the gate.
        self.assertFalse(any('/artifacts?' in path for path in self.f.paths))

    def test_every_required_extra_job_missing_failed_skipped_neutral_or_pending_refuses(self):
        for name in ['print-regressions', 'printer-windows', 'process-proof']:
            for state in ['missing', 'failure', 'skipped', 'neutral', 'cancelled', 'queued']:
                with self.subTest(name=name, state=state):
                    self.f = ServerFixture()
                    if state == 'missing':
                        self.f.jobs = [job for job in self.f.jobs if job['name'] != name]
                    else:
                        job = next(job for job in self.f.jobs if job['name'] == name)
                        job['status' if state == 'queued' else 'conclusion'] = state
                    with self.assertRaises(GateError): self.verify()

    def test_docs_only_may_skip_heavy_jobs_but_never_process_proof(self):
        self.f.changed = ['docs/requirements/WMS-704.md']
        for name in ['print-regressions', 'printer-windows']:
            next(job for job in self.f.jobs if job['name'] == name)['conclusion'] = 'skipped'
        result = self.verify()
        self.assertTrue(result['docs_only'])
        self.f = ServerFixture()
        self.f.changed = ['docs/requirements/WMS-704.md']
        next(job for job in self.f.jobs if job['name'] == 'process-proof')['conclusion'] = 'skipped'
        with self.assertRaises(GateError):
            self.verify()

    def test_red_latest_run_wrong_sha_or_non_push_etalon_refuses(self):
        for mutation in ['new-red', 'sha', 'event', 'branch']:
            with self.subTest(mutation=mutation):
                self.f = ServerFixture()
                if mutation == 'new-red':
                    self.f.runs.append({**self.f.run, 'id': 11, 'run_number': 2, 'conclusion': 'failure'})
                elif mutation == 'sha': self.f.run['head_sha'] = 'b'*40
                elif mutation == 'event': self.f.run['event'] = 'pull_request'
                else: self.f.run['head_branch'] = 'main'
                with self.assertRaises(GateError): self.verify()

    def test_extra_job_other_sha_run_or_duplicate_refuses(self):
        for mutation in ['sha', 'run', 'duplicate']:
            with self.subTest(mutation=mutation):
                self.f = ServerFixture()
                if mutation == 'duplicate': self.f.jobs.append({**self.f.jobs[-1], 'id': 91})
                else: self.f.jobs[-1]['head_sha' if mutation == 'sha' else 'run_id'] = 'b'*40 if mutation == 'sha' else 11
                with self.assertRaises(GateError): self.verify()

    def test_public_reader_is_get_only_no_authorization_and_bounded(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with patch.object(self.m, 'urlopen', return_value=Response(b'{"ok":true}')) as opened:
            self.assertEqual(self.m.public_api_get('repos/owner/repo/actions/workflows/ci.yml'), {'ok': True})
            request = opened.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertTrue(request.full_url.startswith('https://api.github.com/'))
            self.assertNotIn('Authorization', dict(request.header_items()))
            self.assertGreater(opened.call_args.kwargs['timeout'], 0)
        with patch.object(self.m, 'urlopen', side_effect=HTTPError('https://api.github.com', 403, '', {}, None)), self.assertRaises(GateError):
            self.m.public_api_get('repos/owner/repo/actions/runs')

    def test_cli_uses_verified_repository_not_env_override(self):
        with patch.dict(os.environ, {'WMS_DEPLOY_REPOSITORY': 'evil/repo', 'WMS_PROCESS_VERIFIED': '1'}), \
                patch('sys.argv', ['verify_server_process_ci.py', '--sha', SHA]), \
                patch.object(self.m, 'verify_server_ci', return_value={'sha': SHA}) as verifier, \
                patch.object(self.m, 'public_api_get') as reader:
            self.assertEqual(self.m.main(), 0)
            verifier.assert_called_once_with(reader, 'chivkunovd-bitdenis/WMS', SHA)


class ServerScriptTests(unittest.TestCase):
    def simulate(self, *, guard_only=False, gate_ok=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            trace = root / 'trace'
            commands = {
                'git': '#!/bin/sh\ncase "$*" in *rev-parse*) echo ' + SHA + ';; esac\nexit 0\n',
                'python3': '#!/bin/sh\necho "gate:$*" >> "$TRACE"\nexit ' + ('0' if gate_ok else '2') + '\n',
                'docker': '#!/bin/sh\necho "docker:$*" >> "$TRACE"\nexit 95\n',
            }
            for name, text in commands.items():
                path = bin_dir / name
                path.write_text(text)
                path.chmod(0o755)
            env = {'PATH': str(bin_dir) + ':/usr/bin:/bin', 'TRACE': str(trace),
                   'WMS_REPO_DIR': str(root), 'WMS_PROCESS_VERIFIED': '1',
                   'WMS_DEPLOY_CI_VERIFIED': '1', 'WMS_DEPLOY_REPOSITORY': 'evil/repo'}
            if guard_only: env['WMS_DEPLOY_GUARD_ONLY'] = '1'
            result = subprocess.run(['/bin/bash', str(ROOT / 'scripts/deploy/prod-update.sh')],
                                    env=env, capture_output=True, text=True, timeout=10, check=False)
            return result, trace.read_text().splitlines() if trace.exists() else []

    def test_unverified_server_stops_before_every_docker_action_even_with_verified_env_flags(self):
        result, calls = self.simulate()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [f'gate:scripts/ci/verify_server_process_ci.py --sha {SHA}'])

    def test_read_only_guard_only_exit_never_builds_or_checks_external_ci(self):
        result, calls = self.simulate(guard_only=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_successful_server_verification_precedes_first_build(self):
        result, calls = self.simulate(gate_ok=True)
        self.assertEqual(result.returncode, 95)  # Synthetic Docker deliberately stops here.
        self.assertEqual(calls[0], f'gate:scripts/ci/verify_server_process_ci.py --sha {SHA}')
        self.assertEqual(calls[1], 'docker:compose -f docker-compose.prod.yml build migrations')


if __name__ == '__main__': unittest.main()
