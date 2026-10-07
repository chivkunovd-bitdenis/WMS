"""Install only WMS's two native context settings, preserving user configuration."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

KEYS = ("model_auto_compact_token_limit", "model_auto_compact_token_limit_scope")


def merge_context_config(text: str, settings: dict[str, int | str]) -> str:
    before = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    root_end = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    for key in KEYS:
        value = json.dumps(settings[key])
        pattern = re.compile(r"^\s*(?:" + key + r"|[\"']" + key + r"[\"'])\s*=")
        matches = [i for i in range(root_end) if pattern.match(lines[i])]
        if matches:
            lines[matches[0]] = f"{key} = {value}\n"
        elif key in before:
            raise ValueError(f"Unsupported existing TOML spelling of managed key: {key}")
        else:
            if root_end and not lines[root_end - 1].endswith("\n"):
                lines[root_end - 1] += "\n"
            lines.insert(root_end, f"{key} = {value}\n")
            root_end += 1
    merged = "".join(lines)
    after = tomllib.loads(merged)
    if {k: v for k, v in before.items() if k not in KEYS} != {
            k: v for k, v in after.items() if k not in KEYS}:
        raise ValueError("Unrelated WMS user configuration would change; installation refused")
    if {key: after[key] for key in KEYS} != settings:
        raise ValueError("Managed WMS context keys failed validation")
    return merged


def install_context_config(repo: Path, sha: str) -> dict[str, object]:
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True).strip()).parent
    if root != Path("/Users/deniscivkunov/Projects/WMS"):
        raise ValueError("Context configuration may be installed only in the canonical WMS project")
    source = subprocess.check_output(["git", "-C", str(repo), "show", f"{sha}:.codex/config.toml"])
    settings = tomllib.loads(source.decode())
    if settings != {KEYS[0]: 250000, KEYS[1]: "total"}:
        raise ValueError("Saved WMS context configuration must contain exactly the 250000/total keys")
    target = root / ".codex/config.toml"
    before = target.read_bytes() if target.exists() else b""
    merged = merge_context_config(before.decode(), settings).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    if (target.read_bytes() if target.exists() else b"") != before:
        raise ValueError("WMS context configuration changed concurrently; no overwrite performed")
    if merged != before:
        temporary = target.with_name(".config.toml.wms-context-install")
        temporary.write_bytes(merged)
        os.chmod(temporary, target.stat().st_mode & 0o777 if target.exists() else 0o600)
        temporary.replace(target)
    if tomllib.loads(target.read_text()) != tomllib.loads(merged.decode()):
        raise ValueError("Installed WMS context configuration differs from the verified merge")
    return {"path": str(target), "sha": sha, "managed_values": settings,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "installed_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == "__main__":
    repo, sha, app = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    result = install_context_config(repo, sha)
    manifest_path = app / "INSTALLATION.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["wms_context_config"] = result
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("WMS context settings installed from saved Git source: 250000/total; other fields preserved.")
