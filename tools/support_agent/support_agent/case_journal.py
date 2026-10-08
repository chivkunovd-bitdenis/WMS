"""Durable conversation archive and one editable owner card per semantic case."""
from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_FILE_KEYS: dict[str, set[str]] = {}
_FILE_VERSIONS: dict[str, tuple[int, int]] = {}
_PROCESS_LOCKS = threading.local()
_LABELS = {
    'queued': 'Получено, ожидает разбора', 'working': 'Взято в работу',
    'analysis_done': 'Анализ завершён', 'answer_sent': 'Ответ клиенту отправлен',
    'question_sent': 'Ждём ответа клиента', 'owner_needed': 'Нужно уточнение владельца',
    'development_needed': 'Нужна разработка', 'process_change': 'Нужно исправление процесса',
    'task_needed': 'Задача нужна', 'task_created': 'Задача заведена',
}
_SUMMARY_FIELDS = (
    ('essence', 'Кратко'),
    ('checked', 'Проверено'),
    ('found', 'Выяснено'),
    ('unknown', 'Не подтверждено'),
    ('next_step', 'Следующий шаг'),
)
_SUMMARY_LABELS = {
    'кратко': 'essence', 'суть': 'essence', 'краткая суть': 'essence',
    'проверено': 'checked', 'выяснено': 'found',
    'не подтверждено': 'unknown', 'неподтверждено': 'unknown',
    'следующий шаг': 'next_step', 'дальше': 'next_step',
}
_SUMMARY_EMPTY = {
    'essence': 'требует разбора', 'checked': 'пока не проверено',
    'found': 'пока не установлено', 'unknown': 'пока не подтверждено',
    'next_step': 'разобрать обращение',
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
               topic_id: str | int | None = None, data: Any = None,
               timestamp: float | None = None) -> None:
        """Persist the event in SQLite first, then project it to append-only files."""
        with self._locked():
            item_key = self._stored_event_key(chat_id, event_key, topic_id)
            item = self.store.kv_get(item_key)
            if item is None:
                # Normalize arbitrary source data before kv_set (Store uses strict JSON).
                item = json.loads(json.dumps(
                    {'key': event_key, 'ts': time.time() if timestamp is None else timestamp,
                     'kind': kind, 'text': text,
                     'chat_id': chat_id, 'topic_id': topic_id, 'data': data},
                    ensure_ascii=False, default=str,
                ))
                self.store.kv_set(item_key, item)
            try:
                self._materialize(item)
            except OSError:
                # SQLite is the source of truth. A later sync retries the JSONL projection.
                pass

    @staticmethod
    def _stored_event_key(chat_id: int, event_key: str,
                          topic_id: str | int | None = None) -> str:
        digest = hashlib.sha256(f'{chat_id}\0{topic_id}\0{event_key}'.encode()).hexdigest()
        return f'journal_event:{digest}'

    def _materialize(self, item: dict[str, Any]) -> None:
        def file_key(entry: dict[str, Any]) -> str:
            return json.dumps([entry.get('topic_id'), str(entry['key'])], ensure_ascii=False)

        folder = self.root / f"chat-{item['chat_id']}"
        folder.mkdir(parents=True, exist_ok=True)
        destinations = [folder / 'history.jsonl']
        if item.get('topic_id') is not None:
            case_id = hashlib.sha256(str(item['topic_id']).encode()).hexdigest()[:20]
            destinations.append(folder / f'case-{case_id}.jsonl')
        for path in destinations:
            # Cache is per file: a partial disk failure must not hide an unwritten projection.
            cache_key = str(path.resolve())
            version = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else (0, 0)
            if cache_key not in _FILE_KEYS or _FILE_VERSIONS.get(cache_key) != version:
                _FILE_KEYS[cache_key] = set()
                if path.exists():
                    for line in path.read_text(encoding='utf-8').splitlines():
                        try:
                            _FILE_KEYS[cache_key].add(file_key(json.loads(line)))
                        except (ValueError, KeyError):
                            # Keep a crash-truncated final line readable; later records remain appendable.
                            continue
            event_key = file_key(item)
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

    def _restore_chat_events(self, chat_id: int) -> None:
        # The editable card is another SQLite source for its timeline. This closes the
        # crash window after committing a card event but before committing its archive row.
        for row in self.store.rows("SELECT value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row['value'])
            if int(card.get('chat_id', 0)) != chat_id:
                continue
            topic_id = card.get('topic_id')
            snapshot = {key: card[key] for key in (
                'number', 'topic_id', 'chat_id', 'title', 'summary', 'chat_title', 'statuses', 'task_url'
            ) if key in card}
            snapshot_key = hashlib.sha256(json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True
            ).encode()).hexdigest()
            self.record(chat_id, 'case_snapshot', str(card.get('summary') or card.get('title') or ''),
                        f'case-snapshot:{topic_id}:{snapshot_key}', topic_id, snapshot)
            for event in card.get('events', []):
                self.record(chat_id, 'case_event', str(event.get('text', '')),
                            str(event['key']), topic_id, timestamp=float(event.get('ts', 0)))
        prefix = 'journal_event:'
        items = [json.loads(row['value']) for row in self.store.rows(
            "SELECT value FROM kv WHERE key LIKE ?", (prefix + '%',)
        )]
        items = [item for item in items if int(item.get('chat_id', 0)) == chat_id]
        items.sort(key=lambda item: (float(item.get('ts', 0)), str(item.get('key', ''))))
        for item in items:
            try:
                self._materialize(item)
            except OSError:
                # Leave it in SQLite and retry on a later call after storage recovers.
                return

    def find_topic(self, reply_to: str | None) -> str | None:
        if not reply_to:
            return None
        for row in self.store.rows("SELECT key,value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row['value'])
            if (str(card.get('message_id', '')) == str(reply_to)
                    or str(reply_to) in card.get('previous_message_ids', [])):
                return str(card['topic_id'])
        return None

    def find_realtime_event_topic(self, event_key: str) -> str | None:
        """Find a card created by this workflow version that acknowledged an event."""
        if not event_key:
            return None
        for row in self.store.rows("SELECT value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row['value'])
            if card.get('realtime_card_version') != 1:
                continue
            if any(str(event.get('key') or '') == event_key for event in card.get('events', [])):
                return str(card['topic_id'])
        return None

    def find_message_topic(self, message_id: int | str) -> str | None:
        """Keep later edits of an already-carded Telegram message in that case."""
        prefix = f"in:{message_id}:"
        for row in self.store.rows("SELECT value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row['value'])
            if any(str(event.get('key') or '').startswith(prefix)
                   for event in card.get('events', [])):
                return str(card['topic_id'])
        return None

    def sync_chat(self, chat_id: int) -> None:
        for row in self.store.rows('SELECT * FROM messages WHERE chat_id=? ORDER BY id', (chat_id,)):
            self.record(chat_id, 'inbound', row['text'], f"in:{row['id']}:{row['revision']}",
                        data=dict(row), timestamp=float(row['ts']))
            # Transcription is asynchronous and does not create a Telegram edit.
            # Preserve it separately even when the empty original is already archived.
            if row['kind'] == 'voice' and row['text']:
                self.record(chat_id, 'transcript', row['text'],
                            f"transcript:{row['id']}:{row['revision']}", data=dict(row),
                            timestamp=float(row['ts']))
            media = self.store.kv_get(f"media:{row['id']}:{row['revision']}", {})
            if media.get('status') == 'ready':
                self.record(chat_id, 'attachment', row['caption'],
                            f"attachment:{row['id']}:{row['revision']}:{media['sha256']}", data=media,
                            timestamp=float(row['ts']))
        for row in self.store.rows(
            'SELECT r.* FROM message_revisions r JOIN messages m ON m.id=r.message_id '
            'WHERE m.chat_id=? ORDER BY r.id', (chat_id,)
        ):
            self.record(chat_id, 'edited_version', row['text'],
                        f"revision:{row['message_id']}:{row['revision']}", data=dict(row),
                        timestamp=float(row['edited_at']))
            media = self.store.kv_get(f"media:{row['message_id']}:{row['revision']}", {})
            if media.get('status') == 'ready':
                self.record(chat_id, 'attachment', row['caption'],
                            f"attachment:{row['message_id']}:{row['revision']}:{media['sha256']}",
                            data=media, timestamp=float(row['edited_at']))
        for row in self.store.rows('SELECT * FROM outbox WHERE chat_id=? ORDER BY id', (chat_id,)):
            self.record(chat_id, 'outbound', row['text'], f"out:{row['id']}:{row['status']}",
                        data=dict(row), timestamp=float(row['sent_at'] or row['created_at']))
        with self._locked():
            self._restore_chat_events(chat_id)
            memory = self.store.kv_get(f'agent_memory:{chat_id}', {})
            (self.root / f'chat-{chat_id}').mkdir(parents=True, exist_ok=True)
            try:
                (self.root / f'chat-{chat_id}' / 'summary.md').write_text(
                    f'# Чат {chat_id}\n\n' + str(memory.get('summary', '')) + '\n\n'
                    + json.dumps(memory, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError:
                pass
            try:
                self._write_overview()
            except OSError:
                pass

    @staticmethod
    def _summary(card: dict[str, Any]) -> dict[str, Any]:
        fields = {key: '' for key, _ in _SUMMARY_FIELDS}
        details: list[str] = []
        current: str | None = None
        summary = card.get('summary')
        if isinstance(summary, dict):
            aliases = {'essence': 'essence', 'checked': 'checked', 'found': 'found',
                       'unknown': 'unknown', 'next_step': 'next_step'}
            for key, value in summary.items():
                if key in aliases and value not in (None, ''):
                    if isinstance(value, str) and value.strip().startswith('['):
                        try:
                            value = ast.literal_eval(value)
                        except (ValueError, SyntaxError):
                            pass
                    fields[aliases[key]] = ('\n'.join(str(item).strip() for item in value)
                                            if isinstance(value, list) else str(value).strip())
            fields['details'] = details
            return fields
        for line in str(summary or '').splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            label, separator, value = stripped.partition(':')
            if not separator:
                label, separator, value = stripped.partition('—')
            field = _SUMMARY_LABELS.get(label.strip().casefold()) if separator else None
            if field:
                current = field
                if value.strip():
                    fields[field] = '\n'.join(filter(None, (fields[field], value.strip())))
            elif separator:
                # Keep marketplace/product/quantity lines independent; never merge them into a fact.
                details.append(stripped)
                current = None
            elif current:
                fields[current] = '\n'.join(filter(None, (fields[current], stripped)))
            else:
                # Unstructured historical summaries remain visible as the case essence.
                fields['essence'] = '\n'.join(filter(None, (fields['essence'], stripped)))
        if not fields['essence']:
            fields['essence'] = str(card.get('title') or 'Поступило новое обращение').strip()
        fields['details'] = details
        return fields

    @staticmethod
    def _current_status(card: dict[str, Any]) -> str:
        current = card.get('current_status')
        if current in _LABELS:
            return current
        statuses = card.get('statuses', {})
        active = [key for key in _LABELS if statuses.get(key) is True]
        # Legacy cards may have several true badges; prefer the more specific/latest outcome.
        priority = ('task_created', 'task_needed', 'development_needed', 'process_change',
                    'owner_needed', 'question_sent', 'answer_sent', 'analysis_done',
                    'queued', 'working')
        return next((key for key in priority if key in active), 'working')

    @staticmethod
    def _visible_event(event: dict[str, Any]) -> str:
        key, text = str(event.get('key') or ''), str(event.get('text') or '').strip()
        if key.startswith(('in:', 'transcript:', 'analysis-start:')):
            return ''
        if text.startswith(('Получено', 'Начат разбор', 'Проверка:', 'Контекст созвона',
                            'Разбор завершён', 'Разбор завершен', 'Голосовое сообщение расшифровано')):
            return ''
        for prefix, label in (('Ответ отправлен клиенту:', 'Ответ клиенту отправлен.'),
                              ('Уточнение отправлено клиенту:', 'Задан уточняющий вопрос клиенту.'),
                              ('Ответ владельцу отправлен:', 'Ответ владельцу отправлен.')):
            if text.startswith(prefix):
                return label
        return text

    @staticmethod
    def render(card: dict[str, Any]) -> str:
        def shorten(value: Any, units: int) -> str:
            return str(value).encode('utf-16-le')[:units * 2].decode('utf-16-le', errors='ignore')

        status = CaseJournal._current_status(card)
        indicator = '🟡' if status in {'queued', 'working', 'question_sent', 'owner_needed'} else '🟢'
        lines = [f"Статус: {indicator} {_LABELS[status]}",
                 f"Обращение №{card['number']} · {shorten(card.get('chat_title') or card['chat_id'], 180)}"]
        facts = CaseJournal._summary(card)
        lines.append('\nСуть: ' + shorten(facts['essence'], 1200))
        if facts.get('found') and facts['found'] not in _SUMMARY_EMPTY.values():
            lines.append('Результат: ' + shorten(facts['found'], 600))
        if facts.get('next_step') and facts['next_step'] not in _SUMMARY_EMPTY.values():
            lines.append('Дальше: ' + shorten(facts['next_step'], 400))
        if card.get('task_url'):
            lines.append(shorten(card['task_url'], 250))
        lines.extend(shorten(detail, 180) for detail in facts.get('details', [])[:3])
        header = '\n'.join(lines)
        entries = []
        for event in card.get('events', []):
            text = CaseJournal._visible_event(event)
            if text:
                stamp = datetime.fromtimestamp(float(event['ts']), ZoneInfo('Asia/Tbilisi'))
                entries.append(f"{stamp.strftime('%d.%m %H:%M')} — {shorten(' '.join(text.split()), 350)}")
        def body() -> str:
            return header + ('\n\nХод обращения\n' + '\n'.join(entries) if entries else '')
        while entries and len(body().encode('utf-16-le')) // 2 > 4096:
            entries.pop(0)
        return body()

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
                    event_key: str | None = None, chat_title: str = '', task_url: str = '',
                    event_timestamp: float | None = None) -> dict[str, Any]:
        from .telegram import TelegramError
        with self._locked():
            key = f'case_card:{topic_id}'
            card = self.store.kv_get(key, {})
            if not card:
                number = int(self.store.kv_get('case_card_sequence', 0)) + 1
                self.store.kv_set('case_card_sequence', number)
                card = {'number': number, 'topic_id': topic_id, 'chat_id': chat_id,
                        'statuses': {'working': True}, 'current_status': 'working',
                        'events': [], 'delivery': 'new', 'realtime_card_version': 1}
            previous_summary = self._summary(card)
            if title:
                card['title'] = title
            if chat_title:
                card['chat_title'] = chat_title
            if summary is not None:
                card['summary'] = summary
            if task_url:
                card['task_url'] = task_url
            status_updates = {k: v for k, v in (statuses or {}).items() if k in _LABELS}
            active_statuses = [key for key, value in status_updates.items() if value is True]
            if active_statuses:
                current_status = active_statuses[-1]
                card['statuses'] = {key: key == current_status for key in _LABELS}
                card['current_status'] = current_status
            event_ts: float | None = None
            if event:
                event_key = event_key or hashlib.sha256(event.encode()).hexdigest()
                if not any(e['key'] == event_key for e in card['events']):
                    event_ts = time.time() if event_timestamp is None else event_timestamp
                    card['events'].append({'key': event_key, 'ts': event_ts, 'text': event})
                    terminal_statuses = {'analysis_done', 'answer_sent', 'question_sent',
                                         'task_created'}
                    if (not active_statuses
                            and self._current_status(card) in terminal_statuses):
                        card['statuses'] = {key: key == 'working' for key in _LABELS}
                        card['current_status'] = 'working'
            snapshot = {k: card[k] for k in ('number', 'topic_id', 'chat_id', 'title', 'summary',
                                              'chat_title', 'statuses', 'task_url') if k in card}
            snapshot_key = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False,
                                                       sort_keys=True).encode()).hexdigest()
            # The current card and its event are durable before any file or Telegram work.
            self.store.kv_set(key, card)
            self.record(chat_id, 'case_snapshot', str(card.get('summary') or card.get('title') or ''),
                        f'case-snapshot:{topic_id}:{snapshot_key}', topic_id, snapshot)
            if event and event_ts is not None:
                self.record(chat_id, 'case_event', event, event_key, topic_id, statuses,
                            timestamp=event_ts)
            try:
                self._write_overview()
            except OSError:
                # Keep serving the persisted card when a derived Markdown view cannot be written.
                pass
            body = self.render(card)
            if card.get('last_text') == body and card.get('message_id'):
                if owner_chat_id:
                    for obsolete_id in list(card.get('obsolete_message_ids', [])):
                        try:
                            tg.delete_message(owner_chat_id, obsolete_id)
                        except TelegramError:
                            continue
                        card['obsolete_message_ids'].remove(obsolete_id)
                    self.store.kv_set(key, card)
                return card
            if not owner_chat_id:
                return card
            # Sending persisted before network; a crash or unknown outcome must not create a second card.
            if not card.get('message_id') and card['delivery'] in {'sending', 'unknown', 'rejected'}:
                return card
            current_summary = self._summary(card)
            changed = any(previous_summary.get(field) != current_summary.get(field)
                          for field in ('essence', 'found', 'next_step'))
            moving = bool(card.get('message_id') and (changed or (event_ts is not None
                          and self._visible_event({'key': event_key, 'text': event}))))
            if card.get('replacement_delivery') in {'sending', 'unknown'}:
                return card
            creating = not card.get('message_id')
            if creating:
                card['delivery'] = 'sending'
                self.store.kv_set(key, card)
            old_message_id = str(card.get('message_id') or '')
            if moving:
                card['replacement_delivery'] = 'sending'
                card['replacement_previous_message_id'] = old_message_id
                self.store.kv_set(key, card)
            try:
                if creating or moving:
                    card['message_id'] = tg.send_message(owner_chat_id, body)
                else:
                    tg.edit_message(owner_chat_id, card['message_id'], body)
                card.update(delivery='sent', last_text=body)
                if moving:
                    card['replacement_delivery'] = 'sent'
                    previous = list(card.get('previous_message_ids', []))
                    card['previous_message_ids'] = list(dict.fromkeys(previous + [old_message_id]))
                    obsolete = list(card.get('obsolete_message_ids', []))
                    card['obsolete_message_ids'] = list(dict.fromkeys(obsolete + [old_message_id]))
                self.store.kv_set(key, card)
                # New card is durable before deleting only its known previous versions.
                for obsolete_id in list(card.get('obsolete_message_ids', [])):
                    try:
                        tg.delete_message(owner_chat_id, obsolete_id)
                    except TelegramError:
                        continue
                    card['obsolete_message_ids'].remove(obsolete_id)
            except TelegramError as exc:
                if moving:
                    card['replacement_delivery'] = exc.outcome
                card['delivery'] = 'new' if creating and exc.outcome == 'not_sent' else exc.outcome
                card['delivery_error'] = exc.code
            self.store.kv_set(key, card)
            return card
