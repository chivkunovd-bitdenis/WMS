"""Archive and Telegram limits, using local materials and no external sends."""
from __future__ import annotations

import errno
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from support_agent.case_journal import CaseJournal
from support_agent.config import config_from_dict
from support_agent.media import archive_pending, message_image_paths
from support_agent.store import Store
from support_agent.telegram import Bots, TelegramClient, TelegramError, normalize_update


def add(store, number, *, text='', kind='voice', file_id=None, edited=False):
    return store.add_message(source='telegram', chat_id=10, msg_id=str(number), role='client',
                             author_id='5', author_name='Анна', ts=100, kind=kind,
                             text=text, file_id=file_id, reply_to=None, edited=edited)


class Cards:
    def __init__(self):
        self.sent, self.edits = [], []
        self.fail = None

    def send_message(self, chat, text):
        self.sent.append((chat, text))
        if self.fail:
            raise self.fail
        return '1004'

    def edit_message(self, chat, message_id, text):
        self.edits.append((chat, message_id, text))


def records(root):
    return [json.loads(line) for line in (root / 'chat-10/history.jsonl').read_text().splitlines()]


def test_transcript_and_archive_links_survive_first_empty_record_and_replay(tmp_path):
    store = Store(':memory:')
    journal = CaseJournal(store, tmp_path)
    message_id = add(store, 1, file_id='voice')
    journal.sync_chat(10)
    store.complete_transcription(message_id, 1, 'Расшифровка: не получается отгрузить')
    store.kv_set(f'media:{message_id}:1', {'status': 'ready', 'sha256': 'abc', 'path': '/voice.ogg'})
    journal.sync_chat(10)
    journal.sync_chat(10)
    events = records(tmp_path)
    assert len([e for e in events if e['kind'] == 'inbound']) == 1
    assert [e['text'] for e in events if e['kind'] == 'transcript'] == [
        'Расшифровка: не получается отгрузить']
    assert [e['data']['path'] for e in events if e['kind'] == 'attachment'] == ['/voice.ogg']


def test_single_card_edits_drops_oldest_visible_events_and_keeps_complete_journal(tmp_path):
    store, tg = Store(':memory:'), Cards()
    journal = CaseJournal(store, tmp_path)
    for index in range(12):
        card = journal.update_card(tg, 900, 'native:817', 10, title='Нельзя отгрузить',
                                   statuses={'working': True}, event=f'Шаг {index} ' + '🔎' * 600,
                                   event_key=f'step:{index}')
    body = journal.render(card)
    assert len(tg.sent) == 1 and len(tg.edits) == 11
    assert tg.edits[-1][1] == '1004'
    assert len(body.encode('utf-16-le')) // 2 <= 4096
    assert 'Шаг 0 ' not in body and 'Шаг 11 ' in body
    assert len([e for e in records(tmp_path) if e['kind'] == 'case_event']) == 12
    replay = journal.update_card(tg, 900, 'native:817', 10, event='Шаг 11 ' + '🔎' * 600,
                                 event_key='step:11')
    assert replay['number'] == 1 and len(tg.sent) == 1 and len(tg.edits) == 11
    assert journal.find_topic('1004') == 'native:817'


def test_card_render_separates_facts_and_shows_one_current_status(tmp_path):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    journal = CaseJournal(store, tmp_path / 'history')
    facts = [
        'WB: заказ доступен в WMS',
        'Товары WB: 12',
        'Ozon: рабочая поставка',
        'Заказы Ozon: 3',
        'Проверено: заказ найден в WMS',
        'Выяснено: подбор ещё не начат',
        'Не подтверждено: причина не установлена',
        'Следующий шаг: продолжить проверку',
    ]
    card = journal.update_card(
        tg, 900, 'native:format', 10,
        title='Проверка поставки ' * 24,
        summary='\n'.join(facts),
        statuses={'working': True},
    )

    lines = journal.render(card).splitlines()
    assert all(fact in lines for fact in facts)
    assert len(card['title']) > 220
    status_labels = (
        'Взято в работу', 'Анализ завершён', 'Ответ клиенту отправлен',
        'Нужно уточнение владельца', 'Нужна разработка', 'Нужно исправление процесса',
        'Задача нужна', 'Задача заведена',
    )
    status_lines = [line for line in lines if any(label in line for label in status_labels)]
    assert len(status_lines) == 1
    assert 'Взято в работу' in status_lines[0]


def test_journal_enospc_keeps_sqlite_event_and_edits_existing_card(tmp_path, monkeypatch):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    journal = CaseJournal(store, tmp_path / 'history')
    card = journal.update_card(
        tg, 900, 'native:enospc', 10, title='Проверить ответ',
        statuses={'working': True}, event='Разбор начат', event_key='begin',
    )
    message_id = add(store, 41, text='Нужно проверить поставку')
    assert store.row('SELECT id FROM messages WHERE id=?', (message_id,)) is not None

    def disk_full(_fd):
        raise OSError(errno.ENOSPC, 'No space left on device')

    monkeypatch.setattr('support_agent.case_journal.os.fsync', disk_full)
    updated = journal.update_card(
        tg, 900, 'native:enospc', 10,
        event='Подтверждённый ответ клиенту', event_key='answer:41',
    )

    saved = store.kv_get('case_card:native:enospc')
    assert store.row('SELECT id FROM messages WHERE id=?', (message_id,)) is not None
    assert any(event['key'] == 'answer:41' for event in saved['events'])
    assert updated['message_id'] == card['message_id']
    assert len(tg.sent) == 1
    assert tg.edits[-1][1] == card['message_id']
    assert 'Подтверждённый ответ клиенту' in tg.edits[-1][2]


