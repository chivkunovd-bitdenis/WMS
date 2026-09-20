# Вердикт: PASS

F6 закрыта: нормальный путь и отмена управляющей задачи независимо воспроизведены, замки освобождаются штатно до закрытия владеющей ими сессии. F1–F5 остаются закрытыми. Новых находок в проверяемом изменении нет.

Ревьюер: Astra, четвёртый круг перекрёстного ревью бэкенда WMS-453/WMS-455 по WMS-437, 17.09.2026. Проверен detached HEAD `c8be01ede972d05b12388556c984b6942b6b1eae`, база `origin/etalon` — `388f389b8911aa1cae0116323fa38c3e956a60ad`. Исправление F6 — `51778462`. Рабочий каталог — `/Users/deniscivkunov/Projects/WMS/.worktrees/wms453-455-review`.

Прочитаны обязательные `/Users/deniscivkunov/Projects/WMS/AGENTS.md`, обе библиотеки `owner-cases.md` и `failure-cases.md` из основного checkout, требования `docs/requirements/WMS-455.md` и три предыдущих отчёта. Код и тесты не менялись; Git использовался только для чтения. Единственный сохраняемый результат — этот отчёт, без коммита по прямому поручению пользователя.

## F6 — закрыта

В `backend/tests/test_wms455_shared_pool.py:634–643` обёртка стала `@asynccontextmanager`: ожидание `release_first` находится внутри `async with original_lock(...)`, перед `yield`. Поэтому отмена ожидания вызывает выход из уже открытого внутреннего контекста. Сигнал `second_lock_attempted` остался до захвата замка; прежнее взаимное ожидание F3 не вернулось. Блок завершения задач на строках 670–692 и итоговая проверка долей 60/40 не изменены.

Для независимого воспроизведения из AST (синтаксического дерева) текущего теста извлечены и исполнены **без изменения узлов** `observed_lock` (634–643) и блок от `first_task` до конца `except BaseException` (670–692). Использован настоящий `marketplace_seller_lock` из сервиса; только acquire/release заменены двумя блокирующими `asyncio.Lock` с учётом входов и выходов. Повторён прочитанный порядок сервиса: `AsyncExitStack` → сессия → ozon → wb. Наблюдаемая сессия отмечает закрытие, release действительно содержит `await`.

В нормальном пути второй вызов дошёл до занятого ozon при удерживаемых первым обоих замках и установленном сигнале попытки. Затем оба последовательно выполнили работу: first → second; четыре успешных внутренних входа получили ровно четыре выхода.

Для отмены внешний callback вызвал обычный `control_task.cancel()`. Непосредственно перед отменой assertions подтвердили: первый ждёт неотпущенный барьер, оба замка заняты, второй ещё не вошёл в ozon, в очереди настоящего `asyncio.Lock` уже есть незавершённый ожидающий, обе дочерние задачи не завершены. После возврата ошибки из исходного блока оркестрации, **до следующего await**, проверены завершение обеих задач, свободные замки, равенство входов/выходов и порядок закрытия ресурсов:

```text
NORMAL: done=True/True; ozon=False; wb=False; entries/exits=4/4
        first save → first exit wb → first exit ozon → first close
        second save → second exit wb → second exit ozon → second close
CANCEL: done=True/True; ozon=False; wb=False; entries/exits=2/2
        second close
        first exit wb, session.closed=False
        first exit ozon, session.closed=False
        first close
```

В отменённом пути обе дочерние задачи имеют `cancelled=True`; второй не захватил ни одного замка. Каждый успешный внутренний вход имеет ровно один выход до закрытия **его** сессии. Барьер отпущен, незавершённых задач нет, все внутренние генераторы закрыты (`ag_frame is None`). На контекстные менеджеры удерживались сильные ссылки, автоматическая сборка мусора была отключена; `asyncio.run`, `gc.collect` и `shutdown_asyncgens` не использовались. Assertions прошли до закрытия event loop. Код выхода итогового пробника — 0.

Первый вариант моего пробника прошёл нормальный путь, но отдельная корутина-наблюдатель опоздала к окну отмены: её assertion о неотпущенном барьере завершился ошибкой, код 1. В итоговом пробнике изменена только синхронизация внешней подачи отмены: callback поставлен в очередь перед сигналом `second_started`, а при исполнении проверяет фактическое ожидание занятого замка. Извлечённые обёртка и оркестрация теста в обоих прогонах неизменны. Предварительный запуск не использован как доказательство закрытия F6.

