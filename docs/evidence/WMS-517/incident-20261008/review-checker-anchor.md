# Независимый технический аудит exact fixture history WMS-517 — 08.10.2026

Проверен точный implementation HEAD `3ff98d2bba17f5d49c7ca55b3a2055031828ec0d` после отдельного test-first commit `e5e4aa5583c445d980e6aac1c1b8bf2f619be4c2`. **Вердикт по этой дельте: PASS; воспроизводимых P0–P2 дефектов не найдено.** Это аудит checker и записи исторической коррекции, не приёмка WMS-517/WMS-666/WMS-689, не закрытие C13, не CI и не подтверждение production.

## Модель и правила

Аудит выполнен отдельной независимой сессией `gpt-6.1-sol`, effort `high`. Opus 5 Extra в каталоге моделей данной сессии отсутствует: вызов Opus не выполнялся, результат нельзя выдавать за Opus review. Предоставленная в поручении прежняя редакция требовала перекрёстного Opus review; в этой границе данный аудит является явно обозначенной доступной заменой, а не доказательством вызова Opus.

При этом фактически прочитанные `AGENTS.md` проверенного checkout и обновлённый `origin/etalon:AGENTS.md` на `a5df04f1560de0eaaf855199065936cb22a222b1` идентичны. Их актуальный раздел «Независимое ревью» после решения владельца 05.10 требует отдельную сессию Sol 6.1, effort high по умолчанию. Модель и независимость этого аудита соответствуют именно этой текущей редакции. Также целиком прочитаны `owner-cases.md` и `failure-cases.md` из `docs/reviews/2026-09-11-analyst-draft/`. Skills не запускались.

## Что проверено

Весь diff `3ff98d2^..3ff98d2` содержит только `scripts/ci/check_task_documents.py` и `docs/reviews/contract-corrections/WMS-517.json`. Тестовый diff `e5e4aa5^..e5e4aa5` содержит только отдельное расширение `scripts/ci/test_fixture_contract_corrections.py`; этот файл идентичен между `e5e4aa5` и проверенным HEAD.

Anchor `3c3c1b69c15cb611c7d256971f9c85ebb9d1ae60` не признаётся произвольным standard test contract. Допуск в строках 613–625 checker требует task WMS-517, полное равенство entry с immutable metadata, точный subject, полный набор девяти changed paths и ancestry в HEAD. Только `backend/tests/test_withdrawal_ledger.py` включён в frozen paths. Decoy `28671d78…`, другой task, другая роль guard, новые paths и изменения metadata не получают этот допуск.

Коррекция `30de00e5f70c3fde354036702aa921ebaab7fd65` закреплена за одним родителем `f2f9b9b835e7e11cabcce1c693e283072417bac2`. Проверены фактические source/parent/correction objects для всех шести путей. Режим каждого — `100644`; `git_blob` отвергает executable, symlink и gitlink. Весь changed-path set 30de должен совпасть с единственным ledger-файлом и пятью companions. Новый transform запрещён вне точного legacy anchor. Ни другой source/correction, ни другая пара blob, ни добавленный runtime-файл не допускаются.

Отчёт fixture-review закреплён за commit `86df6d2a8122c7e43ad14e6aa40d8303f3eb4fa3`, точным путём `docs/evidence/WMS-517/incident-20261008/review-fixture-correction.md` и blob `a07eb01b2907b04828d4caa31f144ba78bd4da3f`. Проверяются отдельный последующий review commit, ancestry, наличие path в его diff, mode/blob в этом commit и HEAD, а также упоминание correction SHA. Исключение для `docs/evidence/` разрешено только этому закреплённому историческому отчёту; обычные fixture entries не получают общего доступа к этому каталогу.

