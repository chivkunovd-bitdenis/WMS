"""WMS-676: installation must drain the old process before launchd can kill it.

All launchd/process interactions and configuration are isolated fakes. No installed
service, model, Telegram, credential store or production state is accessed.
"""
from __future__ import annotations

import importlib.util
import json
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

INSTALLER = Path(__file__).resolve().parents[3] / 'docs/reviews/artifacts/wms-676/install_sol61.py'
BUNDLED_CODEX = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: Any) -> Any:
    spec = importlib.util.spec_from_file_location('wms676_installer', INSTALLER)
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    root, state = tmp_path / 'repo', tmp_path / 'state'
    app = state / 'app'
    package = app / 'support_agent'
    package.mkdir(parents=True)
    source = root / 'tools/support_agent/support_agent'
    source.mkdir(parents=True)
    old_main = b'# old entry point, already loaded by the running process\n'
    old_worker = b'# installed WMS-664/WMS-668 worker\n'
    (package / '__main__.py').write_bytes(old_main)
    (package / 'worker.py').write_bytes(old_worker)
    (source / '__main__.py').write_bytes(old_main)
    (source / 'worker.py').write_bytes(b'# reviewed Sol migration worker\n')
    cfg = {'llm': {'codex_bin': '/opt/homebrew/bin/codex', 'cli_order': ['claude', 'codex'],
                   'models': {'codex': {'analyst': 'old', 'review': 'old', 'frontend': 'old'},
                              'claude': {'analyst': 'unchanged'}}, 'codex_effort': 'high'},
           'agent': {'owner_model': 'old', 'owner_provider': 'claude', 'enabled': True},
           'telegram': {'token': 'FAKE_VALUE_ONLY'}, 'other': {'nested': [1, 'keep']}}
    (state / 'config.json').write_text(json.dumps(cfg))
    with sqlite3.connect(state / 'state.db') as db:
        db.executescript('CREATE TABLE tickets (id INTEGER, stage TEXT);'
                         'CREATE TABLE kv (key TEXT, value TEXT);'
                         "INSERT INTO tickets VALUES (21, 'development');"
                         "INSERT INTO kv VALUES ('tg_offset:intake','41');"
                         "INSERT INTO kv VALUES ('agent_session:keep','{\"thread_id\":\"keep\"}');"
                         "INSERT INTO kv VALUES ('heartbeat','1000');")
    sha, base = 'a' * 40, 'b' * 40
    harness = SimpleNamespace(module=installer, state=state, app=app, cfg=cfg, package=package,
                              old_main=old_main, old_worker=old_worker, events=[],
                              term=False, alive=True, child=False, parked=False, polls=0,
                              timeout=False, elapsed=0.0, bootstrapped=False, allow_old_bootout=False)
    monkeypatch.setattr(installer, 'ROOT', root)
    monkeypatch.setattr(installer, 'STATE', state)
    monkeypatch.setattr(installer, 'APP', app)
    monkeypatch.setattr(installer, 'PLIST', state / 'test.plist')
    monkeypatch.setattr(sys, 'argv', ['install_sol61.py', sha, 'codex/test', base])
    monkeypatch.setattr(installer.os, 'access', lambda *_: True)
    original_is_file = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda p: True if str(p) == BUNDLED_CODEX else original_is_file(p))

    def advance() -> None:
        if not harness.term:
            return
        harness.polls += 1
        if harness.polls >= 3 and not harness.timeout:
            # The final tick has completed naturally, including its model child.
            harness.child = False
            harness.alive = False
            harness.parked = True
            harness.events.append('old_process_and_model_completed')

    def command(*args: str) -> str:
        if args[:2] == ('git', 'rev-parse'):
            return sha
        if args[:2] == ('git', 'ls-remote'):
            return sha + '\trefs/heads/codex/test'
        if args[:2] == ('git', 'diff'):
            return 'tools/support_agent/support_agent/worker.py'
        if args[:2] == ('git', 'ls-tree'):
            return '\n'.join('tools/support_agent/support_agent/' + f for f in ('__main__.py', 'worker.py'))
        if args[:2] == ('launchctl', 'print'):
            if harness.bootstrapped:
                return 'state = running\n pid = 300'
            return 'state = running\n pid = ' + ('100' if harness.alive else '200')
        if args[0] == 'ps':
            advance()
            if '-axo' in args:
                rows = ['100 1'] if harness.alive else ['200 1']
                if harness.child:
                    rows += ['101 100']
                return '\n'.join(rows)
            if '-p' in args:
                pid = args[args.index('-p') + 1]
                if pid == '100':
                    return 'python -m support_agent run' if harness.alive else ''
                return 'python -m support_agent run'
        raise AssertionError(f'unexpected command: {args}')

    def kill(pid: int, sig: int) -> None:
        assert (pid, sig) == (100, signal.SIGTERM), 'Never signal a model or use SIGKILL'
        assert (package / '__main__.py').read_bytes() != old_main, 'Respawn must be gated BEFORE stop'
        assert (package / 'worker.py').read_bytes() == old_worker, 'Worker code changes only after drain'
        harness.events.append('graceful_term')
        harness.term = True
        # Reproduce the installed runner's final-tick race after SIGTERM.
        harness.child = True

    def run(args: list[str], **kwargs: Any) -> Any:
        if args[:2] == ['launchctl', 'bootout']:
            if harness.allow_old_bootout:
                harness.alive = False
                harness.child = False
            elif not harness.term:
                # Old installer: bootout itself sends SIGTERM and kills the child
                # started by the final tick. The initial idle check cannot prevent it.
                harness.child = True
            assert not harness.child and not harness.alive, 'bootout would kill the final-tick model'
            harness.events.append('bootout_after_drain')
        elif args[:2] == ['launchctl', 'bootstrap']:
            assert (package / '__main__.py').read_bytes() == old_main, 'Temporary gate must be removed'
            harness.bootstrapped = True
        elif args[:2] != ['git', 'merge-base'] and 'check-config' not in args:
            raise AssertionError(f'unexpected subprocess: {args}')
        return subprocess.CompletedProcess(args, 0)

    def check_output(args: list[str], **kwargs: Any) -> bytes:
        assert args[:2] == ['git', 'show']
        return old_main if args[-1].endswith('__main__.py') else old_worker

    def sleep(delay: float) -> None:
        harness.elapsed += delay

    monkeypatch.setattr(installer, 'command', command)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    monkeypatch.setattr(installer.subprocess, 'check_output', check_output)
    monkeypatch.setattr(installer.os, 'kill', kill)
    monkeypatch.setattr(installer.time, 'sleep', sleep)
    monkeypatch.setattr(installer.time, 'monotonic', lambda: harness.elapsed)
    monkeypatch.setattr(installer.time, 'time', lambda: 1001)
    (root / 'docs/reviews/artifacts/wms-676').mkdir(parents=True)
    return harness


