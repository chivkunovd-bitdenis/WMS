# WMS-662 — один steady-state PostgreSQL прогон: RED

06.10.2026. Продолжение interrupted tester после ENOSPC. Исходный checkout
`cc63343890eca726f1442122b660fd8502c59ba8`, продукт
`ef9225bb26d1050e3d4fe18b66d8f1f241f9368c` неизменён:
`git diff ef9225bb -- backend/app` пуст. Прочитаны текущий AGENTS.md,
обновлённый origin/etalon и astra-batch-causality-7f62e184.md.
Это тестирование одного дополнительного состояния, не общая приёмка или CI.

## Сохранность контракта

Новый `backend/tests/test_wms662_batch_handoff_steady_state.py` восстановлен
из собственного untracked draft. Исправлено только оформление импорта через
apply_patch; продуктовых исправлений нет. A/B имеют supplier_status=delivering
и required_meta_json=[] ДО существующего setup commit. Остальное исходное
состояние, три заказа/поставки A(P1), B(P2), C(P2), лимит 2, настоящие публичные
sync/normal_handoff и транспорт C сохранены. Барьер и лимиты 8/15 секунд
унаследованы без изменения из frozen BatchSchedule. Наблюдатели добавляют
UUID Product для attempt/acquired и параметры UPDATE fbs_orders.

Старый тест 7f62e184 побайтово неизменён: Git blob
`eb2255ca93ac453af1117339aa6cc9aba07ee2a0`. Хвост нового теста от
`assert not schedule.harness_errors` до конца побайтово совпадает со старым;
business_issues/tariffs импортируются без изменения. AST сравнение тела теста
показало только три новые операции установки полей A/B и diagnostic print.
Ожидания 1800 для КАЖДОГО заказа, расходы, резервы, факты, recovery/retry,
запрет повторной внешней передачи и сохранение первой SQL ошибки не ослаблены.

## Один фактический запуск

Пустой собственный каталог `/tmp/wms662-steady-pg-55468-68206` не содержал
валидного кластера; порт 55468 был свободен. В нём создан PostgreSQL 16.14,
loopback 127.0.0.1:55468, пользователь wms_test, база wms_test_662_steady,
shared_buffers=16MB, max_connections=20. Большой ramdisk не выделялся.
До и после теста SQL подтвердил 0 других client connections этой базы.
55466, 56517 и текущая БД приложения не использовались и не изменялись.

Из backend с PYTHONDONTWRITEBYTECODE=1,
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55468/wms_test_662_steady,
WMS_TEST_DATA_DIR=/tmp/wms662-steady-data-55468 выполнено ровно один раз:

```
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -s -p no:cacheprovider tests/test_wms662_batch_handoff_steady_state.py --tb=short
```

**1 failed, 6 warnings in 3.18s, exit 1. RED на последнем business assertion,
не timeout/ошибка стенда. SQLSTATE=[('ordinary', '40P01')], pg_cycle=True,
results=[None, None].** Исходный stdout/traceback и серверный журнал сохранены
рядом в steady-state-single-run-evidence.txt; это не повторный запуск.

Batch PID 78544, ordinary PID 78542. P1=1194dce1-382e-4731-80dc-032055237465,
P2=fb0e8d44-43d4-4efe-b60c-fe8178d1cc42. До первого Seller batch получил
только P1. Ordinary получил P2 четырьмя явными Product SELECT и затем ожидал
Seller, удерживаемый batch. Наблюдатель увидел реальное ожидание ordinary→batch
на Seller и отпустил барьер; позднее он подтвердил взаимное ожидание.

Важная точность: batch тоже получил свои явные Product(P2) SELECT.
Серверный deadlock detail фиксирует встречное ожидание batch при **INSERT
INTO fbs_shipment_reversal_ledger**, а не при явном Product SELECT:
78542 ждёт ShareLock транзакции 742 от 78544 на Seller FOR NO KEY UPDATE;
78544 ждёт ShareLock транзакции 751 от 78542 при INSERT ledger.
Конкретный внутренний FK tuple lock отдельным измерением не установлен.
Нельзя заменять этот SQL вывод предположением «batch застрял на Product».

До conduct A/B observer сохранил по одному UPDATE только с last_wb_sync_at;
второй UPDATE supplier_status/required_meta_json исчез. Строка str(clause)
в диагностике является generic SQLAlchemy шаблоном со всеми колонками;
None в compiled defaults НЕ означает фактическую запись NULL. Реальные
переданные параметры ранних UPDATE содержат last_wb_sync_at и ID заказа.

## Деньги, остаток, восстановление и граница передачи

После конкурентного прохода A=1800, B=1800, **C=0 вместо 1800**;
у C также отсутствуют две service charges и один work fact.
P1=12 (13→12), P2=10 (12→10), резервы сняты. Billing перехватил deadlock,
поэтому оба публичных вызова вернули None, но observer сохранил 40P01.

В том же единственном тесте штатное recovery восстановило C до 1800,
последующий retry прошёл проверки неизменности денег, остатка, резервов,
движений, фактов и операций без новой внешней сдачи. Дополнительное чтение SQL
после теста подтвердило A/B/C по 1800 и по две charges. Первоначальные ошибки
сохранены: recovery не превращает исходный конкурентный проход в GREEN.

Новый evidence gate **не PASS**: нормализованная сцена действительно дала RED.
Это новое доказательство конкретного расписания; общий архитектурный диагноз,
причинность относительно baseline и способ исправления здесь не заявляются.
Следующему исполнителю передать этот тест и точный SQL cycle для разбора.
Архитектурных исправлений, полного перезапуска WMS-662, live, браузера,
секретов, дополнительных агентов/skills, merge или deploy не было.
Ruff нового файла PASS; проверка документов задач PASS. Чужие untracked
result files сохранены, requirements/guards/product/frozen test не изменены.
