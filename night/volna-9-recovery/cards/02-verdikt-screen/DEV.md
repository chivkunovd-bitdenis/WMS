# DEV · 02-verdikt-screen · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — записан итог повторной проверки атома после `REVIEW.md`.

Исходники атома повторно не менялись: требуемый вывод одного `StatusChip` и
`TextCell` уже находится в текущей ветке, а обе находки ревью исправлены до этого
прохода в коммитах `32c38f9e50ddf7703cc3b70fa619c30b4835bac6` и
`dade3f19431846e6717749969355c317f5527a60`. Первый сохраняет серверный
`metadata.verdict` в реальном API-ответе и сбрасывает устаревший зелёный вердикт
при пустом или ошибочном свежем ответе WB. Второй закрывает тот же fail-closed
путь (безопасный запрет при ошибке) для прямой передачи поставки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный на общем состоянии ветки:
  новые превышения базовой линии найдены в
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx`,
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`.
  Для целевого
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
  guard сообщает улучшение: `свой-чип 2 → 1`, `экран-монолит 1587 → 1572`.
  Базовая линия не обновлялась; чужие и соседние файлы в этом атоме не правились.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов.
- Узкие unit-тесты `fbsApi.test.ts` и `metaStatus.test.ts` — зелёные: 16 тестов.
- Backend-регрессии реального API и сброса устаревшего вердикта — зелёные:
  4 теста в `test_fbs_marking.py`, `test_fbs_shipment_deliver_gate_unit.py` и
  `test_fbs_worklist_query_count.py`.
- Playwright для S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006 — не
  запущен до сценария: webServer не смог занять `127.0.0.1:18000`, среда вернула
  `[Errno 1] operation not permitted`. Сам сценарий остался без изменений и
  проверяет открытие списка через UI, четыре видимых вердикта, русскую причину,
  отсутствие `uinBadStatus` и текст `Сдача пока недоступна`.
- `git diff --check 31cd2f5f..HEAD` — зелёный.
- Новый коммит этого отчёта создать не удалось: Git попытался создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`,
  но файловая песочница разрешает этому пути только чтение и вернула
  `Operation not permitted`. Артефакт существует в рабочем дереве, однако его
  ещё должен сохранить в Git оркестратор с доступом к общему git-dir.

## Не реализовано

- Буквально не выполнен только живой Playwright-прогон названных сценариев:
  локальный HTTP-порт запрещён средой до запуска браузерного шага. Пункты
  контракта в коде и тесте реализованы; технические поля WB на странице не
  выводятся.
- Отчёт `DEV.md` локально записан, но не закоммичен из-за read-only доступа к
  общему git-dir этой зарегистрированной рабочей копии.

## Находки

- Новых продуктовых находок в файлах атома нет.
