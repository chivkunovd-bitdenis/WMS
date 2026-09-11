# WMS-397/399: отдельный чат поверх вечернего кандидата

База `03592c5be27ee40a8bbea9135c612dc0471e2be7`, ветка `codex/wms-chat-evening-20260910`, `.worktrees/wms-chat-evening-20260910`. Принятая интеграция чата перенесена из `f4189fa1` только разницей к ранее изолированному non-chat4221969c. Поверх неё — `ChatScreen.tsx`, `documentTarget.ts` и его тест из Opus5 `d00caa47`. Старые ветки целиком не сливались.

Основная вечерняя ветка и API/stock/warehouse/document/auth правки не изменены. В общих frontend-файлах переносились уже принятые chat imports/buttons/routes/selectedCache handling; navigation и dirty guards сохранены из той же принятой интеграции. FfInboundQueuePage не перенесён: приёмку открывает существующий App handler `open_inbound`. Авторский handoff сохранён в wms397-final-chat-delta-20260910.md.

Миграция0300 добавлена с исходным parent0257. Единственная новая пустая merge0303: parents0302/0300. Старой0301 нет. `alembic heads` выдаёт одну0303.

Один технический набор: Ruff изменённого backend PASS; `tsc --noEmit -p tsconfig.app.json` PASS; `npm run build` PASS. Авторские34PG/4callback/83mobile и полный pytest не повторялись. Новых независимых reviewers, автоматических браузерных тестов, функций и редизайна не запускалось. Ручные сценарии выполняет root; этот протокол не объявляет их пройденными.

## Полный локальный стенд для root

HTTP200 подтверждены: `http://127.0.0.1:5397/app/ff/chat` и API `http://127.0.0.1:8397/health`. Это обычный Vite App и настоящее приложение backend из интегрированной копии. Использован существующий `backend/scripts/wms397_chat_fixture.py`; единственная fixture-адаптация — отдельное имя локальной БД `wms397_chat_evening_ui_20260910`. Старая учебная БД не имела warehouse empty_places, поэтому её не меняли и не выдавали за совместимую.

Три synthetic роли (FF admin, seller, staff) и существующий fixture default вход остаются в скрипте. Реальных marketplace keys, писем, складских движений и пользователей нет. Raw private logs игнорируются Git. API50954, frontend50955 оставлены root для ручной приёмки; launcher metadata и безопасные document IDs находятся в artifacts/wms397-evening-20260910.

Доступны по одному учебному документу: IN-CHAT397 (приёмка), MP-CHAT397 (отгрузка на маркетплейс), отгрузка со склада, WB order3970001 и «Учебная FBS-поставка397». ID сохранены в fixture-documents.json; открыть можно через обычные экраны/ссылки документа.

Stage, production и publicAPK не изменялись. Основной выпуск не ждёт этот чат. Статус — отдельный сохранённый кандидат с локальным стендом для приёмки, не deployed.


## Синхронизация 11.09 перед отдельным будущим выпуском

Коммит2a7a354d04bf685f77af3b41fab5ff9d58efc279 объединяет прежний chat-кандидат
8cd7ca1f с основным release fb274e0da3429e679d9d71f93d588423ac20c7b9.
Root прочитал разрешения конфликтов App.tsx и FfFbsOrdersScreen.tsx: маршруты
и действия чата сохранены рядом с актуальным хранением и позициями Ozon.
После merge root выполнил одну проверку TypeScript и одну сборку frontend:
обе прошли. Новый браузерный проход на этой основе не выполнялся — Mac
заблокирован. Чат не включён в production release, его выкладка не разрешена.
