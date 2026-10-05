"""WMS-676 R8: real isolated processes and immutable published installation bytes.

May also be loaded as a pytest plugin (-p tests.test_install_model_migration_races) to
extend the frozen installation fake with numeric process-group metadata. This
adapter supplies platform observations, never changes its assertions/outcomes.
Real repros intercept launchctl; only their own synthetic workers receive TERM.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.test_install_model_migration import INSTALLER
from tests.test_install_model_migration import installation as frozen_installation


@pytest.fixture(autouse=True)
def frozen_metadata(request: Any, monkeypatch: Any) -> None:
    if 'installation' not in request.fixturenames:
        return
    h = request.getfixturevalue('installation')
    original = h.module.command

    def command(*args: str) -> str:
        if args == ('ps', '-axo', 'pid=,ppid=,pgid='):
            return '\n'.join(row + (' 100' if row.split()[0] in ('100', '101') else ' 200')
                             for row in original('ps', '-axo', 'pid=,ppid=').splitlines())
        return original(*args)

    def idle_gate_verified(pid: int, marker: Path) -> bool:
        assert h.package.joinpath('__main__.py').read_bytes() != h.old_main
        return pid == 200 and h.parked

    monkeypatch.setattr(h.module, 'command', command)
    monkeypatch.setattr(h.module, 'idle_gate_verified', idle_gate_verified, raising=False)


@pytest.fixture
def source_installation(tmp_path: Path, monkeypatch: Any) -> Any:
    h = frozen_installation.__wrapped__(tmp_path, monkeypatch)
    original = h.module.command

    def command(*args: str) -> str:
        if args == ('ps', '-axo', 'pid=,ppid=,pgid='):
            return '\n'.join(row + (' 100' if row.split()[0] in ('100', '101') else ' 200')
                             for row in original('ps', '-axo', 'pid=,ppid=').splitlines())
        return original(*args)

    monkeypatch.setattr(h.module, 'command', command)
    monkeypatch.setattr(h.module, 'idle_gate_verified', lambda pid, marker: pid == 200 and h.parked,
                        raising=False)
    return h


def test_source_changed_during_drain_installs_only_published_bytes(source_installation: Any,
                                                                  monkeypatch: Any) -> None:
    h = source_installation
    original = h.module.drain_and_bootout

    def drain(pid: int) -> None:
        original(pid)
        (h.module.ROOT / 'tools/support_agent/support_agent/worker.py').write_bytes(b'# UNPUBLISHED\n')

    monkeypatch.setattr(h.module, 'drain_and_bootout', drain)
    h.module.main()
    assert (h.package / 'worker.py').read_bytes() == b'# reviewed Sol migration worker\n'
    report = json.loads((h.module.ROOT / 'docs/reviews/artifacts/wms-676/local-install.json').read_text())
    assert report['installed_sha'] == 'a' * 40
    assert report['all_package_modules_match_commit'] is True


def await_file(path: Path) -> None:
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline, str(path)
        time.sleep(.01)


WORKER = '''import os, pathlib, signal, subprocess, sys, time
p=pathlib.Path.cwd(); stop=False
def term(*_):
    global stop
    stop=True
signal.signal(signal.SIGTERM,term)
p.joinpath('ready').write_text('yes')
while not stop: time.sleep(.001)
child=subprocess.Popen([sys.executable,'-c', "import pathlib,time; time.sleep(.4); pathlib.Path('done').write_text('yes')"])
p.joinpath('child_pid').write_text(str(child.pid))
if p.joinpath('orphan').exists(): os._exit(0)
child.wait()
'''


@pytest.fixture
def processes(tmp_path: Path, monkeypatch: Any) -> Any:
    spec = importlib.util.spec_from_file_location('isolated_wms676', INSTALLER)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    package = tmp_path / 'support_agent'
    package.mkdir()
    (package / '__init__.py').write_text('')
    (package / '__main__.py').write_text(WORKER)
    m.APP = tmp_path
    m.ROOT = tmp_path
    m.PLIST = tmp_path / 'unused.plist'
    m.DRAIN_TIMEOUT_SEC = 3
    # Capture real primitives BEFORE installer monkeypatches shared modules.
    run, kill = subprocess.run, os.kill

    def check_output(args: Any, **kwargs: Any) -> str:
        return run(args, stdout=subprocess.PIPE, check=True, **kwargs).stdout
    h = SimpleNamespace(m=m, app=tmp_path, package=package, procs=[], current=None,
                        bootouts=[], signals=[], run=run, kill=kill, output=check_output)

    def start() -> Any:
        p = subprocess.Popen([sys.executable, '-B', '-m', 'support_agent'], cwd=tmp_path,
                             start_new_session=True)
        h.procs.append(p)
        h.current = p
        await_file(tmp_path / 'ready')
        return p

    h.start = start
    m.service_pid = lambda: h.current.pid

    def command(*args: str) -> str:
        assert args[0] == 'ps', 'No real launchctl or external command allowed'
        for p in h.procs:
            p.poll()
        return check_output(args, text=True).strip()

    monkeypatch.setattr(m, 'command', command)

    def bootout(args: list[str], **kwargs: Any) -> Any:
        assert args[:2] == ['launchctl', 'bootout']
        h.bootouts.append(time.monotonic())
        assert (tmp_path / 'done').exists(), 'bootout reached with live final-tick work'
        assert h.current.poll() is not None or h.current is getattr(h, 'gate', None), (
            'bootout reached with replacement worker alive')
        return subprocess.CompletedProcess(args, 0)

    def term(pid: int, sig: int) -> None:
        h.signals.append((pid, sig))
        assert pid == h.current.pid and sig == signal.SIGTERM
        kill(pid, sig)

    monkeypatch.setattr(m.subprocess, 'run', bootout)
    monkeypatch.setattr(m.os, 'kill', term)
    yield h
    # Cleanup only our workers; model children finish naturally, never get killed.
    for p in h.procs:
        if p.poll() is None:
            kill(p.pid, signal.SIGTERM)
        p.wait(timeout=5)
    if (tmp_path / 'child_pid').exists():
        await_file(tmp_path / 'done')


def test_replaced_worker_before_gate_aborts_without_signal_or_bootout(processes: Any) -> None:
    h = processes
    old = h.start()
    h.kill(old.pid, signal.SIGTERM)
    old.wait(timeout=5)
    (h.app / 'ready').unlink()
    (h.app / 'done').unlink()
    replacement = h.start()
    with pytest.raises(RuntimeError, match='changed|identity|replacement'):
        h.m.drain_and_bootout(old.pid)
    assert replacement.poll() is None
    assert h.bootouts == [] and h.signals == []
    assert (h.package / '__main__.py').read_text() == WORKER


def test_never_observed_orphan_finishes_before_bootout(processes: Any, monkeypatch: Any) -> None:
    h = processes
    (h.app / 'orphan').touch()
    parent = h.start()
    original = h.m.process_tree

    def rows() -> dict[int, int]:
        if h.signals and not getattr(h, 'observed_orphan', False):
            parent.wait(timeout=3)
            h.observed_orphan = True
            child = int((h.app / 'child_pid').read_text())
            metadata = h.output(['ps', '-p', str(child), '-o', 'ppid='], text=True).strip()
            assert metadata == '1', 'Repro must hide child from all PPID observations'
        return original()

    monkeypatch.setattr(h.m, 'process_tree', rows)
    h.m.drain_and_bootout(parent.pid)
    assert (h.app / 'done').exists()
    assert len(h.bootouts) == 1
    assert (h.package / '__main__.py').read_text() == WORKER


def test_orphan_timeout_does_not_bootout_or_replace_files(processes: Any,
                                                        monkeypatch: Any) -> None:
    h = processes
    (h.app / 'orphan').touch()
    parent = h.start()
    h.m.DRAIN_TIMEOUT_SEC = .05
    original = h.m.process_tree

    def rows() -> dict[int, int]:
        if h.signals:
            parent.wait(timeout=3)
        return original()

    monkeypatch.setattr(h.m, 'process_tree', rows)
    with pytest.raises(TimeoutError, match='drain'):
        h.m.drain_and_bootout(parent.pid)
    assert h.bootouts == []
    assert not (h.app / 'done').exists()
    assert (h.package / '__main__.py').read_text() == WORKER


def test_shared_process_group_refused_before_sigterm(processes: Any, monkeypatch: Any) -> None:
    h = processes
    parent = h.start()
    original = h.m.command

    def command(*args: str) -> str:
        if args == ('ps', '-axo', 'pid=,ppid=,pgid='):
            return f'{parent.pid} {os.getpid()} {os.getpgrp()}'
        return original(*args)

    monkeypatch.setattr(h.m, 'command', command)
    with pytest.raises(RuntimeError, match='group'):
        h.m.drain_and_bootout(parent.pid)
    assert h.signals == [] and h.bootouts == []
    assert (h.package / '__main__.py').read_text() == WORKER


def test_real_module_respawn_is_verified_idle_before_bootout(processes: Any,
                                                           monkeypatch: Any) -> None:
    h = processes
    parent = h.start()
    ready = (h.app / 'ready').stat().st_mtime_ns

    def service_pid() -> int:
        if parent.poll() is not None and not hasattr(h, 'gate'):
            h.gate = subprocess.Popen([sys.executable, '-B', '-m', 'support_agent'], cwd=h.app,
                                      start_new_session=True)
            h.procs.append(h.gate)
            h.current = h.gate
            time.sleep(.08)
        return h.current.pid

    monkeypatch.setattr(h.m, 'service_pid', service_pid)
    h.m.drain_and_bootout(parent.pid)
    assert h.gate.poll() is None
    assert (h.app / 'ready').stat().st_mtime_ns == ready
    assert len(h.bootouts) == 1


def test_unverified_replacement_after_drain_never_boots_out(processes: Any,
                                                          monkeypatch: Any) -> None:
    h = processes
    parent = h.start()

    def service_pid() -> int:
        if parent.poll() is not None and not hasattr(h, 'replacement'):
            h.replacement = subprocess.Popen([sys.executable, '-c', WORKER], cwd=h.app,
                                             start_new_session=True)
            h.procs.append(h.replacement)
            h.current = h.replacement
            time.sleep(.08)
        return h.current.pid

    monkeypatch.setattr(h.m, 'service_pid', service_pid)
    with pytest.raises(RuntimeError, match='gate|identity|replacement'):
        h.m.drain_and_bootout(parent.pid)
    assert h.replacement.poll() is None
    assert h.bootouts == []
    assert h.signals == [(parent.pid, signal.SIGTERM)]
    assert (h.package / '__main__.py').read_text() == WORKER


def test_pid_replacement_during_atomic_gate_aborts_without_signal(processes: Any,
                                                                monkeypatch: Any) -> None:
    h = processes
    parent = h.start()
    original = h.m.atomic_bytes

    def atomic(path: Path, value: bytes) -> None:
        if value != WORKER.encode() and not hasattr(h, 'replacement'):
            # Exit/reap original, then start a worker which has read OLD bytes,
            # before the installer commits the atomic gate replacement.
            h.kill(parent.pid, signal.SIGTERM)
            parent.wait(timeout=5)
            (h.app / 'ready').unlink()
            (h.app / 'done').unlink()
            h.replacement = h.start()
        original(path, value)

    monkeypatch.setattr(h.m, 'atomic_bytes', atomic)
    with pytest.raises(RuntimeError, match='changed|identity|replacement'):
        h.m.drain_and_bootout(parent.pid)
    assert h.replacement.poll() is None
    assert h.signals == [] and h.bootouts == []
    assert (h.package / '__main__.py').read_text() == WORKER


def test_installed_bytes_changed_after_bootstrap_cannot_report_exact_sha(source_installation: Any,
                                                                       monkeypatch: Any) -> None:
    h = source_installation
    original = h.module.command

    def command(*args: str) -> str:
        if args[:2] == ('launchctl', 'print') and h.bootstrapped:
            (h.package / 'worker.py').write_bytes(b'# concurrent installed mutation\n')
        return original(*args)

    monkeypatch.setattr(h.module, 'command', command)
    with pytest.raises(AssertionError, match='published|commit'):
        h.module.main()
    assert h.bootstrapped
    assert h.events.count('bootout_after_drain') == 1
    assert h.events.count('service_bootstrap') == 1
    assert not (h.module.ROOT / 'docs/reviews/artifacts/wms-676/local-install.json').exists()
