# WMS-440–WMS-445: выкладка и остановка на ночь

14.09.2026, 00:17–00:20 МСК. Владелец явно разрешил CI → staging → production и поручил после production остановить активности до утра. Последний порог остановки: остаток лимита менее 47%.

## Проверенный результат

- CI [34782392807](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/34782392807) на `7300ec54f6de71c753f0997bcbd0b728e9a5c470`: SUCCESS; backend 2581 passed, 144 skipped, 1 xfailed; Ruff, Mypy, frontend typecheck/build и backlog gate прошли.
- Адресная приёмка исправления истории сотрудников: `ef0915f258eb3bf22f47484fd1bd2f6e7c6e2d8c`. Изменения относительно CI SHA — только доказательства/документы. Native A1/B2 → существующая web-история с обоими ФИО; replay A под B не меняет автора, не дублирует событие или начисление. См. `artifacts/tsd-native-443-journal-fix-20260913/README.md`.
- Staging SHA `d63794926a9739d364042a1fc78236d209fac378`: существующие параллельные изменения staging сохранены обычным merge, без force push. Railway WMS deployment `dfe082f6-707b-4ce2-bd00-be16f51db1ae` и web deployment `da5a3700-3dee-4dd1-b33b-4784c369c123`: SUCCESS с точным SHA. Штатный staging smoke: `/` и `/api/health` HTTP 200, SPA shell OK.
- Production: пакет `ef0915f258eb3bf22f47484fd1bd2f6e7c6e2d8c` опубликован fast-forward в `origin/etalon`; отдельные staging-only изменения в production не переносились. [Deploy Production 34783173106](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/34783173106): SUCCESS. Серверный guard подтвердил target/trunk `ef0915f258eb`; резервная копия проверена, миграции и запуск завершены. `/`, `/seller/`, `/api/health` дали HTTP 200; отдельное чтение production health вернуло `{"status":"ok"}`.

## Остановка

Исполнители завершены. Heartbeat `wms-2` переведён в PAUSED. Принадлежащие пакету локальные API 18082/18084, web 5197/5204 и emulator-5580 остановлены. Чужие worktree/процессы и удалённые сервисы приложения не останавливались. Автоматического утреннего возобновления не назначено.

## Граница результата

Это подтверждение выкладки, не полная приёмка всех шести задач. Не закрыты физическая печать/проверки Windows/macOS, реальный кабинет «Виталик Хорс» и оставшиеся составные сценарии чек-листов (включая WMS-444 C18). Их вердикты не заменялись зелёным CI или успешным деплоем. Дальнейшая работа остановлена по прямому указанию владельца.
