"""Audit-only CLI publication histories with synthetic callbacks; no GitHub writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
from unittest.mock import patch

SOURCE = Path('/Users/deniscivkunov/Projects/WMS/.worktrees/wms652-trusted-anchor')
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == 'ac6628aacda5631e0be886364ed01d2a324847c4', 'Use the frozen reviewed source'
sys.path.insert(0, str(SOURCE))
from scripts.ci import trusted_process_check as anchor
from scripts.ci.tests.test_trusted_process_artifact import ArtifactFixture
from scripts.ci.tests.test_trusted_process_check import H, REPO

with tempfile.TemporaryDirectory(prefix='wms-anchor-audit-') as temp:
    event = Path(temp) / 'event.json'
    event.write_text(json.dumps({'workflow_run': {'id':10, 'status':'completed',
        'head_sha':H, 'pull_requests':[{'number':7,'head':{'sha':H}}]}}))
    args = ['trusted_process_check.py','--repository',REPO,'--event',str(event),'--publish']
    environment = {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_run'}
    f = ArtifactFixture()
    history = [('earlier',H,'success')]
    def unavailable(path):
        raise ValueError('synthetic transient GitHub metadata outage')
    def publish(repo,head,conclusion,result):
        history.append(('new',head,conclusion))
    with patch.dict(os.environ,environment,clear=True), patch.object(sys,'argv',args), \
            patch.object(anchor,'api_get',unavailable), patch.object(anchor,'publish',publish), \
            contextlib.redirect_stdout(io.StringIO()):
        exit_code = anchor.main()
    print('API_OUTAGE_EXIT',exit_code)
    print('API_OUTAGE_PUBLICATION_HISTORY',json.dumps(history))
    assert exit_code == 2 and history[-1][2] == 'success' and len(history) == 1

    # The real CLI has completed its final recheck when publish() is entered.
    # Simulate a slow outgoing POST: a second workflow completes first.
    f = ArtifactFixture()
    entered,release = threading.Event(), threading.Event()
    history=[]; results={}
    def slow_publish(repo,head,conclusion,result):
        if conclusion == 'success':
            entered.set()
            if not release.wait(5): raise AssertionError('probe timeout')
        history.append((head,conclusion))
    def older():
        results['old'] = anchor.main()
    with patch.dict(os.environ,environment,clear=True), patch.object(sys,'argv',args), \
            patch.object(anchor,'api_get',f.get), patch.object(anchor,'download_artifact',f.download), \
            patch.object(anchor,'publish',slow_publish), contextlib.redirect_stdout(io.StringIO()):
        thread=threading.Thread(target=older)
        thread.start()
        if not entered.wait(5): raise AssertionError('old strict verifier did not reach publish')
        f.run['id']=11;f.run['run_number']=6;f.run['conclusion']='failure'
        results['new'] = anchor.main()
        release.set();thread.join(5)
        if thread.is_alive(): raise AssertionError('old publication did not finish')
    print('OVERLAPPING_CLI_EXITS',json.dumps(results))
    print('OVERLAPPING_PUBLICATION_HISTORY',json.dumps(history))
    assert results == {'new':2,'old':0}
    assert history == [(H,'failure'),(H,'success')]
