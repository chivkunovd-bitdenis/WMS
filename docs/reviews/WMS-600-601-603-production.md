# WMS-600 / WMS-601 / WMS-603 — точечный production-выпуск

30.09.2026 владелец разрешил: «выкати пока точечно шк и сортировку». Состав выпуска: распознавание коробов FBS, группировка подбора по ячейкам и устранение 500 большого каталога. WMS-593–597, WMS-599 и нативный ТСД не включены; миграций нет.

- Проверенный исходный SHA: `3cbabfe5435ff9f1fea5bebabd60ee904c7c6b53`; независимый release-scope review Sol — PASS, 17 изменённых путей.
- Локальные проверки именно этого SHA: 4 backend-теста (WMS-601/603), 4 Vitest для WMS-600, Ruff, mypy (532 файла), TypeScript и production build — PASS.
- [PR #307](https://github.com/chivkunovd-bitdenis/WMS/pull/307) слит в etalon. Merge SHA: `feac07f90f85e84bfaf1d4cab4e9981903f350d1`; дерево полностью совпало с проверенным SHA.
- [CI 36724192050](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/36724192050): backlog, frontend-build, backend — SUCCESS.
- [Deploy Production 36726679280](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/36726679280): SUCCESS. Выполнены штатные backup, проверка миграций и перезапуск; новые API/web-контейнеры запущены около 14:10 UTC.

## Проверка работающего сервера

`/opt/wms` HEAD — `feac07f90f85e84bfaf1d4cab4e9981903f350d1`. SHA-256 трёх сервисов внутри работающего API совпали с исходниками проверенной ветки:

- fbs_picking_service.py: `5a0ef4f6d787f50b8028eeb1346d724cfdd4bb57b60d772cd174ae19cd1f8598`
- inventory_container_service.py: `e86638dffb09d28068cdeeda2aab1fee3a6ba990ca84f3cc2b82e04be7df66f3`
- marking_code_service.py: `e2d0a3a6386ade4d2bf76ce2ba753db2a9fe87add819da0961ae8b772ab03c44`

Главная страница и seller — HTTP 200; `/api/health` — `{"status":"ok"}`. Публичный `/assets/UnloadPickScreen-CZ1J2Glq.js` содержит новую группировку `fbs-pick-item-`; SHA-256 `0f3ea59939b6490f395834ada233ea80268cb101b78129a533b7b5b4a255c11c` совпал с файлом работающего web-контейнера.

В production-сессии с `SET TRANSACTION READ ONLY` выполнены:

1. Точный `INB-M5KSFV1J1XP9WW`, нижний регистр и вариант `]C1INB-M5KSFV1J1XP9WW` — один и тот же существующий короб.
2. `J-1-4` — та же ячейка, которую подтверждали при WMS-602.
3. Вызов самого обработчика `get_linked_wb_catalog` для проблемного селлера — 55 202 строки за 24,41 секунды, без прежнего превышения параметров PostgreSQL. Это проверка обработчика и реальной БД внутри API, а не выдача прямого вызова за внешний авторизованный HTTP-запрос.

Транзакция завершена rollback; количество и складские движения не менялись. Физическая строка проблемного скана владельца ещё не получена, поэтому конкретная этикетка и работа физического сканера не объявляются принятыми. Производственный браузерный проход оператором не выполнялся; факт отдачи нового интерфейса подтверждён публичным артефактом и совпадением хешей.
