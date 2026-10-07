# WMS-475 / WMS-537: независимое ревью ремонта WB fixtures

**PASS. Новых дефектов в дельте не найдено.** Независимый reviewer Sol 6.1 high,
06.10.2026. Проверен точный commit `c38e2cfbcc142b50e9dd1d606adddb2a42b19acf`
от базы `18df9a703e39dd7a998caa1757792e23576fd95c`.
Это только test-only delta review, не повторное ревью продукта или общего кандидата.

Прочитаны свежие `origin/etalon:AGENTS.md` и применимые требования WMS-475 R1–R2,
WMS-537 R1–R6 и WMS-683 R1–R2. Библиотеки owner/failure cases прочитаны в этой
независимой review-сессии ранее; skills не вызывались.

В `backend/tests/test_wms475_added_order_stickers.py:111–116,135–138` и
`backend/tests/test_wms537_draft_supply_stickers.py:312–317,347–350` mock чтения
возвращает исходный состав `{475001}` / `{537301}`, а не переданные expected IDs.
Новые IDs появляются только после успешного `await real_add(...)`. Настоящий
`_execute_wb_batch_add` вызывается по-прежнему; продуктовый код не менялся.

AST-сравнение подтвердило неизменность всех 29 assertions WMS-475 и 95 assertions
WMS-537. После удаления только добавленных fixture-узлов весь AST обоих файлов
совпадает с базой: имена, параметры, сценарии, положительные и отрицательные
ожидания сохранены, новых skip/xfail нет. Частичное подтверждение по-прежнему
задаётся отдельным mock `reconcile_supply_orders`; неподтверждённый заказ не
связывается и не получает стикер. Проверки повторов, отмены и Ozon сохранены.

Изолированные пробы непосредственно извлечённых из точного commit функций
fixture прошли для чтения до add, незавершённого add, успешного add, исключения
при add, повторного чтения и независимого состояния следующего теста. Ошибка
или неизвестный результат add не выдумывает подтверждение; запрошенные IDs сами
не расширяют readback. Это модель успешного mock PATCH для тестов стикеров,
а не новое доказательство поведения живого WB при неизвестном результате.
Границы и ограничения WMS-683 не изменены.

В собственном постоянном worktree на точном reviewed SHA один раз выполнено:

```text
cd backend
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR \
  JWT_SECRET_KEY=test-jwt-secret-key-at-least-32-characters-long \
  CELERY_BROKER_URL='' CELERY_RESULT_BACKEND='' \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 0 \
  tests/test_wms475_added_order_stickers.py tests/test_wms537_draft_supply_stickers.py
23 passed, 1 skipped in 51.95s
```

Единственный skip — прежний C8 с PostgreSQL row locking; в SQLite он явно
пропускается, его код и условия не изменены. PostgreSQL-конкуренция в этом
дельта-ревью заново не прогонялась. Ruff двух файлов и `git diff --check` — PASS.
Полный CI не запускался; внешних API-вызовов, печати и production-действий не было.

При начале проверки опубликованный HEAD ветки был точно reviewed SHA. Перед
публикацией отчёта ветка продвинулась до
`a841e067e4883bbb39eec4f6953b06fb92f510c4`; свежий fetch и
`git merge-base --is-ancestor c38e2cfbcc142b50e9dd1d606adddb2a42b19acf FETCH_HEAD`
подтвердили, что точный тестовый commit сохранён в опубликованной ветке
`codex/wms475-537-prefetch-ci-repair-20261006` и доступен CI. Новый HEAD этим
узким ревью не объявляется проверенным.