## F1–F5 и границы diff

`git diff --stat 70f23381..c8be01ed -- backend`:

```text
backend/tests/test_wms455_shared_pool.py | 43 +++++++++++++++++++-------------
1 file changed, 26 insertions(+), 17 deletions(-)
```

Полный diff подтверждает только импорт `asynccontextmanager` и замену обёртки с поясняющим комментарием. Рабочие сервисы, API, модели, миграции и тесты WMS-453 относительно третьего круга не менялись. Поэтому F1 (повтор A после B), F2 (защита отката частичного количества), F4 (атомарный rollback SQLite), F5 (область ключа операции) сохраняют закрытый статус без повторения отдельных пробников. F3 дополнительно подтверждена нормальным сценарием выше: сигнал до захвата, отсутствие взаимного ожидания, завершение обоих вызовов. Прежний набор регрессионных тестов повторён полностью.

## Команды и результаты

Читающие проверки из корня: `pwd`, `git status --short`, `git rev-parse HEAD origin/etalon`, `git symbolic-ref -q HEAD`, `git log --oneline 70f23381..c8be01ed`, `git diff --stat 70f23381..c8be01ed -- backend`, `git diff --name-only 70f23381..c8be01ed -- backend`, полный backend-diff и `git diff --check`. SHA совпали с заданием; symbolic-ref вернул 1 без вывода (detached HEAD); diff-check без замечаний. Исходный статус уже содержал untracked-каталог ночных отчётов, tracked-правок нет.

Из `backend` выполнено (переменная ниже — сокращение полного пути к использованному Python):

```sh
REVIEW_PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
"$REVIEW_PY" -m ruff check .
"$REVIEW_PY" -m mypy .
env -u WMS_TEST_DATABASE_URL "$REVIEW_PY" -m pytest -n auto -ra tests/test_wms455_shared_pool.py tests/test_fbs_stock_rule_service.py tests/test_wms351_marketplace_publication_switches.py tests/test_fbs_ozon_lane.py tests/test_ozon_box_positions.py tests/test_ozon_box_assembly.py tests/test_fbs_packing_box.py tests/test_fbs_box_clear_and_workspace_extras.py tests/test_fbs_supply_assembly.py tests/test_ozon_posting_contract.py tests/test_fbs_cancelled_after_pack.py tests/test_wms325_document_mutations.py
"$REVIEW_PY" -m alembic heads
"$REVIEW_PY" - <<'PY'
# Независимый пробник F6 через stdin, описанный выше:
# ast.parse текущего теста; compile неизменённых observed_lock и оркестрации;
# настоящий marketplace_seller_lock с блокирующими asyncio.Lock;
# normal и внешний control_task.cancel(); assertions очистки до закрытия loop.
PY
```

- Ruff: `All checks passed!`, код 0.
- Mypy: `Success: no issues found in 460 source files`, код 0.
- Pytest: **292 passed, 7 skipped, 47 warnings in 33.98s**, код 0; 299 тестов, 8 workers. Предупреждения — SWIG и отражение expression-index в двух SQLite-тестах миграции.
- Alembic: единственная голова **`20260917_0500 (head)`**, код 0.
- Итоговый независимый пробник F6: **PASS**, код 0; результаты приведены выше.

Семь пропусков относятся к PostgreSQL: C16 WMS-455; конкурентное добавление WMS-453; row-level lock в `test_fbs_supply_assembly.py:337`; четыре проверки rollback/savepoint в `test_wms325_document_mutations.py:270,351,432,493`. В этом круге они не выдаются за мои PostgreSQL-проверки. Переданный ведущим результат аналитика — PostgreSQL 17, **19 passed по файлу WMS-455, включая C16** — учтён отдельно как внешний результат; самостоятельно он здесь не повторялся.

Полный pytest проекта и общий `check_migrations.py` не запускались. Фронт, браузер, HTTP-стенд, production и внешние кабинеты в этот круг не входят. PASS означает закрытие F6 и отсутствие регрессии в проверенном периметре бэкенда; продуктовая приёмка и деплой этим отчётом не подтверждаются.
