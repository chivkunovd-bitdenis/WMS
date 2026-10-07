"""Keep original Telegram attachments next to the durable conversation history."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any


def archive_root(cfg: Any) -> Path:
    return Path(cfg.agent.history_dir or str(Path(cfg.repo) / 'var/support-conversations'))


def suffix(data: bytes, kind: str) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return '.webp'
    if data.startswith(b'%PDF'):
        return '.pdf'
    if data.startswith(b'OggS'):
        return '.ogg'
    if data[4:8] == b'ftyp':
        return '.mp4'
    if data.startswith(b'PK\x03\x04'):
        return '.zip'
    return '.bin'


def archive_message(pipe: Any, message: Any) -> dict[str, Any]:
    m = dict(message)
    if not m.get('file_id'):
        return {}
    key = f"media:{m['id']}:{m.get('revision', 1)}"
    saved = pipe.store.kv_get(key, {})
    if saved.get('path') and Path(saved['path']).is_file():
        return saved
    if float(saved.get('retry_at', 0)) > time.time():
        return saved
    try:
        data = pipe.bots.for_role(m['role']).download_file(m['file_id'])
        folder = archive_root(pipe.cfg) / f"chat-{m['chat_id']}" / 'attachments'
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{m['id']}-r{m.get('revision', 1)}" + suffix(data, m['kind'])
        path = folder / name
        temporary = folder / f'.{name}.{os.getpid()}.part'
        with temporary.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        result = {'path': str(path), 'kind': m['kind'], 'bytes': len(data),
                  'sha256': hashlib.sha256(data).hexdigest(), 'status': 'ready'}
        pipe.store.kv_set(key, result)
        return result
    except Exception as exc:
        result = {'status': 'unavailable', 'error': type(exc).__name__,
                  'retry_at': time.time() + 120}
        pipe.store.kv_set(key, result)
        return result


def message_image_paths(pipe: Any, message: Any) -> list[str]:
    """Actual pixels, including the replied-to attachment, never just its caption."""
    if message is None:
        return []
    rows = [dict(message)]
    if rows[0].get('reply_to'):
        parent = pipe.store.row('SELECT * FROM messages WHERE chat_id=? AND msg_id=?',
                                (rows[0]['chat_id'], rows[0]['reply_to']))
        if parent is not None:
            rows.append(dict(parent))
    paths = []
    for row in rows:
        media = archive_message(pipe, row)
        path = media.get('path', '')
        if path and Path(path).suffix in ('.png', '.jpg', '.gif', '.webp'):
            paths.append(path)
    return list(dict.fromkeys(paths))


def archive_pending(pipe: Any) -> None:
    # Ready files are a cheap local lookup; a recent window would permanently
    # starve older attachments, including versions superseded by Telegram edits.
    for row in pipe.store.rows("SELECT * FROM messages WHERE file_id IS NOT NULL ORDER BY id DESC"):
        archive_message(pipe, row)
    for row in pipe.store.rows(
        "SELECT m.id,m.chat_id,m.role,r.revision,r.kind,r.file_id FROM message_revisions r "
        "JOIN messages m ON m.id=r.message_id WHERE r.file_id IS NOT NULL ORDER BY r.id DESC"
    ):
        archive_message(pipe, row)
