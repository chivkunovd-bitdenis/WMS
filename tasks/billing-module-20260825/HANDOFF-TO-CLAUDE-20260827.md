# Полный handoff для Claude: модуль «Расчёты»

Дата фиксации: 27.08.2026, Europe/Moscow.

Этот документ описывает фактическое состояние ветки после неудачно затянутой
мультиагентной разработки. Он намеренно разделяет принятый результат,
незавершённый код и неподтверждённые заявления агентов.

## 1. Требование владельца

Нужно закончить полный модуль «Расчёты» по принятому продуктовому контракту:

- Wave 2A — надёжные факты операций;
- Wave 2B — тарифная матрица;
- Wave 3 — отчёт по селлерам;
- Wave 4 — счета;
- Wave 5 — сотрудники.

Главный продуктовый источник:

- `tasks/billing-module-20260825/TASK.FINAL.md`.

Отдельные исполняемые контракты:

- `tasks/billing-02a-operation-facts/TASK.md`;
- `tasks/billing-02b-tariff-matrix/TASK.md`;
- `tasks/billing-03-seller-report/TASK.md`;
- `tasks/billing-04-invoices/TASK.md`;
- `tasks/billing-05-employees/TASK.md` — **не принят, есть грязная незакоммиченная правка**.

Критическое требование владельца к фронту:

- только существующий `frontend/src/ui-kit/` и стиль WMS;
- не переделывать старые экраны;
- не допускать сжатых, налезающих или уехавших колонок;
- фильтры, dropdown, кнопки, chips, таблицы и модалки должны быть каноническими;
- автоматические тесты не заменяют живую проверку экрана.

## 2. Где работать и что опубликовано

Постоянный checkout:

```text
/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826
```

Это разрешённый `git worktree` внутри канонического проекта. Его общий Git dir:

```text
/Users/deniscivkunov/Projects/WMS/.git
```

Ветка:

```text
codex/billing-module-20260826
```

Последний product-code tip до добавления этого handoff:

```text
1078fae7eb24cacd6ff41b846afe0192f0dafc39
```

На момент фиксации `HEAD` и `origin/codex/billing-module-20260826` совпадали.
Ничего не влито в `main`, staging или production. Не заявлять deploy/готовность.

Не переходить в корневой checkout `/Users/deniscivkunov/Projects/WMS`: там была
другая пользовательская ветка `codex/fix-inbound-empty-product-picker`. Не
переключать её и не переносить туда изменения без отдельного осознанного шага.

## 3. Честная готовность по волнам

### Wave 2A — принята в ветке

Основные commits:

- `b35302b1` — OperationFact и источники;
- `0f0fc491` — recovery hardening;
- `89fec60d` — финальная SQLite actor regression;
- `60f82566` — correction proof.

Состояние: код, тесты и proof есть; волна считается принятой внутри feature-ветки.

### Wave 2B — принята в ветке

Основной итоговый commit:

- `797bf2e3` — тарифная матрица.

Перед ним добавлен и принят общий UI-kit для форм. Есть browser evidence для
матрицы. Известное старое поведение на 375 px было наследованным ограничением
экрана Settings, а не разрешением ломать новые экраны.

### Wave 3 — принята в живом браузере

Основные commits:

- `a50ecaa4` — отчёт по селлерам;
- `368ceb88` — очистка stale-детализации при смене фильтров;
- `4e4b9f9a` — независимый live-browser verdict и скриншоты.

Verdict:

```text
PRODUCT_BROWSER_APPROVED
```

Доказательства:

- `docs/evidence/20260827-volna-3-otchet-po-selleram/VERDICT.md`;
- `docs/evidence/20260827-volna-3-otchet-po-selleram/BILLING-SELLERS-1600.jpg`;
- `docs/evidence/20260827-volna-3-otchet-po-selleram/BILLING-SELLERS-FINANCE-OFF-1600.jpg`.

Что реально проверено в browser 1600x1000:

