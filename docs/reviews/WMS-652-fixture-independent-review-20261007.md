# WMS-652: независимое ревью исправления fixture, 07.10.2026

**Вердикт: PASS.** Исправление тестового стенда исполняет настоящий серверный
проверяющий скрипт до Docker, подменяет его внешние ответы GitHub и сохраняет
прежние ожидания тестов. Обхода доверенной проверки или принудительного успеха
не обнаружено. Этот вердикт относится только к указанному fixturefix; он не
является приёмкой всего WMS-652, результатом полного CI или подтверждением деплоя.

Проверен commit `aed6d802af1ce880abeabc7f9bff65d6365e2729` относительно
`f6066d68bd198794602a6e8916612d0d3b32460f`. Diff содержит ровно два файла:
`backend/tests/test_prod_deploy_backup.py` и `.agent-runs/ci-blocker-handoff.md`.
Работа проведена в постоянном worktree `.worktrees/night1007-wms652-ci-fix`,
ветка `codex/night1007-wms652-ci-fix`. Новых агентов не запускал; проверки
выполнялись последовательно одним процессом, без установки зависимостей и сборок.

Прочитаны полностью локальный `AGENTS.md`, `owner-cases.md` и `failure-cases.md`
из `docs/reviews/2026-09-11-analyst-draft`, а также документ передачи контекста.
После `git fetch origin etalon` сверено `git show origin/etalon:AGENTS.md`:
локальные правила совпадают. Из библиотеки сбоев здесь применимы B14
(сохранить смысл проверки при устранении красного CI) и B11 (различать исходный
commit, включение в выпуск и фактическую выкладку). Другие продуктовые сценарии
не превращены в дополнительные требования к этому техническому исправлению.

## Что проверено

| Проверка | Вердикт | Основание |
| --- | --- | --- |
| Настоящий `verify_server_process_ci.py` исполняется до Docker | PASS | Fixture копирует исходный verifier и `verify_ci.py` без изменения. Неизменённый `prod-update.sh` использует `set -euo pipefail` и на строке 83 синхронно запускает Python; первое Docker-действие возможно только далее, на строке 90 или 98. Отрицательный опыт ниже подтвердил остановку. |
| Подмена новой fixture ограничена внешней GET-границей GitHub | PASS | `sitecustomize.py` заменяет только `urllib.request.urlopen`, возвращая JSON через `BytesIO`. Сам `public_api_get` по-прежнему создаёт GET на `https://api.github.com/`, а `verify`, `pages`, проверки jobs/artifact и повторное чтение run исполняются реально. Неизвестный маршрут вызывает ошибку. Старые git/docker/curl-заглушки сохранены. |
| Snapshot согласован с точным synthetic SHA/run/attempt | PASS | SHA `a` × 40 совпадает с прежней git-заглушкой; workflow 987, run 654, attempt 1, check-suite 321, восемь обязательных jobs и artifact 777 связаны согласованно. Имена/статусы проверяет реальный verifier. Значения являются тестовыми ответами API, а не свидетельством реального зелёного CI этого commit. |
| Нет green-forcing или bypass trusted gate | PASS | Нет подмены результата verifier, `python3`, `verify_server_ci` или `GateError`; нет `skip`, `xfail`, раннего успешного выхода или игнорирования кода отказа. `WMS_DEPLOY_GUARD_ONLY` остаётся `0`. Production, workflow, доверенные хеши и существующий negative gate suite отсутствуют в diff. |
| Прежние backup/rollback/network/retry assertions сохранены | PASS | Сравнение синтаксических деревьев Python подтвердило идентичность всех прежних выражений `assert`; добавлены только два новых assertions про gate. Параметры прежние: success/dump/archive/listing/empty/network/retry и два bootstrap-случая. Сохранены запрет migrations при ошибке dump/archive, остановка writers до dump, проверка архива до migrations, отказ topology до build/stop, retry после сбоя, область остановки legacy listener и приватные права 0700/0600. Нового доказательства полноценного восстановления БД этот тест не добавляет. |
| Узкая повторная проверка положительного пути, network и retry | PASS | Три существующих случая прошли без изменения ожиданий, одним процессом; результат ниже. |
| Отказ реального gate внутри этой же fixture не допускает Docker | PASS | Изменение только `artifact.expired` в ответе GitHub дало exit 2, ноль Docker/curl-действий и отсутствие backup. Маркер первого GET уже существовал и не позволил продолжить запуск. |

