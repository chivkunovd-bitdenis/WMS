# WMS-440…445 — выкладка на staging 13.09.2026

## Итог

Backend и web выложены на Railway staging из одного release-коммита
`b2a284196715ebe6904581a898f7510d31440a50`.

- `origin/staging` после push: `b2a284196715ebe6904581a898f7510d31440a50`.
- Railway backend deployment: `32a3ef78-c526-4291-8e3e-0a4637977264`, `SUCCESS`, commit hash совпадает.
- Railway web deployment: `3258c0c1-a855-444d-bf1f-23414bdf26c0`, `SUCCESS`, commit hash совпадает.
- `GET https://wms-production-780c.up.railway.app/health`: HTTP 200, `{"status":"ok"}`.
- `GET https://wms-production-780c.up.railway.app/openapi.json`: HTTP 200.
- `GET https://web-production-9e7c1.up.railway.app/`: HTTP 200.

Production и ветка `main` не изменялись.

## Почему понадобился второй deploy

Первый push `f8f9ff3de97861922008f32f2794ae1cdbbbce30` успешно развернул web, но новый
backend-контейнер не стартовал: staging-БД уже находилась на Alembic revision
`20260911_0305`, которой не было в устаревшей Git-ветке `origin/staging`.

Release-ветка сохранила точную ранее развернутую историю до `d6554059` и добавила
пустую merge-миграцию `20260913_0307` с родителями `20260911_0305` и
`20260913_0306`. Миграция не меняет схему или данные; она сводит две уже
существующие ветки в один Alembic head. После этого повторный deploy завершился
успешно для обоих сервисов.

## Границы проверки

Браузерный пользовательский проход после deploy не выполнен: macOS была
заблокирована, а UI-автоматизация не смогла открыть экран. HTTP и Railway status
проверены напрямую. Это доказательство выкладки и работоспособности сервисов,
но не положительная бизнес-приёмка всех пользовательских сценариев.

Mobile не является Railway-сервисом. Финальный mobile commit
`45676eee0225d895a21d2d41030a652172411e6d` прошёл debug tests/lint/assemble в
реализационном цикле. Дополнительный `assembleRelease` 13.09.2026 завершился
успешно и создал unsigned APK; подписанный APK, установка на физический ТСД и
подключение приложения к staging этим отчётом не подтверждаются.