- page `scrollWidth === clientWidth === 1600`;
- фильтры, быстрые периоды и таблица не разъезжаются;
- finance off полностью убирает денежные поля;
- finance on показывает `630,00 ₽`;
- детали: одна строка хранения, 50 операций, load more до 53 без второй строки хранения;
- empty/error/detail-error;
- старая вкладка «Счета» не переделана;
- после `Луна -> детали -> Пустой селлер` старые детали теперь исчезают.

Перед принятием Wave 3 полный backend дал:

```text
1175 passed, 10 skipped, 9 warnings in 18:14
```

Полный frontend перед принятием Wave 3:

- unit: `212 passed`;
- TypeScript: exit 0;
- production build: exit 0;
- Playwright: `214 passed, 7 skipped`.

Эти результаты относятся к Wave 3 tip, а **не** к более поздним Wave 4 commits.

### Wave 4 — частично реализована, не принята

Контракт Wave 4 принят независимым review после нескольких исправлений:

- `c35ef1f0` — окончательная правка narяд scope без ложного `S-19`.

Важно: `S-19` в реестре — Settings, а не Billing. Для Wave 4 используется
точный `--files` без `--screens S-19`.

Опубликованные backend commits:

- `036cd79e` — additive migration 0114, V2 invoice/line/source/idempotency models,
  tenant composite identity, старый daily invoice task превращён в safe no-op,
  beat entry удалён;
- `a214c435` — manual V2 preview/save/detail/cancel, decimal-string -> kopecks,
  idempotency;
- `84b83a27` — signed totals разрешены для reversal chains, manual input остаётся
  nonnegative;
- `b63f590e` — выбор root charge и всей цепочки reversal descendants, signed net,
  source snapshots, standalone reversal отклоняется;
- `6081aeb7` — неудачный commit: случайно переформатировал большой seller-report service;
- `1078fae7` — восстановил узкий diff после `6081aeb7`, оставил только verifier storage token.

Текущие targeted результаты, сообщённые агентом:

- billing task tests: `2 passed`;
- manual API/task slice: `4 passed`;
- reversal-chain API slice: `3 passed`;
- storage-related targeted slice: `8 passed`;
- changed-path ruff/mypy/diff-check: green.

После Wave 4 commits **не было** полного backend pytest, полного frontend suite,
независимого backend review или живого browser verdict.

#### Критический незавершённый дефект Wave 4

Агент заявил, что storage-token проверяется до сохранения счёта, но текущий код
этого не делает полностью:

- `verify_storage_calculation_token()` существует в
  `backend/app/services/billing_seller_report_service.py`;
- `billing_invoice_v2_service.py` его не вызывает;
- `storage_calculation_token` из request не участвует в preview/save;
- `BillingInvoiceV2Source.storage_calculation_token` сейчас сохраняется как `None`;
- строка хранения не добавляется в invoice preview/persist.

То есть commit `1078fae7` добавил verifier-примитив, а не законченный storage invoice
flow. Это первый обязательный backend fix.

#### Что ещё отсутствует в Wave 4 backend

- полноценная строка хранения в preview/save с серверным пересчётом и блокировкой
  `missing_dimensions`;
- compatibility facade: единый legacy+v2 список в старом envelope
  `{"invoices": ..., "issues": ...}`;
- устойчивый глобальный signed cursor и сортировка legacy+v2;
- точная period-filter semantics для manual V2;
- полная invoice history/reissue visibility;
- окончательная OpenAPI/tenant/RBAC/concurrency проверка всего контура;
- возможные print/open snapshot поля должны быть сверены с контрактом;
- независимое содержательное backend review.

#### Wave 4 UI-kit prerequisite — candidate отклонён review

Candidate commit:

- `9f803ea0` — `CheckboxInput`, string `MoneyInput`, `AppDialog`.

Автоматические проверки candidate:

- targeted ui-kit: `27 passed`;
- TypeScript, build, `ui_guard`, diff-check: green.

Но независимый verdict:

```text
UIKIT_REWORK_REQUIRED
```

Причины:

1. `AppDialog.test.tsx` проверяет внутреннюю константу, а не DOM-поведение. Нет
   доказательства title association, initial focus, focus trap, Escape -> onClose
   и восстановления фокуса.
