"""Durable conversation archive and one editable owner card per semantic case."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_FILE_KEYS: dict[str, set[str]] = {}
_FILE_VERSIONS: dict[str, tuple[int, int]] = {}
_PROCESS_LOCKS = threading.local()
_LABELS = {
    'working': 'Взято в работу', 'analysis_done': 'Анализ завершён',
    'answer_sent': 'Ответ клиенту отправлен', 'owner_needed': 'Нужно уточнение владельца',
    'development_needed': 'Нужна разработка', 'process_change': 'Нужно исправление процесса',
    'task_needed': 'Задача нужна', 'task_created': 'Задача заведена',
}


class CaseJournal:
    def __init__(self, store: Any, root: str | Path) -> None:
        self.store, self.root = store, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _locked(self):
        # Native bridge, passive daemon and CLI workers share this archive.
        # Reentrant within a thread so card updates can record events safely.
        with _LOCK:
            held = getattr(_PROCESS_LOCKS, 'held', {})
            key = str(self.root.resolve())
            if key in held:
                yield
                return
            with (self.root / '.journal.lock').open('a') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                held[key] = handle
                _PROCESS_LOCKS.held = held
                try:
                    yield
                finally:
                    held.pop(key, None)
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def record(self, chat_id: int, kind: str, text: str, event_key: str,
               topic_id: str | int | None = None, data: Any = None) -> None:
        """Disk journal is append-only; retries use the same key, edits distinct revisions."""
        with self._locked():
            folder = self.root / f'chat-{chat_id}'
            folder.mkdir(parents=True, exist_ok=True)
            destinations = [folder / 'history.jsonl']
            if topic_id is not None:
                case_id = hashlib.sha256(str(topic_id).encode()).hexdigest()[:20]
                destinations.append(folder / f'case-{case_id}.jsonl')
            item = {'key': event_key, 'ts': time.time(), 'kind': kind, 'text': text,
                    'chat_id': chat_id, 'topic_id': topic_id, 'data': data}
            for path in destinations:
                # Recover safely if a previous process wrote the file then crashed before kv commit.
                cache_key = str(path.resolve())
                version = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else (0, 0)
                if cache_key not in _FILE_KEYS or _FILE_VERSIONS.get(cache_key) != version:
                    _FILE_KEYS[cache_key] = set()
                    if path.exists():
                        for line in path.read_text().splitlines():
                            try:
                                _FILE_KEYS[cache_key].add(json.loads(line)['key'])
                            except (ValueError, KeyError):
                                # Preserve a crash-truncated final line; subsequent records stay readable.
                                continue
                if event_key in _FILE_KEYS[cache_key]:
                    continue
                with path.open('a', encoding='utf-8') as stream:
                    if path.stat().st_size:
                        with path.open('rb') as tail:
                            tail.seek(-1, 2)
                            needs_newline = tail.read(1) != b'\n'
                        if needs_newline:
                            stream.write('\n')
                    stream.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                _FILE_KEYS[cache_key].add(event_key)
                _FILE_VERSIONS[cache_key] = (path.stat().st_mtime_ns, path.stat().st_size)

    def find_topic(self, reply_to: str | None) -> str | None:
        if not reply_to:
            return None
        for row in self.store.rows("SELECT key,value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row['value'])
            if str(card.get('message_id', '')) == str(reply_to):
                return str(card['topic_id'])
        return None

    def sync_chat(self, chat_id: int) -> None:
        for row in self.store.rows('SELECT * FROM messages WHERE chat_id=? ORDER BY id', (chat_id,)):
            self.record(chat_id, 'inbound', row['text'], f"in:{row['id']}:{row['revision']}",
                        data=dict(row))
        for row in self.store.rows(
            'SELECT r.* FROM message_revisions r JOIN messages m ON m.id=r.message_id '
            'WHERE m.chat_id=? ORDER BY r.id', (chat_id,)
        ):
            self.record(chat_id, 'edited_version', row['text'],
                        f"revision:{row['message_id']}:{row['revision']}", data=dict(row))
        for row in self.store.rows('SELECT * FROM outbox WHERE chat_id=? ORDER BY id', (chat_id,)):
            self.record(chat_id, 'outbound', row['text'], f"out:{row['id']}:{row['status']}", data=dict(row))
        with self._locked():
            memory = self.store.kv_get(f'agent_memory:{chat_id}', {})
            (self.root / f'chat-{chat_id}').mkdir(parents=True, exist_ok=True)
            (self.root / f'chat-{chat_id}' / 'summary.md').write_text(
                f'# Чат {chat_id}\n\n' + str(memory.get('summary', '')) + '\n\n'
                + json.dumps(memory, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def render(card: dict[str, Any]) -> str:
        header = f"Обращение №{card['number']} · {str(card.get('chat_title') or card['chat_id'])[:180]}\n"
        header += str(card.get('title') or 'Разбор обращения')[:220] + '\n'
        if card.get('summary'):
            header += '\n' + str(card['summary'])[:900] + '\n'
        for field, label in _LABELS.items():
            value = card.get('statuses', {}).get(field)
            header += f"{'🟢' if value is True else '🟡' if value else '⚪'} {label}\n"
        if card.get('task_url'):
            header += str(card['task_url'])[:300] + '\n'
        entries = [f"{datetime.fromtimestamp(e['ts']).strftime('%d.%m %H:%M')} — {e['text'][:1400]}"
                   for e in card.get('events', [])]
        # Telegram counts UTF-16 units, not Python Unicode code points.
        def fits(text: str) -> bool:
            return len(text.encode('utf-16-le')) // 2 <= 4096
        while entries and not fits(header + '\nХод обращения\n' + '\n'.join(entries)):
            entries.pop(0)
        return header + ('\nХод обращения\n' + '\n'.join(entries) if entries else '')

    def _write_overview(self) -> None:
        cards = [json.loads(row['value']) for row in self.store.rows(
            "SELECT value FROM kv WHERE key LIKE 'case_card:%'")]
        cards.sort(key=lambda card: card['number'])
        text = '# Обращения WMS\n\n'
        for card in cards:
            text += self.render(card) + '\n\n---\n\n'
            folder = self.root / f"chat-{card['chat_id']}"
            folder.mkdir(parents=True, exist_ok=True)
            identity = hashlib.sha256(str(card['topic_id']).encode()).hexdigest()[:20]
            (folder / f'case-{identity}.md').write_text(self.render(card) + '\n', encoding='utf-8')
        destination = self.root / 'overview.md'
        temporary = self.root / '.overview.tmp'
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(destination)

    def update_card(self, tg: Any, owner_chat_id: int, topic_id: str | int, chat_id: int,
                    title: str = '', summary: str | None = None,
                    statuses: dict[str, Any] | None = None, event: str | None = None,
                    event_key: str | None = None, chat_title: str = '', task_url: str = '') -> dict[str, Any]:
        from .telegram import TelegramError
        with self._locked():
            key = f'case_card:{topic_id}'
            card = self.store.kv_get(key, {})
            if not card:
                number = int(self.store.kv_get('case_card_sequence', 0)) + 1
                self.store.kv_set('case_card_sequence', number)
                card = {'number': number, 'topic_id': topic_id, 'chat_id': chat_id,
                        'statuses': {}, 'events': [], 'delivery': 'new'}
            if title:
                card['title'] = title
            if chat_title:
                card['chat_title'] = chat_title
            if summary is not None:
                card['summary'] = summary
            if task_url:
                card['task_url'] = task_url
            card['statuses'].update({k: v for k, v in (statuses or {}).items() if k in _LABELS})
            if event:
                event_key = event_key or hashlib.sha256(event.encode()).hexdigest()
                if not any(e['key'] == event_key for e in card['events']):
                    card['events'].append({'key': event_key, 'ts': time.time(), 'text': event})
                    self.record(chat_id, 'case_event', event, event_key, topic_id, statuses)
            self.store.kv_set(key, card)
            self._write_overview()
            body = self.render(card)
            if card.get('last_text') == body and card.get('message_id'):
                return card
            if not owner_chat_id:
                return card
            # Sending persisted before network; a crash or unknown outcome must not create a second card.
            if not card.get('message_id') and card['delivery'] in {'sending', 'unknown', 'rejected'}:
                return card
            creating = not card.get('message_id')
            if creating:
                card['delivery'] = 'sending'
                self.store.kv_set(key, card)
            try:
                if creating:
                    card['message_id'] = tg.send_message(owner_chat_id, body)
                else:
                    tg.edit_message(owner_chat_id, card['message_id'], body)
                card.update(delivery='sent', last_text=body)
            except TelegramError as exc:
                card['delivery'] = 'new' if creating and exc.outcome == 'not_sent' else exc.outcome
                card['delivery_error'] = exc.code
            self.store.kv_set(key, card)
            return card
