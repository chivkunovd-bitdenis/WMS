# WMS-652: отдельный контракт критических FBS-путей

База `cb0da8fd79e7fa92b1c882c3bebc9b15a55ebd3e` включает постановку R41–50/C53–63.
Авторство: отдельный тестировщик. Продукт/CI/checker не меняются; прежние защищённые
ожидания меняются только в явно разрешённом R50 фазовом контракте старой гонки.

## Checkpoint1: миграция PG create race по R50

Случай **сохранил прежний pytest ID**:
`backend/tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply`.
Он теперь детерминированно удерживает mock ADD после committed pending_confirmation.
Проверяется persisted canonical operation/supply/WB ID и отсутствие order binding
до ответа; второй ASGI-запрос обязан дать503/operation_in_progress/retryable=true
с точным canonical context. После освобождения ADD winner201; тот же loser
послеconfirmed обязан дать409/order_incompatible. В итоге одна поставка,
одна confirmed-операция, order bound/in_supply, ровно один mock create и ADD.
Реальные external calls не используются: существующий e2e WB mock остаётся.

- `race-before.txt` сохраняет исходный недетерминированный тест.
- `race-old-red.log`: при управляемой фазе старое ожидание409 падает на
  **503 с operation_in_progress/pending_confirmation**. Setup succeeded;
  это содержательное рассогласование старого ожидания с фазой, не product regression.
- `race-green.log`/`race-green.xml`: мигрированный тест **1 PASS,0 SKIP**;
  обе обязательные HTTP-фазы и все DB/count invariants исполняются одним case.
- `race-negative-control.py`/`race-mutants-red.log`: in-memory порча настоящего
  `_create_operation_in_progress` на generic503 code, чужой canonical ID и
  retryable=false даёт **3 содержательных FAIL**. Product bytes неизменны.
  Охрану от изменения самого assertion/helper/manifest выполняет отдельная
  инфраструктурная часть R45/R46; здесь она не реализуется и не объявляется PASS.
- Ruff `tests/test_fbs_supply_from_orders.py` — PASS.

Команда из backend:

```sh
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test_runner@127.0.0.1:56635/wms_test_652_fbs_contract /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply -q -n0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session --junitxml=../docs/evidence/WMS-652/critical-fbs-contracts-20261006/race-green.xml
```

PostgreSQL17 — отдельный synthetic test cluster на loopback56635/database
wms_test_652_fbs_contract. CI подставляет свою существующую isolated wms_test DB;
обязателен PG backend безskip, `-n0` и обе session loop настройки.

Для negative controls скопировать сохранённый `race-negative-control.py` в
`/tmp/test_wms652_race_negative.py`, запускать из root с `PYTHONPATH="$PWD/backend:$PWD/backend/tests"`
и той же WMS_TEST_DATABASE_URL:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -c backend/pyproject.toml -p tests.conftest /tmp/test_wms652_race_negative.py -q -n0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session
```

**Dependency closure для freeze:** основной test file (включая четыре `_create/_setup`
helper), `backend/tests/conftest.py`, `backend/tests/fbs_seed_helpers.py`,
`backend/tests/inventory_actor_helpers.py`; общий runner/pytest config уже
принадлежат инфраструктурной защите ведущего. Evidence-only negative-control
не является новым постоянно collected testcase и не должен увеличивать PG count.

Checkpoint1 не завершает C54/регрессионную карту. Настоящий QR-input path и
selection→create/add остаются отдельными следующими тестовыми шагами.
Независимое ревью/аналитическая приёмка/fullCI/production здесь не заявлены.
