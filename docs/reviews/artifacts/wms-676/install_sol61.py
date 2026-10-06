"""Install the published model migration while the local Telegram service is idle."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
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
BACKUP: Path | None = None
STOPPED = False


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
                                      "ORDER BY key").fetchall()}


def no_child_processes(pid: int) -> None:
    rows = command('ps', '-axo', 'pid=,ppid=').splitlines()
    assert not any(int(row.split()[1]) == pid for row in rows), 'A service subprocess is active'


def main() -> None:
    global BACKUP, STOPPED
    sha, branch, base = sys.argv[1:4]
    assert len(sha) == 40 and all(c in '0123456789abcdef' for c in sha)
    assert command('git', 'rev-parse', 'HEAD') == sha
    assert command('git', 'ls-remote', 'origin', f'refs/heads/{branch}').split()[0] == sha
    assert len(base) == 40 and all(c in '0123456789abcdef' for c in base)
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
    state = command('launchctl', 'print', f'gui/{os.getuid()}/{LABEL}')
    pid = int(next(line.split('=')[1].strip() for line in state.splitlines() if line.strip().startswith('pid =')))
    no_child_processes(pid)
    before = idle_snapshot()
    backup = Path(tempfile.mkdtemp(prefix='sol61-before-', dir=STATE))
    BACKUP = backup
    os.chmod(backup, 0o700)
    # Stop only after proving no model/worker is in flight; no kill of ongoing work.
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(PLIST)], check=True)
    STOPPED = True
    stopped = idle_snapshot()
    with sqlite3.connect(STATE / 'state.db') as source, sqlite3.connect(backup / 'state.db') as dest:
        source.backup(dest)
    os.chmod(backup / 'state.db', 0o600)
    cfg_path = STATE / 'config.json'
    shutil.copy2(cfg_path, backup / 'config.json')
    os.chmod(backup / 'config.json', 0o600)
    cfg = json.loads(cfg_path.read_text())
    original = json.loads(json.dumps(cfg))
    cfg['llm']['cli_order'] = ['codex']
    cfg['llm']['models']['codex'] = {role: MODEL for role in cfg['llm']['models']['codex']}
    cfg['agent']['owner_model'] = MODEL
    cfg['agent']['owner_provider'] = 'codex'
    # All values outside the four model-selection settings remain identical.
    preserved = json.loads(json.dumps(cfg))
    preserved['llm']['cli_order'] = original['llm']['cli_order']
    preserved['llm']['models']['codex'] = original['llm']['models']['codex']
    preserved['agent']['owner_model'] = original['agent']['owner_model']
    preserved['agent']['owner_provider'] = original['agent']['owner_provider']
    assert preserved == original
    temporary = STATE / 'config.sol61-install.json'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(cfg, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.replace(temporary, cfg_path)
    hashes = {}
    for path in install_files:
        relative = Path(path).relative_to('tools/support_agent')
        target = APP / relative
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
        shutil.copy2(ROOT / path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        hashes[str(relative)] = digest
    for path in package_files:
        relative = Path(path).relative_to('tools/support_agent')
        assert (APP / relative).read_bytes() == (ROOT / path).read_bytes(), str(relative)
    assert idle_snapshot() == stopped, 'Installation altered task/job/Telegram state'
    subprocess.run([str(APP / '.venv/bin/python'), '-m', 'support_agent', 'check-config',
                    '--config', str(cfg_path)], cwd=APP, check=True)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
    time.sleep(3)
    running = command('launchctl', 'print', f'gui/{os.getuid()}/{LABEL}')
    assert 'state = running' in running
    with sqlite3.connect(f'file:{STATE / "state.db"}?mode=ro', uri=True) as db:
        heartbeat = json.loads(db.execute("SELECT value FROM kv WHERE key='heartbeat'").fetchone()[0])
    assert time.time() - float(heartbeat) < 30
    report = {'installed_sha': sha, 'published_branch': branch, 'model': MODEL,
              'previous_package_sha': base,
              'files': hashes, 'state_preserved_during_install': True,
              'all_package_modules_match_commit': True,
              'initial_ticket_count': len(before['tickets']), 'backup': str(backup),
              'service_running': True, 'heartbeat_age_sec': time.time() - float(heartbeat),
              'non_model_configuration_preserved': True,
              'scope': 'Local Telegram service only; no merge or WMS production deploy'}
    output = ROOT / 'docs/reviews/artifacts/wms-676/local-install.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    STOPPED = False
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        if STOPPED:
            subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(PLIST)],
                           capture_output=True)
            if BACKUP is not None:
                saved_config = BACKUP / 'config.json'
                if saved_config.exists():
                    shutil.copy2(saved_config, STATE / 'config.json')
                for saved in (BACKUP / 'support_agent').rglob('*'):
                    if saved.is_file():
                        shutil.copy2(saved, APP / saved.relative_to(BACKUP))
            subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)],
                           check=True)
        raise