Смешанный ledger сохранён без ослабления старого массива `corrections`. Новая ветка строк 1075–1092 допускает смешанность только для WMS-517 и ровно одного закреплённого fixture entry, затем выполняет обе проверки. Вызов для anchor возвращает baseline 30de только для ledger-теста. Вызов для старого frontend-contract `d0e60d16…` возвращает прежний baseline `9d252003…`. Независимая проба с подменой legacy verdict на FAIL возвращает ошибку и не теряется за успешно проверенной fixture-записью.

## Проверки и воспроизводимость

Выполнены на точном HEAD до создания этого отчёта:

- `python3 -B scripts/ci/test_fixture_contract_corrections.py`: 13 tests, OK, 35.875 s. Новые actual-history проверки включают позитивный 3c3→30de допуск и отрицательные source/correction/path/blob/mode/anchor/companion/review подмены.
- `python3 -B scripts/ci/test_fixture_contract_correction_edges.py`: 5 tests, OK, 5.105 s. Сохранились общие отрицательные проверки позднего mode change, режима самой коррекции, неправильного full review SHA, смешанного формата и semantic allowlist.
- `python3 -B scripts/ci/check_task_documents.py origin/etalon`: exit 0, документы заполнены и AGENTS/CLAUDE совпадают. Это проверка документов, не полный GitHub CI.
- `git diff --exit-code e5e4aa5 3ff98d2 -- scripts/ci/test_fixture_contract_corrections.py`: exit 0.
- Чтение `git ls-tree` и истории ledger после 30de подтвердило в HEAD тот же обычный blob `f20342fe34f3c7d05b96960028087dd2968d0960`; изменений ledger после 30de в данной истории нет.

Дополнительные read-only пробы через `unittest.mock.patch` перехватывали только ответы checker-функций, не меняя Git, ledger или тесты. Для `exact_fixture_corrections(root, "WMS-517", anchor, fixture_ledger)` настоящий положительный ответ — `({"30de00e5f70c3fde354036702aa921ebaab7fd65": {"backend/tests/test_withdrawal_ledger.py"}}, [])`. При подмене `git_blob(root, head, "guards/PROCESS_CONTRACTS.json")` на другой blob этот ответ остаётся положительным. При такой же подмене frozen ledger возвращается `последующая мутация HEAD`; при подмене review path — `нет неизменного отдельного review artifact в HEAD`. Поэтому guard остаётся companion: его будущие process-source изменения сами по себе не блокируются этой исторической записью; ledger и review остаются защищёнными по HEAD.

## C13 и внешние границы

Прочитана постановка коррекции C13 в `docs/requirements/WMS-666.md`, включая C13H1–C13H4 и заключение. Она отдельно атрибутирует 30de каталогу WMS-689 и financial fixture WMS-517, сохраняет сырой запрет guards и будущих backend-изменений и оставляет формальные этапы OPEN. Изменения checker согласованы с этой узкой границей: six-path metadata является доказательством исторического коммита и не создаёт общего разрешения для C13. Этот аудит не выполнял frontend C13 validator, process proof или приёмку соответствующих задач. FX5171–FX5174 и полный CI не объявляются закрытыми.

В новой implementation-дельте нет app/runtime-файлов, HTTP, Redis, Celery, внешнего broker или операций deploy. Checker использует локальные Git subprocess. В точном историческом ledger diff прочитаны `monkeypatch.context()` и существующая autouse `legacy_sales_http`: Redis.from_url заменён RedisBoundary, WB HTTP возвращает synthetic sales, остальные HTTP допускаются только с MockTransport/ASGITransport. Это статическая проверка границы; продуктовый API-gate тест в рамках этого аудита не запускался, отсутствие реальных сетевых обращений новым динамическим прогоном не заявляется.

На момент проверки свободно около 133 MiB на Data volume (df сообщает 100% использования). ENOSPC в запущенных проверках не возник. Кэши и чужие `/tmp` не чистились. Полный CI и более широкий продуктовый прогон здесь не выполнены. Реализация, ledger, защищённые тесты и guard этим аудитом не изменены; единственный создаваемый файл — этот отчёт.
