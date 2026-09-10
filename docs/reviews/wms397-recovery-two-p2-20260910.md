# WMS-397 / WMS-399 — исправление двух P2 независимого ревью

Это отчёт исполнителя для повторного независимого review, не приёмка и не новый
бэклог. Первым прочитан полный SAFE
`wms415-coord/docs/reviews/artifacts/wms415-astra-takeover-20260910/resumed/review-chat-recovery-final-result.md`.
Проверенный чистый старт: `655b566d5b314e1d4bee52f2f84e27e6a3336fa2`,
ветка `feat/wms397-chat-mvp`, существующий worktree `wms397-chat-mvp`.
Канон/handoff и чужие файлы не редактировались; агентов, deploy, новых страниц,
сущностей, счётчиков и автоматического удаления нет.

## P2: выбран UUID без строки заказа — исправлен для повторного review

Exact-order load теперь при каждом успешном актуальном ответе обновляет
selectedCache той же серверной строкой, что попадает в orders. Общий чекбокс
получает реальный selectedOrders и разрешает действия по существующему условию.
Статус/marketplace/seller не подменяются; устаревшие success/error ответы не
меняют текущую строку/выбор, актуальный отказ очищает строки, выбор и кэш.

В coordinator уже есть дополнительный эффект очистки выбора при смене контекста.
Просто добавить заполнение кэша недостаточно: серверные фильтры exact-order
запускают этот эффект и снова очищают кэш. **Обновлённый интеграционный патч
обязательно сохраняет кэш при linkedOrderId, оставляя сброс самого выбора.**
Для обычного списка прежняя очистка кэша сохранена. Эта узкая адаптация находится
в patch, поскольку самого coordinator-эффекта ещё нет в worker source.
Нельзя ограничиться слепым cherry-pick worker FBS-строки и пропустить адаптацию.

`FfFbsOrdersScreen.chatLink.test.ts` извлекает AST и исполняет именно исходные
load, toggleVisibleSelectable, selectedOrders и условие disabled кнопки; callback
эффекта контекста также исполняется, когда он присутствует в проверяемом файле.
Это тест функций с подставленным API, **не браузерный тест**. До исправления
на source 655b566d три проверки падали: выбран один UUID, selectedOrders пуст.
После исправления четыре проверки проходят на worker source и на результате
трёхсторонней интеграции. Отдельное удаление защиты кэша из интеграционного
результата снова воспроизвело падение select-all после эффекта контекста.
Проверены первоначальная загрузка/общий чекбокс/доступность действий, обновление
строки при poll, смена статуса, устаревшие success/error и актуальный forbidden.

## P2: восстановление SQL draft без физического файла — исправлен для review

Перед связыванием вложений, под существующими attachment row locks, сервис
проверяет наличие объектов. Все проверки проходят до установки message_id.
LocalObjectStorage использует stat, S3ObjectStorage — HEAD с существующим
prefix/bucket. Содержимое файлов не скачивается. Missing даёт 422
`attachment_content_missing`; composer предлагает убрать вложение из сообщения,
удалить оставшийся draft и загрузить файл заново, сохраняя текст.

403, throttling, I/O и ошибки инициализации адаптера не считаются отсутствием:
503 `attachment_storage_unavailable` сохраняет точный pending send для повторения.
Успешный идемпотентный повтор уже сохранённого сообщения не выполняет HEAD снова.
Commit discard теперь внутри обработки ошибки с rollback/503. Повторное удаление
действительно отсутствующего объекта допускается; локальный unlink(missing_ok)
не скрывает permission/I/O errors, S3 delete игнорирует только missing codes.
Глобальный бюджет, User lock, upload flush-before-storage и send/delete row-lock
порядок не изменены. ACL проверяется до проверки содержимого.