def test_overview_enospc_does_not_block_sqlite_event_or_same_card_edit(tmp_path, monkeypatch):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    journal = CaseJournal(store, tmp_path / 'history')
    card = journal.update_card(
        tg, 900, 'native:overview-enospc', 10, title='Проверить ответ',
        statuses={'working': True}, event='Разбор начат', event_key='begin',
    )
    original_write_overview = journal._write_overview
    attempts = 0

    def fail_once():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(errno.ENOSPC, 'No space left on device')
        original_write_overview()

    monkeypatch.setattr(journal, '_write_overview', fail_once)
    updated = journal.update_card(
        tg, 900, 'native:overview-enospc', 10,
        event='Подтверждённый ответ клиенту', event_key='answer:overview',
    )

    saved = store.kv_get('case_card:native:overview-enospc')
    assert sum(event['key'] == 'answer:overview' for event in saved['events']) == 1
    assert updated['message_id'] == card['message_id']
    assert len(tg.sent) == 1
    assert len(tg.edits) == 1
    assert tg.edits[0][1] == card['message_id']
    assert 'Подтверждённый ответ клиенту' in tg.edits[0][2]

    replay = journal.update_card(
        tg, 900, 'native:overview-enospc', 10,
        event='Подтверждённый ответ клиенту', event_key='answer:overview',
    )
    assert sum(event['key'] == 'answer:overview' for event in replay['events']) == 1


def test_unknown_card_creation_does_not_duplicate_after_restart(tmp_path):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    tg.fail = TelegramError('unknown', 'ReadTimeout')
    journal = CaseJournal(store, tmp_path / 'history')
    card = journal.update_card(tg, 900, '817', 10, event='Начал разбор', event_key='begin')
    assert card['delivery'] == 'unknown'
    tg.fail = None
    CaseJournal(Store(tmp_path / 'state.db'), tmp_path / 'history').update_card(
        tg, 900, '817', 10, event='Дополнительный материал', event_key='next')
    assert len(tg.sent) == 1


def test_all_old_attachments_and_superseded_versions_are_archived(tmp_path):
    store = Store(':memory:')

    class Files:
        def __init__(self):
            self.calls = []

        def download_file(self, file_id):
            self.calls.append(file_id)
            return b'\x89PNG\r\n\x1a\n' + file_id.encode()

    tg = Files()
    pipe = SimpleNamespace(store=store, bots=Bots(tg, tg),
                           cfg=SimpleNamespace(repo=str(tmp_path), agent=SimpleNamespace(history_dir='')))
    first = add(store, 1, kind='photo', file_id='old-photo')
    for number in range(2, 203):
        add(store, number, kind='photo', file_id=f'photo-{number}')
    add(store, 1, kind='photo', file_id='new-photo', edited=True)
    archive_pending(pipe)
    assert 'old-photo' in tg.calls and 'new-photo' in tg.calls and len(tg.calls) == 203
    old = store.kv_get(f'media:{first}:1', {})
    latest = store.kv_get(f'media:{first}:2', {})
    assert Path(old['path']).read_bytes().endswith(b'old-photo')
    assert Path(latest['path']).read_bytes().endswith(b'new-photo')
    row = store.row('SELECT * FROM messages WHERE id=?', (first,))
    assert message_image_paths(pipe, row) == [latest['path']]
    archive_pending(pipe)
    assert len(tg.calls) == 203


def test_utf16_transport_limit_and_document_caption(tmp_path):
    payloads = []

    def handle(request):
        payloads.append(request.content)
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})

    tg = TelegramClient('test', httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(TelegramError, match='too_long'):
        tg.send_message(10, '🔎' * 2049)
    assert payloads == []
    assert tg.send_message(10, '🔎' * 2048) == '1'
    document = tmp_path / 'all.txt'
    document.write_text('Полный текст')
    tg.send_document(10, str(document), '🔎' * 1000)
    assert ('🔎' * 500).encode() in payloads[-1]
    assert ('🔎' * 501).encode() not in payloads[-1]


def test_owner_plain_messages_and_card_replies_are_accepted():
    cfg = config_from_dict({'telegram': {'owner_chat_id': 900, 'owner_user_id': 42}})
    message = {'message_id': 1007, 'date': 100, 'chat': {'id': 900},
               'from': {'id': 42}, 'text': 'Работает, больше не нужно'}
    plain = normalize_update({'message': message}, cfg)
    reply = normalize_update({'message': {**message, 'reply_to_message': {'message_id': 1004}}}, cfg)
    assert plain is not None and plain.role == 'owner' and plain.reply_to is None
    assert reply is not None and reply.role == 'owner' and reply.reply_to == '1004'
