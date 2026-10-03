"""Publish a synthetic static mockup in the existing public landing file server."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import httpx

REMOTE_ROOT = "/root/wb-finance/landing/wms-previews"
PUBLIC_ROOT = "https://sellerfocus.pro/wms-previews"
ALLOWED = {".html", ".htm", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".json"}


class PublishError(RuntimeError):
    pass


def publish(directory: Path, *, public_id: str, client: httpx.Client | None = None) -> str:
    root = directory.resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        raise PublishError("static mockup must contain index.html")
    files = [p for p in root.rglob("*") if p.is_file()]
    if not files or len(files) > 300:
        raise PublishError("invalid mockup file count")
    total = 0
    for item in files:
        if item.is_symlink() or item.suffix.lower() not in ALLOWED:
            raise PublishError("unsafe mockup file")
        total += item.stat().st_size
    if total > 30_000_000:
        raise PublishError("mockup exceeds 30 MB")
    index = (root / "index.html").read_bytes()
    marker = hashlib.sha256(index).hexdigest()
    if len(public_id) != 24 or any(ch not in "0123456789abcdef" for ch in public_id):
        raise PublishError("invalid stable publication id")
    version = f"{marker[:12]}-{public_id}"
    staging = f"{REMOTE_ROOT}/.{version}.upload"
    target = f"{REMOTE_ROOT}/{version}"
    url = f"{PUBLIC_ROOT}/{version}/"
    http = client or httpx.Client()
    try:
        existing = http.get(url + "index.html", timeout=20)
    except httpx.HTTPError:
        raise PublishError("publication outcome unknown; public URL unreadable") from None
    if existing.status_code == 200:
        if hashlib.sha256(existing.content).hexdigest() == marker:
            return url
        raise PublishError("public URL exists with different content")
    if existing.status_code != 404:
        raise PublishError("publication outcome unknown")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for item in files:
            archive.add(item, arcname=str(item.relative_to(root)), recursive=False)
        meta = json.dumps({"index_sha256": marker}, separators=(",", ":")).encode()
        info = tarfile.TarInfo(".wms-preview.json")
        info.size = len(meta)
        archive.addfile(info, io.BytesIO(meta))
    # Only own prefix is touched; version names are random hex and never model input.
    command = (f"set -e; umask 022; mkdir -p {REMOTE_ROOT} {staging}; "
               f"tar -xf - -C {staging}; test ! -e {target}; mv {staging} {target}")
    run = subprocess.run(["ssh", "-o", "BatchMode=yes", "root@sellerfocus.pro", command],
                         input=buffer.getvalue(), capture_output=True, timeout=120, check=False)
    if run.returncode:
        raise PublishError(f"publication failed ({run.returncode})")
    try:
        response = http.get(url + "index.html", timeout=20)
    except httpx.HTTPError:
        raise PublishError("published URL could not be verified") from None
    if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != marker:
        raise PublishError("public URL does not serve the published version")
    return url
