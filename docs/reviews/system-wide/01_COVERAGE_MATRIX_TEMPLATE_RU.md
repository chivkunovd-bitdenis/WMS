# Матрица охвата полного ревью WMS

Матрица является главным счётчиком полноты. До запуска ревью оркестратор заменяет примеры реальным инвентарём маршрутов, компонентов и процессов. Строки не удаляются из-за отсутствия реализации: они получают `GAP`, `NOT_RUN` или `N/A` с объяснением.

## Паспорт прогона

- Review ID:
- Git branch / SHA:
- Frontend SHA стенда:
- API SHA стенда:
- Worker SHA стенда:
- Mobile repo branch / SHA / included or excluded:
- Schema version:
- Environment / URL:
- WB mode: emulator / test / live / not used
- Test tenant and seller IDs:
- Start / finish time (МСК):
- Reviewer:

## Статусы

- `PASS` — ожидаемое поведение и результат доказаны.
- `FAIL` — создана находка с полным пакетом доказательств.
- `GAP` — обязательного шага или пути завершения нет.
- `BLOCKED_BY_DECISION` — источники правды противоречат друг другу.
- `NOT_RUN` — не проверено; причина и риск обязательны.
- `N/A` — неприменимо; объяснение обязательно.

## Инвентарь системы

| Area ID | Область | Роль | UI route/screen | API / worker / integration | Data owner | Source of truth | Owner-agent |
|---|---|---|---|---|---|---|---|
| INV-001 | Пример: FBS — новые заказы | комплектовщик ФФ | `/app/ff/fbs` | API + WB sync worker | tenant + seller | FBS handoff | product |

## Охват исходного кода

Tracked source-файлы группируются по модулю. Generated/vendor/evidence-артефакты не требуют построчного ревью, но их исключение записывается. Для каждой группы должен быть статус `REVIEWED`, `EXCLUDED` или `BLOCKED`.

| Code area | Included paths | Excluded paths and reason | Primary reviewer | Security/invariant focus | Status | Evidence/report section |
|---|---|---|---|---|---|---|
| Пример: FBS API/service | paths | generated fixtures | teamlead | authz, retry, atomicity | NOT_RUN | |

## Реестр конфликтов источников

| Conflict ID | Scope | Source A + exact section | Source B + exact section | Actual behavior | Owner decision/date | Matrix status |
|---|---|---|---|---|---|---|
| CONFLICT-001 | example | path | path | unknown | pending | BLOCKED_BY_DECISION |

## Матрица сценариев

| Scenario ID | Область и цель пользователя | Роль | Предусловия и физический контекст | Вариант | Ожидаемый видимый результат | Ожидаемый результат данных/WB | UI evidence | State evidence | Status | Finding / reason |
|---|---|---|---|---|---|---|---|---|---|---|
| REV-001-HAPPY | Пример: завершить действие | оператор | Тестовые данные описаны | happy | Следующий шаг понятен | Состояние записано один раз | path | path | NOT_RUN | |
| REV-001-EMPTY | То же | оператор | Нет данных | empty/first use | Есть понятное первое действие | Нет ложной записи | path | path | NOT_RUN | |
| REV-001-INVALID | То же | оператор | Неверный ввод | validation/forbidden | Ошибка рядом с причиной, данные сохранены | Запись не изменилась | path | path | NOT_RUN | |
| REV-001-RETRY | То же | оператор | Потерян ответ | double click/retry/reload | Нет двойного успеха | Один durable result / тот же external ID | path | path | NOT_RUN | |
| REV-001-PARTIAL | То же | оператор | Часть операции успешна | partial | Ясно, что сделано и как продолжить | Нет скрытой полузаписи | path | path | NOT_RUN | |
| REV-001-RACE | То же | два оператора | Одна версия остатка | concurrency | Один получает понятный итог | Нет отрицательного остатка / lost update | path | path | NOT_RUN | |
| REV-001-OUTAGE | То же | оператор | API/WB/worker недоступен | failure/recovery | Прогресс не потерян | После восстановления безопасное продолжение | path | path | NOT_RUN | |
| REV-001-ISOLATION | То же | чужой seller/tenant | Известен чужой ID | authorization | Данные и действие недоступны | 403/404 без утечки | path | path | NOT_RUN | |

## Обязательные области для сверки с фактическим инвентарём

- публичный вход, регистрация, восстановление и первый вход селлера;
- роли, tenant/seller isolation, сессии и аудит действий;
- склады, ячейки, каталог, остатки, резервы и движения;
- приёмка, расхождения, сортировка и перемещения;
- упаковка, Честный знак, этикетки, накладные и физическая печать;
- внутренний outbound и отгрузка на маркетплейс;
- FBS: импорт, совместимость, поставка, подбор, упаковка, короба, QR, передача, статусы, отмены и возвраты;
- FBW read-only и границы исходящих действий;
- синхронизация остатков и read-back после публикации;
- фоновые задачи, ретраи, расписания, дедупликация и восстановление;
- биллинг, календарная граница МСК и объяснимость начислений;
- настройки, feature flags, миграции и совместимость версий.

## Итог полноты

- Inventory rows total / covered:
- Scenario rows total / PASS / FAIL / GAP / BLOCKED / NOT_RUN:
- UI routes total / screens evidenced:
- Tracked code areas total / reviewed / excluded / blocked:
- Contract conflicts total / resolved / blocking:
- P0/P1 second reproductions complete:
- Emulator rows / test rows / live rows:
- Unreviewed risk:
