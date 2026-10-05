"""Drain the published local Telegram service before installing its model migration.

The entrypoint gate prevents KeepAlive from starting another worker. The existing
Python process keeps its already loaded code and exits through its SIGTERM handler;
its non-daemon executor threads finish naturally. bootout only follows that exit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
STATE = Path('/Users/deniscivkunov/.wms-support-agent')
APP = STATE / 'app'
LABEL = 'pro.sellerfocus.wms-support-agent'
PLIST = Path('/Users/deniscivkunov/Library/LaunchAgents') / f'{LABEL}.plist'
MODEL = 'gpt-6.1-sol'
REVIEW_MODEL = 'gpt-6-astra'
CODEX_BIN = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
DRAIN_TIMEOUT_SEC = 3600
BACKUP: Path | None = None
STOPPED = False
# No imports from support_agent and no work on any launchd respawn. Default
# SIGTERM terminates only this idle gate process when the service is booted out.
ENTRYPOINT_GATE = b'"""WMS-676 installation: wait without starting any service work."""\nimport signal\nwhile True:\n    signal.pause()\n'


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def idle_snapshot() -> dict:
    with sqlite3.connect(f'file:{STATE / "state.db"}?mode=ro', uri=True) as db:
        busy = db.execute("SELECT key FROM kv WHERE key LIKE 'agent_job:%' AND "
                          "(json_extract(value,'$.status') IN ('running','recovering','queued','scheduled') "
                          "OR json_extract(value,'$.preflight_status') IN ('running','queued'))").fetchall()
        assert not busy, 'A project job is active; wait for its saved boundary'
        return {'tickets': db.execute('SELECT id,stage FROM tickets ORDER BY id').fetchall(),
                'jobs': db.execute("SELECT key,json_extract(value,'$.status') FROM kv "
                                   "WHERE key LIKE 'agent_job:%' ORDER BY key").fetchall(),
                'offsets': db.execute("SELECT key,value FROM kv WHERE key LIKE 'tg_offset%' "
                                      "ORDER BY key").fetchall(),
                'database_digest': hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()}


def process_tree() -> dict[int, int]:
    return {int(row.split()[0]): int(row.split()[1])
            for row in command('ps', '-axo', 'pid=,ppid=').splitlines() if row.strip()}


def no_child_processes(pid: int) -> None:
    assert pid not in process_tree().values(), 'A service subprocess is active'


def service_pid() -> int:
    state = command('launchctl', 'print', f'gui/{os.getuid()}/{LABEL}')
    return int(next(line.split('=')[1].strip() for line in state.splitlines()
                    if line.strip().startswith('pid =')))


def atomic_bytes(path: Path, value: bytes) -> None:
    """Replace a complete file, including on abort; never expose a half-written gate."""
    mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.wms676-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def drain_and_bootout(pid: int) -> None:
    """Gate all respawns atomically, then await the old process AND descendants.

    Installed runner startup loads __main__ before run_forever. Thus replacing
    __main__ does not alter any in-flight Python stack. Unlike bootout, os.kill
    sends SIGTERM only to the parent, without launchd's kill deadline. The legacy
    final tick may still submit work; Python's non-daemon executors drain it before
    the parent exits. A timeout restores the original entrypoint and kills nothing.
    """
    global STOPPED
    entrypoint = APP / 'support_agent/__main__.py'
    original = entrypoint.read_bytes()
    gate = ENTRYPOINT_GATE
    # Python's timestamp bytecode cache also uses source size; force invalidation.
    if len(gate) == len(original):
        gate += b'\n'
    atomic_bytes(entrypoint, gate)
    tracked = {pid}
    try:
        # The parent cannot respawn as a worker after this atomic gate boundary.
        # If it exited independently, the next process is gated; do not signal a
        # stale PID which launchd no longer identifies as this service.
        if service_pid() == pid:
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + DRAIN_TIMEOUT_SEC
        while True:
            rows = process_tree()
            while True:
                children = {child for child, parent in rows.items() if parent in tracked}
                expanded = tracked | children
                if expanded == tracked:
                    break
                tracked = expanded
            if not tracked.intersection(rows):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Service drain timed out; ongoing work was not killed')
            time.sleep(0.25)
        # The old process and every observed descendant are gone. Any launchd
        # respawn can only run the gated entrypoint, even if it races this bootout.
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(PLIST)], check=True)
        STOPPED = True
    finally:
        atomic_bytes(entrypoint, original)


def main() -> None:
    global BACKUP, STOPPED
    sha, branch, base = sys.argv[1:4]
    assert len(sha) == 40 and all(c in '0123456789abcdef' for c in sha)
    assert command('git', 'rev-parse', 'HEAD') == sha
    assert command('git', 'ls-remote', 'origin', f'refs/heads/{branch}').split()[0] == sha
    assert len(base) == 40 and all(c in '0123456789abcdef' for c in base)
    assert Path(CODEX_BIN).is_file() and os.access(CODEX_BIN, os.X_OK), 'Bundled Codex is unavailable'
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, sha], cwd=ROOT, check=True)
    changed = command('git', 'diff', '--name-only', base, sha, '--', 'tools/support_agent').splitlines()
    install_files = [path for path in changed if Path(path).parts[2] == 'support_agent']
    package_files = command('git', 'ls-tree', '-r', '--name-only', sha, '--',
                            'tools/support_agent/support_agent').splitlines()
    assert install_files, 'No package migration in this commit'
    for path in package_files:
        target = APP / Path(path).relative_to('tools/support_agent')
        baseline = subprocess.check_output(['git', 'show', f'{base}:{path}'], cwd=ROOT)
        assert target.read_bytes() == baseline, f'Installed file differs from baseline: {path}'
        published = subprocess.check_output(['git', 'show', f'{sha}:{path}'], cwd=ROOT)
        assert (ROOT / path).read_bytes() == published, f'Checkout differs from published SHA: {path}'
    pid = service_pid()
    no_child_processes(pid)
    before = idle_snapshot()
    backup = Path(tempfile.mkdtemp(prefix='sol61-before-', dir=STATE))
    BACKUP = backup
    os.chmod(backup, 0o700)
    cfg_path = STATE / 'config.json'
    shutil.copy2(cfg_path, backup / 'config.json')
    os.chmod(backup / 'config.json', 0o600)
    # Save every replaced file BEFORE changing even the temporary entrypoint.
    backup_files = set(install_files) | {'tools/support_agent/support_agent/__main__.py'}
    for path in backup_files:
        relative = Path(path).relative_to('tools/support_agent')
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP / relative, saved)
    start_attempted = False
    try:
        drain_and_bootout(pid)
        stopped = idle_snapshot()
        # Final-tick results are authoritative: back up after natural completion.
        # Never restore the pre-drain DB and lose completed model/job outcomes.
        with sqlite3.connect(STATE / 'state.db') as source, sqlite3.connect(backup / 'state.db') as dest:
            source.backup(dest)
        os.chmod(backup / 'state.db', 0o600)
        cfg = json.loads(cfg_path.read_text())
        original = json.loads(json.dumps(cfg))
        cfg['llm']['cli_order'] = ['codex']
        cfg['llm']['codex_bin'] = CODEX_BIN
        cfg['llm']['models']['codex'] = {
            role: REVIEW_MODEL if role == 'review' else MODEL
            for role in cfg['llm']['models']['codex']
        }
        cfg['agent']['owner_model'] = MODEL
        cfg['agent']['owner_provider'] = 'codex'
        # All values outside these five model-selection settings remain identical.
        preserved = json.loads(json.dumps(cfg))
        for section, key in [('llm', 'cli_order'), ('llm', 'codex_bin'),
                             ('agent', 'owner_model'), ('agent', 'owner_provider')]:
            preserved[section][key] = original[section][key]
        preserved['llm']['models']['codex'] = original['llm']['models']['codex']
        assert preserved == original
        atomic_bytes(cfg_path, (json.dumps(cfg, ensure_ascii=False, indent=2) + '\n').encode())
        hashes = {}
        for path in install_files:
            relative = Path(path).relative_to('tools/support_agent')
            target = APP / relative
            atomic_bytes(target, (ROOT / path).read_bytes())
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            assert digest == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            hashes[str(relative)] = digest
        for path in package_files:
            relative = Path(path).relative_to('tools/support_agent')
            assert (APP / relative).read_bytes() == (ROOT / path).read_bytes(), str(relative)
        assert idle_snapshot() == stopped, 'Installation altered task/job/Telegram state'
        subprocess.run([str(APP / '.venv/bin/python'), '-m', 'support_agent', 'check-config',
                        '--config', str(cfg_path)], cwd=APP, check=True)
        # From this point even a failed bootstrap/heartbeat has an unknown work
        # outcome. Do not bootout or revert code underneath newly started models.
        start_attempted = True
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
        STOPPED = False
        time.sleep(3)
        running = command('launchctl', 'print', f'gui/{os.getuid()}/{LABEL}')
        assert 'state = running' in running
        with sqlite3.connect(f'file:{STATE / "state.db"}?mode=ro', uri=True) as db:
            heartbeat = json.loads(db.execute("SELECT value FROM kv WHERE key='heartbeat'").fetchone()[0])
        assert time.time() - float(heartbeat) < 30
        report = {'installed_sha': sha, 'published_branch': branch, 'model': MODEL,
                  'codex_bin': CODEX_BIN, 'review_model': REVIEW_MODEL, 'review_effort': 'high',
                  'previous_package_sha': base, 'files': hashes,
                  'state_preserved_during_install': True,
                  'old_process_drained_before_bootout': True,
                  'respawn_gated_before_sigterm': True,
                  'all_package_modules_match_commit': True,
                  'initial_ticket_count': len(before['tickets']), 'backup': str(backup),
                  'service_running': True, 'heartbeat_age_sec': time.time() - float(heartbeat),
                  'non_model_configuration_preserved': True,
                  'scope': 'Local Telegram service only; no merge or WMS production deploy'}
        output = ROOT / 'docs/reviews/artifacts/wms-676/local-install.json'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False))
    except BaseException:
        if STOPPED and not start_attempted:
            # Service is known absent; only here is file rollback safe.
            atomic_bytes(cfg_path, (backup / 'config.json').read_bytes())
            for saved in (backup / 'support_agent').rglob('*'):
                if saved.is_file():
                    atomic_bytes(APP / saved.relative_to(backup), saved.read_bytes())
            subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
        STOPPED = False
        raise


if __name__ == '__main__':
    main()
