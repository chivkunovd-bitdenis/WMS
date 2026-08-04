# SUPERVISOR HANDOFF — FBS operator flow

> **Архивный снимок проверки на `0f75e21`.** Не используйте раздел «Граница
> релизной готовности» ниже как текущее состояние ветки. Актуальные SHA,
> PostgreSQL/Alembic proof и production preflight находятся в
> [`HANDOFF.md`](./HANDOFF.md).

**Ветка:** `feat/fbs-stock-sync`

**База проверки:** `0f75e21`
**Внешние действия на момент этого снимка:** push, merge, deploy и запросы к живому WB не выполнялись.

## Итог независимой добивки

Backend-контракт для нового FBS UI и сам frontend доведены до состояния, в котором можно
делать локальный коммит и передавать в PR. Проверка не ограничивалась старым handoff: заново
прогнаны реальные команды TypeScript, ESLint, Vitest, Vite и расширенный backend pytest.

Что исправлено после первоначальной реализации:

- `POST /operations/fbs-supplies/{id}/deliver` теперь возвращает канонический
  `FbsWorkspaceOut`, как требует frontend-контракт;
- ошибки cancellation, warehouse binding и stock sync возвращаются единым конвертом
  `{code, message, context, retryable}`;
- backend-тесты проверяют конверт целиком и повторную доставку после сбоя QR;
- устранён зависимый от порядка тестов жёсткий идентификатор `WB-GI-MOCK-1`;
- исправлены все 43 ошибки настоящего TypeScript-гейта `tsc -b` в новых FBS-файлах;
- дедлайн WB продолжает идти от серверного времени с учётом прошедшего клиентского времени;
- browser-моки переведены со старой ручки списка на канонический `/worklist`;
- добавлены 4 FBS unit-теста для API-клиента и арифметики дедлайна.

## Почему прежняя frontend-проверка вводила в заблуждение

Команда `tsc --noEmit` здесь ничего не проверяет: корневой `tsconfig.json` содержит `files: []`,
а project references раскрываются только в build mode. Правильный гейт — `tsc -b` или
`npm run build`.

Первоначально `node_modules` был неконсистентен: Vite и ESLint загружали частично записанные
модули. После чистого `npm ci` инструменты заработали и показали реальные ошибки. Затем Vite
зависал в подготовке старого `frontend/dist`, хотя сборка в `/private/tmp` успешно завершалась.
Старый маленький `dist` был сохранён в
`/private/tmp/wms-fbs-dist-before-standard-build-20260804-1350`, после чего штатный
`npm run build` также прошёл. `dist` — генерируемый и не входит в коммит.

## Проверенные гейты

```text
frontend: npm run build                                      PASS
          TypeScript + Vite, 11993 модуля, bundle создан
frontend: targeted ESLint                                   PASS
frontend: npm run test:unit                                 PASS
          13 файлов, 110 тестов
frontend: targeted FBS Vitest                               PASS
          2 файла, 4 теста
frontend: Playwright FBS contract browser                   PASS
          2 сценария, отдельный SQLite backend + Vite
backend:  ruff по изменённым API и тестам                    PASS
backend:  расширенный SQLite pytest                         PASS
          49 passed, 4 skipped, 0 failed
```

Backend pytest независимо повторён командой `python3 -m pytest`: 49/4 за 114,63 секунды.
Копия AnyIO внутри `backend/.venv` при импорте зависает на файловом чтении, поэтому два запуска
через `./.venv/bin/pytest` были остановлены до collection. Системный Python 3.14.3 с теми же
тестами работает нормально; это локальный дефект виртуального окружения, а не тестовый failure.

Четыре backend skip относятся к PostgreSQL-специфичным проверкам: блокировкам строк,
частичным уникальным индексам и Alembic round-trip. Предупреждения SQLite возникают при
удалении циклических внешних ключей в cleanup и не являются падениями тестов.

## Что доказано не полностью

- Playwright поднимает настоящий auth/backend на SQLite, но FBS worklist подменён contract mock;
  это не полный проход FBS API против PostgreSQL.
- PostgreSQL, Celery и полный compose-контур не запускались вместе.
- TC-24 с живым Wildberries не запускался: нужны секреты и отдельная явная команда.
- Аудит подтверждения размеров ПВЗ хранится в journal операции, а не в колонках `trbx`;
  изменение схемы требует отдельной миграции.
- Deprecated `create` / `add-order` и другие legacy-ручки намеренно не унифицированы: новый UI
  ими не пользуется.

## Граница релизной готовности

Этот раздел описывает состояние на базе `0f75e21` и сохранён только как история проверки.
Текущий release-state не следует выводить из него; используйте `HANDOFF.md`.