2. Money/Checkbox tests основаны на SSR markup/private validator. Нет реальных
   interaction tests, что `MoneyInput` возвращает точные строки `12.20` и `0.29`
   без numeric coercion, показывает/блокирует invalid input; checkbox должен
   реально переключаться, а disabled checkbox — не переключаться и иметь
   accessible disabled reason.

Текущий активный narяд:

```text
20260827-volna-4-raschety-obschie-ui-kit-checkbox
```

Его граница видна через:

```bash
python3 scripts/naryad.py show
```

Сначала исправить только эти tests/при необходимости primitives в текущей
границе, получить независимый `UIKIT_ACCEPTED`, commit/push и закрыть narяд.
Экран Wave 4 до этого не начинать.

#### Wave 4 frontend не реализован

На `FfBillingScreen` нет законченного нового сценария:

- выбор операций checkbox-ами;
- disabled reasons для unpriced/not-billable;
- manual invoice form до 10 строк;
- preview/back/save/print;
- повторное выставление;
- новая совместимая история V2/legacy;
- live evidence 1600/1280/print.

Не использовать собственные MUI Checkbox/Dialog/TextField мимо принятого UI-kit.
Не переделывать старую вкладку счетов до появления нового контрактного поведения.

### Wave 5 — не начата, контракт не принят

Product code Wave 5 отсутствует.

Committed contract tip:

- `c046ae46`.

После независимого review начата, но прервана незакоммиченная правка
`tasks/billing-05-employees/TASK.md`. Она добавляет в boundary PackagingTask/User
и completion writer, чтобы закрыть два P0:

1. PostgreSQL composite FK к `(tenant_id, id)` невозможен без соответствующего
   unique constraint у `PackagingTask`.
2. Текущий packaging completion не сохраняет `billing_rate_configured` и имя
   сотрудника; после удаления User история имени теряется.

Эту грязную правку нельзя молча потерять или автоматически включить в чужой
commit. Её нужно закончить, перепроверить против `TASK.FINAL.md`, независимо
принять как `CONTRACT_ACCEPTED`, затем отдельным commit/push сохранить. Только
после этого начинать Wave 5 code.

## 4. Текущее грязное дерево

Осознанная tracked dirty-правка:

```text
M tasks/billing-05-employees/TASK.md
```

Она принадлежит незавершённому contract rework Wave 5. Сохранить и довести либо
явно отложить отдельным commit; не откатывать.

Есть многочисленные untracked `baseline-dirty.txt` и один старый task package.
Они создавались narяд-инструментом/предыдущими prerequisite и не должны попадать
в product commits автоматически:

```text
tasks/20260827-vladelec-27-08-2026-dodelat-zadachu-v-mu/baseline-dirty.txt
tasks/20260827-vladelec-27-08-2026-ispravit-obschiy-ui-/baseline-dirty.txt
tasks/20260827-volna-2b-modulya-raschety-tarifnaya-matr/baseline-dirty.txt
tasks/20260827-volna-3-modulya-raschety-otchet-po-selle/baseline-dirty.txt
tasks/20260827-volna-3-raschety-generic-ui-kit-money-me/
tasks/20260827-volna-3-raschety-obschaya-ui-kit-prerequ/baseline-dirty.txt
tasks/20260827-volna-3-raschety-vosstanovit-otdelnyy-zh/baseline-dirty.txt
tasks/20260827-volna-4-modulya-raschety-scheta-na-susch/baseline-dirty.txt
tasks/20260827-volna-4-raschety-obschie-ui-kit-checkbox/baseline-dirty.txt
```

Нельзя делать `git add -A`.

## 5. Рекомендуемая последовательность без повторения хаоса

