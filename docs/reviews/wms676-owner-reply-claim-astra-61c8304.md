# WMS-676: независимое DELTA-ревью исправления F1

**Вердикт: FAIL** на точном SHA
`61c8304bccaf76b8af707a0ae2f85cbed2d59dd0`, база сравнения —
`b1e3b7dd48f9a2ad24ad129bdf6b01aab3d1cbe6`.
Исходная гонка проверки и захвата исправлена, но требование выполнить всю
файловую подготовку до последнего claim пока нарушено. Установка этого
кандидата по результату данного ревью не разрешается.

Назначение этой отдельной сессии по прямому запросу — Astra high DELTA review;
фактические параметры модели отдельным инструментом здесь не измерялись.
Эта сессия не разрабатывала проверяемый код. Навыки, дополнительные агенты
и модельные вызовы не запускались. Изменяется только данный отчёт.

## Основание и сохранность

Полностью прочитаны локальный AGENTS.md, owner-cases.md и failure-cases.md.
После fetch прочитаны правила origin/etalon на
`954862b718f9f2f1faefb2f00ad2fef72a6e1929`; прямые ограничения владельца
на это ревью имеют приоритет. Прочитаны R9–R12/C17–C22 требований WMS-676,
первоначальный FAIL `19a76b72af656b808f22717add5613dbeb51f35b`, отдельный
RED-контракт `ce9f43c8206b76f2a6959a54bd0e91bfdb184a04`, его handoff и
`wms676-owner-reply-claim-developer.md`.

Сам fix относительно ce9f43c8 меняет ровно два продуктовых файла — store.py
и telegram.py — и отчёт разработчика. Тесты, требования и guards побитово
не изменены. Delta от b1e3b7 дополнительно включает уже названные независимый
FAIL и отдельный RED-контракт; это не правка frozen-тестов разработчиком.
`git diff --check b1e3b7 61c8304` проходит. Чужие untracked-файлы сохранены.

## F1.1 — P1: чтение файла осталось после claim, до сетевого вызова

Место: `tools/support_agent/support_agent/telegram.py:303–324` и
`TelegramClient.send_document`, строки 94–96 того же файла.

Перенесено только создание длинного текстового файла. После успешного
pending → sending dispatcher вызывает send_document, а тот ещё выполняет
`Path.read_bytes()` до `_call` и HTTP POST. Это блокирующая файловая операция:
во время чтения другой процесс может сохранить запрет или отзыв разрешения.
Новой проверки после чтения нет. Та же проблема относится к обычным вложениям.
Утверждение отчёта разработчика об отсутствии файловой подготовки после claim
не подтверждается полным путём до сети.

На точном SHA воспроизведены три порядка операций на двух соединениях одной
временной синтетической SQLite. Использован настоящий TelegramClient и его
send_document, HTTP заменён записывающим двойником; сеть не вызывается.
Callback в Path.read_bytes проверяет status=sending, отсутствие HTTP-вызовов
и завершённую транзакцию claim. Затем второе соединение сохраняет соответственно:

1. паузу чата для ранее разрешённого обычного длинного ответа;
2. отзыв источника точного разрешения и revision=2;
3. текущую версию обращения v2 вместо одобренной v1.

После реального чтения файла HTTP-двойник во всех трёх случаях подтвердил,
что актуальный outbox_delivery_allowed уже False и DB-транзакция закрыта,
но всё равно получил один POST. Результат каждого flush — 1, строка стала sent.

Это **не повтор исходного нарушения до claim**: новые три frozen-проверки
исходной гонки проходят. Это оставшееся нарушение прямо заданного условия
этого ревью «claim AFTER budget/local file prep; no wait after claim till network».
Ревью не требует отзывать уже ушедший запрос или держать SQLite-транзакцию
в течение сети. Нужно подготовить неизменяемые байты документа до последней
атомарной проверки и передать их в сетевой метод без повторного чтения пути.
Само перемещение ещё одного guard перед send_document проблему не устраняет.

Минимальное воспроизведение варианта с отзывом разрешения, без изменения тестов:

```python
# PYTHONPATH=tools/support_agent python3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from tests.test_owner_client_reply_pause import paused, CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from tests.test_owner_client_reply_pause_cli import _source
from support_agent.store import Store
from support_agent.telegram import TelegramClient, flush_outbox

with TemporaryDirectory(prefix="wms676-delta-review-") as folder:
    fixture = paused.__wrapped__(Path(folder))
    e = next(fixture)
    other = Store(e.path)
    try:
        body = ("Проверенный длинный ответ. " * 200).strip()
        source = _source(e, e.store.client_reply_approval_text(
            CLIENT_CHAT, e.ticket, "v1", body))
        key = e.store.approve_client_reply(
            chat_id=CLIENT_CHAT, ticket_id=e.ticket, version="v1", text=body,
            owner_user_id=OWNER_ID, owner_chat_id=OWNER_CHAT, source_message_id=source)
        calls = []

        class HttpDouble:
            def post(self, url, **kwargs):
                assert not e.store.db.in_transaction
                assert not e.store.outbox_delivery_allowed(
                    e.store.outbox_by_key(key), owner_user_id=OWNER_ID,
                    owner_chat_id=OWNER_CHAT)
                calls.append(kwargs)
                class Response:
                    status_code = 200
                    def json(self):
                        return {"ok": True, "result": {"message_id": 1}}
                return Response()

        read = Path.read_bytes
        def read_after_revocation(path):
            assert e.store.outbox_by_key(key)["status"] == "sending"
            assert not calls and not e.store.db.in_transaction
            other.set_message(source, text="Разрешение отозвано", revision=2)
            assert not other.db.in_transaction
            return read(path)

        with patch.object(Path, "read_bytes", read_after_revocation):
            sent = flush_outbox(e.store, TelegramClient("synthetic", HttpDouble()), e.cfg)
        assert sent == 1 and len(calls) == 1  # воспроизведение дефекта
    finally:
        other.db.close()
        fixture.close()
```

