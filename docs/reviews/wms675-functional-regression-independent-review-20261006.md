# WMS-675: независимое ревью функциональной регрессии

**PASS — подтверждённых дефектов новой дельты не обнаружено.**

Reviewed SHA: `f98960a1e3d8adcc52264aafdad715f63e2397c5`.
База: `acd0523e9986e89149959319c74fd355c659d22e`.
Ревью: та же независимая сессия Sol 6.1 high, 06.10.2026, по прямому назначению
владельца. Прочитаны текущий AGENTS.md, свежий origin/etalon:AGENTS.md и обе
библиотеки owner/failure cases целиком; навыки не вызывались.
Дельта содержит только incident test, proof и requirements675; product diff пуст.
Предыдущие продуктовые ревью не повторялись.

В `backend/tests/test_wms675_recovery_scenario.py:217–278` вызываются настоящий
provider/transport с `MockTransport` сохранённых карточек и реальные
`ozon_targets → make_observation → save_observations → locks → conduct_supply`.
Inventory, reservation, source recipe, ledger и billing не подменены.
Две подмены (`48–57`) ограничены внешним HTTP и dispatch публикации остатка;
обычные намерения публикации создаются и проверяются в scope tenant/seller.

Проверки `315–386` подтверждают расход26 и остаток каждого из шести SKU,
резерв16→1, исключение4 cancelled+1 awaiting, нулевой расход SKU1695134284.
До восстановления реальные billing services создают11 facts/22 charges;
после сохраняются их IDs/quantity/amount и22 строки начислений, добавляются
15 facts/30 charges/30 строк. Повтор сохраняет те же движения, остатки, резервы,
факты, начисления, строки и completed quantities: новая дельта0.

Независимый прогон точного SHA в собственном permanent checkout:

- Стандартная SQLite без `WMS_TEST_DATABASE_URL`: **2 passed, 0 skipped**, 5.25s.
- Собственная PostgreSQL16.14: **2 passed, 0 skipped**, 7.66s;
  `wms_test_675_independent_review`, `127.0.0.1:56685`.
- Targeted Ruff: **All checks passed**.

В каждом прогоне один и тот же incident test выполнен дважды в одном процессе:
`python -m pytest -q -s -n 0 --keep-duplicates tests/test_wms675_recovery_scenario.py tests/test_wms675_recovery_scenario.py`.
Таким образом проверен и повтор сценария внутри теста, и сброс fixture между
двумя тестами. Оба запуска дали ожидаемые26/16→1/11→26/22→52, без пропуска.
Шесть предупреждений в каждом запуске — deprecation Starlette/Swig.

Привязки к частному имени/порту нет: fixture `60–75` допускает SQLite и тот же
loopback/CI PostgreSQL с префиксом `wms_test`, который уже требует conftest.
Стандартный CI использует SQLite с отдельным файлом каждого xdist-worker;
новый тест не вводит общего ресурса, skip/xfail, session-global patch или
собственного reset поверх стандартного db_session. Последовательный повтор
прошёл на обеих БД. Полная suite/CI не запускались и не объявляются проверенными.

Кластер ревью остановлен. Shared55466/56517/55475, общий кандидат, чужие worktree,
frozen tests, production, секреты и внешняя печать не затрагивались.
Сохранён только этот report в собственной review-ветке. PASS относится к новой
тестовой дельте, не к production recovery или полному итоговому кандидату.
