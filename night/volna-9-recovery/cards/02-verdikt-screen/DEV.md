# Фича 1

# Backend-dev · 02-verdikt-screen

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/wildberries_fbs_client.py — сохранение `reason` из ответа WB в типизированной детали метаданных.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py — безопасная агрегация вердикта для пустых, обязательных и необязательных требований; причина прокидывается в операторский вердикт.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py — регрессии на парсинг причины, пустые требования и отсутствующее optional-значение.

## Гейты

- ruff: FAIL — существующие несвязанные нарушения в репозитории (81 ошибка, включая старые `noqa`, импорты и длину строк).
- mypy: FAIL — существующие несвязанные ошибки в шести файлах, 21 ошибка.
- pytest: PARTIAL — полный набор остановлен после длительного выполнения; целевой `tests/test_fbs_marking.py`: 24 passed.
- back_guard.py: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует в рабочей копии.

## Не реализовано

- UI-находки ревьюера не реализовывались: это backend-dev атом, их исправление относится к screen-dev.
- Миграции не требуются.

# Фича 2

# Backend-dev отчёт · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

Серверный delivery-check теперь всегда читает единый `_wb_order_verdict` для каждого заказа поставки, включая заказы без WB-метаданных. Проходные `filled`, `optional`, `notRequired` без причины проходят; отказ с причиной, `pending`, `required` и неизвестный ответ блокируют передачу. Блокирующая проверка содержит UUID конкретного заказа и причину.

## Миграции

Нет.

## Тесты

Добавлен unit-тест прохода заказа без требований WB; существующий набор проверяет проходные и блокирующие решения, привязку отказа к заказу и сообщение причины. Точечный запуск: 17 passed.

## Гейты

- `ruff check .` — FAIL: 81 существующая ошибка в несвязанных файлах; изменённые файлы в выводе не фигурируют.
- `mypy .` — FAIL: существующие ошибки типизации в несвязанных файлах; изменённые файлы в выводе не фигурируют.
- `pytest -q tests/test_fbs_shipment_deliver_gate_unit.py` — PASS, 17 passed.
- `pytest -q` — выполнялся; обнаружен отдельный сбой полного набора, итоговый процесс ещё не дал финального отчёта на момент сдачи артефакта.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файла нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файла нет в этой рабочей копии.

## Не реализовано

- Frontend-находки из REVIEW.md не входят в атом `backend-dev` и не изменялись.
- Исправление парсинга WB `reason` и прочие изменения `fbs_marking_service.py` не входят в заданные файлы этого атома; текущий backend-вердикт использует сохранённую причину, если она присутствует.

## Блокеры

Нет продуктовых блокеров. Технические ограничения гейтов описаны выше.

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

В клиентский контракт добавлен безопасный серверный вердикт по умолчанию: если
живой ответ ещё не содержит `metadata.verdict`, заказ получает блокирующее
состояние `Нет ответа WB`, а не оптимистичное разрешение из локальных полей.
Ответы worklist и workspace нормализуются перед передачей в экран. Словарь
отображения сохраняет фиксированные подписи и тоны, переводит известные причины
на русский и безопасно показывает неизвестную причину как пришедший текст.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда запущена, но окружение не
  вернуло диагностический вывод или код завершения через оболочку инструмента;
  результат не удалось подтвердить как зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в
  несвязанных файлах: `src/components/WbProductPickerDialog.tsx`,
  `src/screens/v2/FfFbsSupplyWorkspace.tsx`,
  `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не изменял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Находки ревью, относящиеся к backend и экранным компонентам
  `FfFbsOrdersScreen.tsx`/`FfFbsSupplyWorkspace.tsx`, не исправлялись: они не
  входят в разрешённый атом фичи 3 и требуют отдельных карточек.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`

В существующей зоне «Статус» вердикт WB теперь отображается для строк всех
вкладок, а не только «Просроченных». Локальный статус заказа больше не может
заменить блокирующий вердикт WB; причина отказа и текст «Сдача пока недоступна»
остаются в `TextCell`, без новой колонки и без заливки строки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, диагностик нет.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх нарушений в несвязанных
  файлах: `src/components/WbProductPickerDialog.tsx`,
  `src/screens/v2/FfFbsSupplyWorkspace.tsx`,
  `src/screens/v2/SellerInboundDraftScreen.tsx`. Новых нарушений в изменённом
  `FfFbsOrdersScreen.tsx` не добавлено; его показатели улучшились.
- `npm run test:unit` — красный: в окружении отсутствует команда `vitest`.
- Playwright для названных сценариев не запускался: локальная зависимость
  Playwright в этом окружении недоступна.

## Не реализовано

- Находки 1–5 из `REVIEW.md` относятся к backend или
  `FfFbsSupplyWorkspace.tsx`, которые не входят в разрешённые файлы этого
  атома; их исправление оставлено соответствующим карточкам.
- Полное исправление находки 6 для строк поставок невозможно в рамках
  разрешённых файлов: worklist поставок не содержит заказных WB-вердиктов, а
  изменение API-типа или `FfFbsSupplyWorkspace.tsx` выходит за границы атома.

# Фича 5

# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальные `node_modules` отсутствуют, `npx` попытался скачать `tsc`, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный: в рабочей копии остаются новые нарушения baseline в `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx`; для `FfFbsSupplyWorkspace.tsx` после сокращения файла нового нарушения нет.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` — красный: `vitest: command not found`, зависимости не установлены.

## Не реализовано

- Находки REVIEW.md по backend-файлам и `FfFbsOrdersScreen.tsx` не изменялись: они вне разрешённых файлов текущего экранного атома.
- Playwright-сценарии S-03-TC-004, S-03-TC-005 и S-03-TC-007 не запускались из-за отсутствующих frontend-зависимостей.