## Что подтверждено положительно

Store.transaction действительно начинает BEGIN IMMEDIATE. Внутри claim заново
читается только pending-строка, политика точного чата, актуальный источник,
автор/чат/revision источника, текущая версия обращения и полное тело разрешения.
Сравниваются key/chat_id/ticket_id/purpose/text/file_path/reply_to с намерением,
из которого подготовлена отправка. Только затем выполняется UPDATE sending
и увеличение attempts. COMMIT происходит до возврата claim и до отправки.
Отдельная синтетическая проверка SQL trace подтвердила BEGIN IMMEDIATE…COMMIT,
повторный claim не проходит. Семь отдельных изменений перечисленных полей
отклонены, строка сохраняется pending с attempts=0.

В синхронном dispatcher нет limiter, semaphore или await; ожидание тестового
CallbackLimiter заканчивается до настоящей транзакции. Межпроцессная запись,
завершённая до BEGIN IMMEDIATE, теперь учитывается. Python-lock не используется
в качестве единственной защиты. Транзакции через сеть нет; оставшийся риск
относится именно к файловому чтению внутри send_document.

Синтетический source 334/msg473 с настоящим owner id и смыслом «сначала
анализируй и сообщай гипотезы владельцу» отвергнут настоящим main CLI:
код 1, specific_owner_reply_approval_required, новой строки outbox нет.
При этом загрузка конфигурации, Store и чтение входного текстового файла
подменены синтетическими данными. Final и file без ticket_id также не отправлены,
пауза неизменна. Это проверка переданного смысла источника, не чтение живого 334.

Пауза по-прежнему охватывает весь точный чат, включая старую очередь, сообщения
без ticket_id, файлы и финальные ответы. Generic semantic approval не снимает её.
Новое точное разрешение проверяет автора, чат, источник, тело, обращение и версию;
создаёт только одну новую строку с уникальным ключом, повтор не дублирует её
и не выпускает прежнюю очередь. Другой чат и канал владельца доступны.
История, анализ и состояния задач не меняются.

Пути unknown, interrupted sending, not_sent, rejected/failed, sent и repeat_ok
не изменены. Целевые и соседние проверки подтверждают отсутствие слепого повтора
клиентского unknown/sending, допустимый повтор not_sent, окончательность отказа,
идемпотентность и сохранение маршрута к владельцу. Это не заявление о runtime.

## Выполненные проверки и передача

Единственный ограниченный pytest-прогон — **65 passed in 0.85s**, без skips:
24 целевых (frozen6 + CLI15 + race3) и 41 соседняя проверка.

```sh
PYTHONPATH=tools/support_agent python3 -m pytest -q -o addopts='' \
  tools/support_agent/tests/test_owner_client_reply_claim_race.py \
  tools/support_agent/tests/test_owner_client_reply_pause.py \
  tools/support_agent/tests/test_owner_client_reply_pause_cli.py \
  tools/support_agent/tests/test_agent_tools.py \
  tools/support_agent/tests/test_runner_and_safety.py \
  tools/support_agent/tests/test_two_bots.py \
  tools/support_agent/tests/test_cli_diagnostics.py
```

Дополнительно выполнены только узкие проверки найденного файлового окна,
source334 и атомарного claim, описанные выше. Полный набор и несвязанные проверки
не повторялись. После успешного pytest и трёх файловых воспроизведений следующая
попытка временного сценария не стартовала из-за No space left on device;
source334 и payload/SQL trace затем успешно проверены на SQLite :memory:.
Чужие файлы для освобождения места не удалялись. Исторические RED не повторялись;
ruff/mypy из отчёта разработчика не выдаются за проверку этой сессии.

Исполнителю: закрыть F1.1 с отдельным тестом реального send_document-пути,
сохранив frozen-контракт, все состояния и защиту неизвестного исхода. После
исправления нужен новый точный SHA и независимое DELTA-ревью. Браузер, рабочая
БД, Telegram, секреты, установленный runtime, установка и деплой не затрагивались.
Приёмка и полный CI не выполнены. Установку выполняет ведущий отдельно после PASS.