### Шаг 1. Зафиксировать checkout

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826
git status --short --branch
git rev-parse HEAD
git rev-parse origin/codex/billing-module-20260826
python3 scripts/naryad.py show
```

Не переключать ветку и не трогать root checkout.

### Шаг 2. Закрыть UI-kit prerequisite

Исправить только interaction tests из verdict. Не расширять primitives без
необходимости. Запустить targeted ui-kit unit, TypeScript, build, `ui_guard`,
diff-check. Затем независимый static review. Только `UIKIT_ACCEPTED` разрешает
закрыть prerequisite narяд и начать Wave 4 screen.

### Шаг 3. Закончить Wave 4 backend

Сначала подключить storage token verifier к preview/save и доказать stale/tamper,
tenant/seller/date mismatch, missing dimensions и immutable snapshot. Затем
facade/cursor/history/OpenAPI/concurrency. Делать маленькими commits, targeted
tests после каждого. После интеграции — полный backend suite один раз.

### Шаг 4. Реализовать Wave 4 frontend

Открыть Wave 4 narяд точной командой из принятого
`tasks/billing-04-invoices/TASK.md`. Использовать только принятый UI-kit.
Сохранить старый экран legacy invoices и его regressions. Сделать unit/E2E,
потом независимый reviewer/ui-critic и живой browser 1600/1280/print.

### Шаг 5. Принять Wave 4 целиком

Не считать Wave 4 готовой без:

- full backend pytest;
- full frontend unit/tsc/build/Playwright;
- guards/migrations/diff-check;
- независимого code review;
- `PRODUCT_BROWSER_APPROVED`;
- screenshots + `VERDICT.md` committed/pushed.

### Шаг 6. Вернуться к Wave 5

Сначала закончить и принять грязный contract rework. Затем backend и frontend,
без параллельного изменения Wave 4. Проверить single-source packaging payout,
configured zero, deleted employee name snapshot и отсутствие двойной оплаты.

### Шаг 7. Интеграция

После Wave 5 выполнить один полный интеграционный прогон и живую проверку всех
трёх вкладок: «Селлеры», «Счета», «Сотрудники». Merge в main или deploy не делать
без отдельного разрешения владельца.

## 6. Что нельзя повторять

- Не запускать полный 18-минутный backend suite после каждого маленького diff.
- Не запускать несколько контрактных агентов одновременно с product dev одного
  экрана.
- Не принимать fixture/Playwright/curl за живой browser verdict.
- Не объявлять candidate принятым до независимого verdict.
- Не доверять сообщению агента без проверки кода: storage flow — пример такого
  расхождения.
- Не давать коротких ETA без разложения оставшегося scope.
- Не трогать старые экраны «заодно» и не добавлять ad-hoc MUI.
- Не смешивать untracked baseline artifacts с task commits.

## 7. Разбор провала процесса

Полезный результат есть, но оркестрация была неприемлемо медленной.

Доказуемые потери:

- два полных backend запуска потеряли process handle/output: около 45 минут;
- третий полный backend запуск пришлось повторить: ещё 18 минут полезной, но
  вызванной потерей предыдущих результатов работы;
- первая browser fixture не реализовала notifications endpoint и дала blank
  screen;
- одна live-judge сессия не получила in-app browser и была перезапущена;
- Wave 4 contract прошёл несколько исправительных кругов из-за payload,
  evidence, tenant FK, task-test и ложного `S-19`;
- Wave 5 contract был начат параллельно слишком рано и остался грязным;
- commit `6081aeb7` случайно переформатировал большой файл и потребовал correction;
- UI-kit tests дали зелёный suite, но проверяли константы/private validators, а
  не пользовательское поведение.

Минимум напрямую доказуемого чистого простоя — около 1.5–2 часов. Общие потери на
переключение ролей и повторные contract loops больше, но точное число без полного
event-log нельзя честно назвать.

## 8. Короткий статус для владельца

```text
Полоса: обычная
Экран: /app/ff/billing (не S-19)
Стадия: Wave 4 development
Статус: Waves 2A/2B/3 приняты в ветке; Wave 4 backend частичный; Wave 4 frontend отсутствует; Wave 5 не начата
Product tip: 1078fae7eb24cacd6ff41b846afe0192f0dafc39
Доказательства: docs/evidence/20260827-volna-3-otchet-po-selleram/
Раунд правок: Wave 4 UI-kit требует rework behavioral tests
Блокеры: незаконченный storage integration/facade/frontend; Wave 5 contract rework dirty
```
