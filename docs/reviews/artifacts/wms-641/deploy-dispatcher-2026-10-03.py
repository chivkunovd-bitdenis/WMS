"""Install an exact committed bot tree; preserve configuration secrets and SQLite."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[4]
sha = sys.argv[1]
assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=ROOT, check=True)
remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/feat/wms641-support-agent"], cwd=ROOT, text=True).split()[0]
assert remote == sha, "Deploy only the verified published branch head"
state = Path.home() / ".wms-support-agent"
audit = ROOT / ".bot-audit-20261003"
audit.mkdir(exist_ok=True)
backup = audit / ("state-before-dispatcher-" + sha[:12] + ".sqlite3")
with sqlite3.connect(state / "state.db") as source, sqlite3.connect(backup) as dest:
    source.backup(dest)
os.chmod(backup, 0o600)
cfg_path = state / "config.json"
cfg = json.loads(cfg_path.read_text())
original_config = cfg_path.read_bytes()
assert cfg.get("agent", {}).get("enabled") is True, "Existing agent configuration required"
with tempfile.TemporaryDirectory(prefix="wms641-install-") as temp:
    tar = subprocess.check_output(["git", "archive", sha, "tools/support_agent"], cwd=ROOT)
    subprocess.run(["tar", "-xf", "-", "-C", temp], input=tar, check=True)
    package = Path(temp) / "tools/support_agent"
    subprocess.run(["bash", str(package / "launchd/install.sh")], check=True)
    app = state / "app"
    matched = []
    for src in package.rglob("*"):
        rel = src.relative_to(package)
        if not src.is_file() or rel.parts[0] == "tests":
            continue
        target = app / rel
        assert target.is_file() and hashlib.sha256(src.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest(), str(rel)
        matched.append(str(rel))
assert cfg_path.read_bytes() == original_config, "Installer changed configuration"
result = {"installed_sha": sha, "remote_sha": remote, "installed_files_verified": len(matched), "agent": cfg["agent"], "all_config_unchanged": True, "sqlite_backup_created": True, "scope": "local Telegram bot service only; no main merge or WMS production deployment"}
Path(__file__).with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