def test_final_tick_model_finishes_before_bootout(installation: Any) -> None:
    installation.module.main()
    assert installation.events.index('graceful_term') < installation.events.index('old_process_and_model_completed')
    assert installation.events.index('old_process_and_model_completed') < installation.events.index('bootout_after_drain')
    assert installation.polls >= 3


def test_only_model_settings_and_verified_bundled_binary_change(installation: Any) -> None:
    # Separate the binary contract from the drain failure in the previous test.
    installation.allow_old_bootout = True
    installation.module.main()
    cfg = json.loads((installation.state / 'config.json').read_text())
    assert cfg['llm']['codex_bin'] == BUNDLED_CODEX
    assert cfg['llm']['models']['codex']['analyst'] == 'gpt-6.1-sol'
    assert cfg['llm']['models']['codex']['review'] == 'gpt-6-astra'
    assert cfg['agent']['owner_model'] == 'gpt-6.1-sol'
    cfg['llm']['models']['codex'] = installation.cfg['llm']['models']['codex']
    for section, key in [('llm', 'cli_order'), ('llm', 'codex_bin'),
                         ('agent', 'owner_model'), ('agent', 'owner_provider')]:
        cfg[section][key] = installation.cfg[section][key]
    assert cfg == installation.cfg
    with sqlite3.connect(installation.state / 'state.db') as db:
        assert db.execute("SELECT value FROM kv WHERE key='agent_session:keep'").fetchone()[0] == '{"thread_id":"keep"}'
        assert db.execute("SELECT value FROM kv WHERE key='tg_offset:intake'").fetchone()[0] == '41'
        assert db.execute('SELECT id,stage FROM tickets').fetchall() == [(21, 'development')]


def test_drain_timeout_never_boots_out_or_installs_over_running_work(installation: Any) -> None:
    installation.timeout = True
    with pytest.raises((TimeoutError, RuntimeError), match='drain|exit|stop|finish'):
        installation.module.main()
    assert 'bootout_after_drain' not in installation.events
    assert installation.child and installation.alive
    assert (installation.package / '__main__.py').read_bytes() == installation.old_main
    assert (installation.package / 'worker.py').read_bytes() == installation.old_worker
    assert json.loads((installation.state / 'config.json').read_text()) == installation.cfg


def test_active_model_before_stop_is_left_untouched(installation: Any) -> None:
    installation.child = True
    with pytest.raises(AssertionError, match='subprocess'):
        installation.module.main()
    assert not installation.term
    assert installation.events == []
    assert (installation.package / '__main__.py').read_bytes() == installation.old_main


def test_wrong_installed_baseline_is_rejected_before_stop(installation: Any) -> None:
    (installation.package / 'worker.py').write_bytes(b'# foreign changes must not be replaced\n')
    with pytest.raises(AssertionError, match='baseline'):
        installation.module.main()
    assert not installation.term
    assert installation.events == []