## Ограниченное независимое доказательство

Перед исполнением побайтово сверены с проверяемым SHA пять используемых файлов:
тест, `prod-update.sh`, `verify_server_process_ci.py`, `verify_ci.py` и
`scripts/ci/tests/test_server_process_gate.py`. Старые assertions сравнивались
через `ast.dump`; исключены ровно два вновь добавленных gate assertions.

Выполнена команда:

```sh
PYTHONDONTWRITEBYTECODE=1 pytest -n 0 -q -p no:cacheprovider \
  'backend/tests/test_prod_deploy_backup.py::test_deploy_requires_verified_backup_before_migration[]' \
  'backend/tests/test_prod_deploy_backup.py::test_deploy_requires_verified_backup_before_migration[network]' \
  'backend/tests/test_prod_deploy_backup.py::test_deploy_requires_verified_backup_before_migration[retry]'
```

Результат: **3 passed, 6 warnings in 11.49s**, exit 0. Предупреждения относятся
к существующим deprecated FastAPI/Swig API. Авторские 9 backup tests и 11 gate
tests из передачи контекста не выдаются за повторно выполненные мной наборы.

Дополнительно выполнен один отрицательный опыт через прямой вызов неизменённой
функции `test_deploy_requires_verified_backup_before_migration(tmp_path, '')`.
Функция импортирована из проверенного файла. В памяти процесса через
`unittest.mock.patch.object(Path, 'write_text', ...)` изменена только строка
`'expired': False` на `'expired': True` при записи временного `sitecustomize.py`.
Исходники теста, production script и обоих verifier не изменялись. Вызов
`subprocess.run` обёрнут исключительно для ограничения timeout до 15 секунд
и сохранения настоящего результата; запускался реальный Bash/Python.

Наблюдение: **7 подменённых GET-запросов**, включая
`/actions/runs/654/artifacts?...`; настоящий verifier вернул **2** с сообщением
«Отчёт CI просрочен…». `commands.jsonl` содержал только git-команды:
**ни одного Docker или curl**, каталог backup отсутствовал. Неизменённый тест
отверг сценарий: поиск обязательного `stop` завершился `StopIteration`, поскольку
до этой операции запуск не дошёл. Все перечисленные условия проверены assertions
самого отрицательного опыта. Временные файлы удалены `TemporaryDirectory`.

## Уточнение о маркере

`TEST_GATE_PASSED` на строке 143 теста создаётся при первом `urlopen`, а не после
успешного завершения verifier. Поэтому комментарий на строках 101–102, текст
assertion на строке 177 и соответствующая фраза handoff описывают силу самого
маркера неточно. В retry маркер также остаётся от первой попытки. Это ограничение
добавленного вспомогательного assertion, а не обнаруженный обход gate в данном
SHA: реальное завершение до Docker обеспечивает неизменённый последовательный
Bash с `set -e`, и отрицательный опыт выше подтвердил отказ при уже существующем
маркере. PASS не основан на существовании этого файла.

## Граница изменений ревьюера

Ревьюер создал только этот отчёт. Тесты, продукт, CI, требования и документ
передачи контекста не исправлялись. Во время работы появилась чужая правка
`frontend/tests-e2e/wms672-dom.test.tsx`; её содержимое не включалось в ревью,
не изменялось и не должно входить в commit отчёта. Полный CI и деплой не
запускались. Commit/push отчёта подтверждают сохранность ревью, а не выпуск кода.