До исправления воспроизведено на реальной изолированной SQLite и локальном
object storage: настоящий SQL DELETE/flush, настоящее удаление объекта,
инъекция ошибки на AsyncSession.commit с rollback. SQL draft снова виден,
а отправка возвращала 201 с отсутствующим объектом. Это инъекция ошибки на
границе commit, не авария настоящего PostgreSQL-сервера. После исправления
тот же сценарий на SQLite и PostgreSQL возвращает 422, не оставляет сообщения
или привязки; повторный discard освобождает row, reupload и идемпотентный send
успешны. Отдельно проверен сбой HEAD второго файла после проверки первого:
ни один не связан, пустого сообщения нет, повтор после восстановления успешен.

## Проверки и интеграция

- PostgreSQL: только `tests/test_chat_api.py tests/test_chat_storage_availability.py` — **34 passed**, 40.72 s; включая прежние ACL/budget/concurrency тесты и новые storage-проверки.
- SQLite: только recovery/discard/commit/head selection — **3 passed, 31 deselected**, 7.62 s. S3 adapter проверен stub-клиентом без сети: successful HEAD, 404/NoSuchKey/NotFound, 403/SlowDown/500, отсутствие GET содержимого, идемпотентный missing delete. Локально проверены stat без чтения байтов, повторный delete и propagation PermissionError.
- После последней обработки ошибки инициализации адаптера повторены PostgreSQL commit-failure / transient-head / delete-versus-attach; **3 passed, 23 deselected**, 6.10 s; mypy повторно PASS.
- Vitest: **4 passed** на worker и **4 passed** на подготовленном coordinator source. `WMS_FBS_SOURCE` позволяет запустить тот же тест на конкретном интегрированном файле, не редактируя его.
- Ruff затронутых Python files, mypy трёх services/API, ESLint ChatComposer и нового source-callback теста, TypeScript app — PASS. FBS production delta — одна строка заполнения кэша; прежние lint замечания из предыдущего отчёта не объявляются исправленными.
- `RAYON_NUM_THREADS=2 npm run build` — PASS, Vite 2.14 s; прежний chunk warning сохраняется. Полного pytest/xdist нет, не более двух test processes.
- `git diff --check` — PASS. Обновлённый `artifacts/wms397-working-links-coordinator-20260910.patch` подготовлен против coordinator **29a9972a5d5070bfd8e29a67f3cbcb5dd7e15193**, `git apply --check` без применения — PASS. Сохранены 719/857/e3aac, open_inbound, supply_id, onDirtyChange и stale-response guards. Patch содержит совокупную frontend delta от ещё не интегрированного 655b566d вместе с исправлением P2; не применять повторно поверх уже перенесённых строк.

Ручной браузер в этом продолжении не использовался: предыдущая автоматическая
проверка доступа отклонила 127.0.0.1:5397, владелец запретил обход. Другой браузер,
порт или CLI automation для обхода не использовались. Нужны независимое review
итогового SHA и разрешённые клики после интеграции: exact-order общий чекбокс,
действия/«Показать выбранные», фильтры/poll/Back, recovery missing/transient error.
Реальный удалённый S3, staging/production и клиентские данные не использовались.

SQL/storage по-прежнему не одна транзакция: после discard commit failure может
остаться missing draft, но теперь он не принимается к отправке и доступен для
явного повторного discard/reupload. Внешняя потеря объекта уже отправленного
сообщения и объекты без SQL row после аварийного upload не исправляются этим
срезом. Прежние ограничения seller-маршрутов и revoked-chat drafts сохранены.

Точные файлы: `backend/app/api/chat_routes.py`,
`backend/app/services/chat_service.py`, `backend/app/services/object_storage_service.py`,
`backend/tests/test_chat_api.py`, `backend/tests/test_chat_storage_availability.py`,
`frontend/src/components/chat/ChatComposer.tsx`,
`frontend/src/screens/v2/FfFbsOrdersScreen.tsx`,
`frontend/src/screens/v2/FfFbsOrdersScreen.chatLink.test.ts`, обновлённый patch
и этот отчёт. Shared storage adapter изменён только для необходимой metadata
проверки и корректного missing/transient delete; новые API credentials не нужны.

Координатор обновляет канон/handoff после собственного review. Оба P2 переданы
как исправленные с воспроизведением до/после, а не как принятые или deployed.
