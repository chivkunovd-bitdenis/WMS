"""WMS-652 Astra P1 contracts: withdraw stale success and serialize publishers."""
import contextlib
import importlib
import io
import json
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.ci.tests.test_trusted_process_artifact import ArtifactFixture
from scripts.ci.tests.test_trusted_process_check import REPO, H

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / 'docs/evidence/WMS-652/trusted-anchor-20261006/process-integrity.yml'


def event(kind, run_id=10, head=H):
    identity = {'number': 7, 'state': 'open', 'head': {'sha': head, 'repo': {'full_name': REPO}},
                'base': {'ref': 'etalon', 'repo': {'full_name': REPO}}}
    body = {'repository': {'full_name': REPO}}
    if kind == 'pull_request_target':
        body['pull_request'] = identity
    else:
        body['workflow_run'] = {'id': run_id, 'status': 'completed', 'event': 'pull_request',
            'path': '.github/workflows/ci.yml', 'head_sha': head,
            'repository': {'full_name': REPO}, 'head_repository': {'full_name': REPO},
            'pull_requests': [identity]}
    return body


def group(body):
    template = re.search(r'^  group: (.+)$', WORKFLOW.read_text(), re.MULTILINE).group(1)
    expression = '${{ github.event.pull_request.number || github.event.workflow_run.id }}'
    identity = body.get('pull_request', {}).get('number') or body.get('workflow_run', {}).get('id')
    result = template.replace(expression, str(identity))
    if '${{' in result:
        raise AssertionError('Unreviewed dynamic publisher concurrency')
    return result


class PublishFailureTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.trusted_process_check')

    def outage(self, kind, body):
        history = [(H, 'success')]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            path.write_text(json.dumps(body))
            argv = ['trusted_process_check.py', '--repository', REPO, '--event', str(path), '--publish']
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': kind}, clear=True), \
                    patch('sys.argv', argv), \
                    patch.object(self.m, 'api_get', side_effect=ValueError('synthetic initial API outage')), \
                    patch.object(self.m, 'publish', side_effect=lambda repo, head, conclusion, result: history.append((head, conclusion))), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = self.m.main()
        return code, history

    def test_initial_pr_api_outage_withdraws_prior_success_for_both_trusted_events(self):
        for kind in ['pull_request_target', 'workflow_run']:
            with self.subTest(kind=kind):
                code, history = self.outage(kind, event(kind))
                self.assertEqual(code, 2)
                self.assertEqual(history, [(H, 'success'), (H, 'failure')])

    def test_missing_invalid_or_foreign_event_identity_never_publishes_fallback(self):
        for mutation in ['head', 'number', 'repository', 'target', 'head_repository']:
            with self.subTest(mutation=mutation):
                body = event('workflow_run')
                run = body['workflow_run']
                if mutation == 'head': run['head_sha'] = 'not-a-sha'
                elif mutation == 'number': run['pull_requests'][0]['head'].pop('sha')
                elif mutation == 'repository': body['repository']['full_name'] = 'foreign/repo'
                elif mutation == 'target': run['pull_requests'][0]['base']['ref'] = 'main'
                else: run['head_repository']['full_name'] = 'fork/repo'
                code, history = self.outage('workflow_run', body)
                self.assertEqual(code, 2)
                self.assertEqual(history, [(H, 'success')])

    def test_event_head_is_failure_only_and_never_overrides_fresh_verified_head(self):
        fixture = ArtifactFixture()
        body = event('workflow_run', head='e'*40)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            path.write_text(json.dumps(body))
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_run'}, clear=True), \
                    patch('sys.argv', ['checker', '--repository', REPO, '--event', str(path), '--publish']), \
                    patch.object(self.m, 'api_get', fixture.get), \
                    patch.object(self.m, 'download_artifact', fixture.download), \
                    patch.object(self.m, 'publish') as published, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.m.main(), 0)
                self.assertEqual(published.call_args.args[:3], (REPO, H, 'success'))


class SerializedPublisherTests(unittest.TestCase):
    def test_every_event_kind_and_run_or_pr_uses_one_global_non_cancelling_queue(self):
        bodies = [event('pull_request_target'), event('workflow_run', 10), event('workflow_run', 11)]
        other = event('pull_request_target')
        other['pull_request']['number'] = 8
        bodies.append(other)
        self.assertEqual(len({group(body) for body in bodies}), 1)
        self.assertIn('  cancel-in-progress: false', WORKFLOW.read_text())

    def test_declared_queue_prevents_delayed_old_success_post_after_new_failure(self):
        anchor = importlib.import_module('scripts.ci.trusted_process_check')
        fixture = ArtifactFixture()
        old_event, new_event = event('workflow_run', 10), event('workflow_run', 11)
        queues = {key: threading.Lock() for key in {group(old_event), group(new_event)}}
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        history, results, errors = [], {}, []
        local = threading.local()
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for name, body in [('old', old_event), ('new', new_event)]:
                paths[name] = Path(folder) / (name + '.json')
                paths[name].write_text(json.dumps(body))
            def arguments(_self, *args, **kwargs):
                return SimpleNamespace(repository=REPO, pr=None, event=str(paths[local.name]), publish=True)
            def publish(repo, head, conclusion, result):
                if conclusion == 'success':
                    entered.set()
                    if not release.wait(5): raise AssertionError('Synthetic publish timeout')
                history.append((head, conclusion))
            def invoke(name, body):
                local.name = name
                if name == 'new': queued.set()
                try:
                    with queues[group(body)]:
                        results[name] = anchor.main()
                except BaseException as error:  # noqa: BLE001 - fail the parent test on any thread error
                    errors.append(error)
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_run'}, clear=True), \
                    patch.object(anchor.argparse.ArgumentParser, 'parse_args', arguments), \
                    patch.object(anchor, 'api_get', fixture.get), \
                    patch.object(anchor, 'download_artifact', fixture.download), \
                    patch.object(anchor, 'publish', publish), contextlib.redirect_stdout(io.StringIO()):
                old = threading.Thread(target=invoke, args=('old', old_event))
                old.start()
                self.assertTrue(entered.wait(5))
                fixture.run.update(id=11, run_number=6, conclusion='failure')
                new = threading.Thread(target=invoke, args=('new', new_event))
                new.start()
                try:
                    self.assertTrue(queued.wait(5))
                    # Different old queues let the failure POST finish first.
                    if group(old_event) != group(new_event): new.join(5)
                finally:
                    release.set()
                    old.join(5)
                    new.join(5)
                self.assertFalse(old.is_alive() or new.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(results, {'old': 0, 'new': 2})
                self.assertEqual(history, [(H, 'success'), (H, 'failure')])


if __name__ == '__main__': unittest.main()
