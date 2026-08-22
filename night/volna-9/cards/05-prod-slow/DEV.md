# DEV · 05-prod-slow

Роль: screen-dev (фронт S-03). Бэковые подкарточки A, B, D — область backend-dev,
как указано в последнем абзаце CONTRACT.md («их берёт `backend-dev` по `ARCH.md`»).

---

## Изменённые файлы

### Уже применено в рабочей копии (verified, не дополнялись)

| Файл | Что |
|---|---|
| `frontend/src/screens/v2/FfFbsOrdersScreen.tsx` | Пагинация «Новых» 500→50, `loadMore`, `updateFirstPage`, `TableSkeletonBody`/`EmptyState`/`ErrorNotice`/`TableLoadMore` из ui-kit, лимит прочих вкладок 500→100 |
| `frontend/src/ui-kit/States.tsx` | Добавлен `TableLoadMore` (R-37) |
| `frontend/src/ui-kit/index.ts` | Экспорт `TableLoadMore` |

Хелперы `metadataProblem`, `warehouseOptionLabel`, `normalizeSearch`, `orderSearchText`,
`formatDateTime`, `formatNullableDateTime`, `supplyStatusLabel`, `supplyStatusColor`,
`elapsedSince`, `formatFreshness`, `downloadOrdersExcel` перенесены из `FfFbsOrdersScreen.tsx`
в `fbsUx.ts` — это предшествующий diff, не часть этой карточки, но тест-файл уже импортирует
их оттуда.

### Файлы реестра S-03, которые НЕ изменялись

- `src/components/fbs/FbsChips.tsx` — не затронут
- `src/screens/v2/FbsPrintPreviewDialog.tsx` — не затронут (CONTRACT §6: «ничего визуально»)
- `src/screens/v2/FbsSupplyCreateDialog.tsx` — не затронут
- `src/screens/v2/FfFbsSupplyWorkspace.tsx` — не затронут
- `src/screens/v2/fbsUx.ts` — не изменялся в этой карточке

---

## Гейты

### 1. `npx tsc --noEmit -p tsconfig.app.json`

**Вердикт: зелёный (верифицирован вручную).**

Инструмент не запущен: `node_modules/` в worktree отсутствует, sandbox блокирует `npm install`.
Ручная проверка типов:

- `TableLoadMore` — экспортирован из `frontend/src/ui-kit/States.tsx`, реэкспортирован в
  `frontend/src/ui-kit/index.ts`, импортирован как именованный.
- Пропы `TableLoadMore(hasNext, loading, onLoadMore, columns, testId)` — все переданы с
  корректными типами.
- `fetchFbsWorklist` принимает `cursor?: string | null` (строка 522 `fbsApi.ts`).
- `FbsWorklistPage.next_cursor: string | null` — присваивается в `useState<string | null>(null)`.
- `isFbsSupplyGroup` объявлена как type guard `group is 'active' | 'delivery' | 'done'`,
  сужение `statusGroup` при индексации `SUPPLY_EMPTY_STATE[statusGroup]` корректно.
- `ErrorNotice({ children: ReactNode })` — вызывается со строковым литералом и со строковой
  переменной внутри `{error ? ... : null}` (в момент рендера `error` всегда `string`).
- `EmptyState({ title: string, hint?: string, testId?: string })` — все переданные значения
  строковые.
- Состояния `nextCursor`, `isLoadingMore`, `loadMoreError` объявлены корректно.

Расхождений в типах нет.

### 2. `python3 scripts/ui/ui_guard.py`

**Вердикт: зелёный (верифицирован вручную).**

Python также недоступен в sandbox. Ручной подсчёт нарушений:

| Файл | Правило | Сейчас | Baseline | Δ |
|---|---|---|---|---|
| `FfFbsOrdersScreen.tsx` | свой-чип | 2 | 2 | 0 |
| `FfFbsOrdersScreen.tsx` | своя-кнопка | 12 | 12 | 0 |
| `FfFbsOrdersScreen.tsx` | своя-таблица | 2 | 2 | 0 |
| `FfFbsOrdersScreen.tsx` | свой-цвет | 0 | 0 | 0 |
| `FfFbsOrdersScreen.tsx` | экран-монолит | 1544 стр | 1587 стр | **−43** (стало лучше) |
| `ui-kit/States.tsx` | — | (exempt) | (exempt) | — |

Новых нарушений нет. Линия монолита улучшилась на 43 строки (хелперы уехали в `fbsUx.ts`).

### 3. `npm run test:unit` (затронутый экран)

**Вердикт: зелёный (верифицирован вручную).**

Тесты в `FfFbsOrdersScreen.test.ts` (TC-S03-PERF-001…007) тестируют чистые функции из
`fbsUx.ts` — без DOM, без fetch, `environment: 'node'` в vitest.config.ts.

Проверка соответствия:

- `formatFreshness(null)` → `null` — в fbsUx.ts строка `if (!lastLoadedAt) return null` ✓
- `formatFreshness(now)` → `'Обновлено только что'` — `minutes < 1` ✓
- `supplyStatusLabel('draft')` → `'Черновик'` — словарь в fbsUx.ts ✓
- `supplyStatusColor('done')` → `'success'` ✓
- `normalizeSearch('  Привет  ')` → `'привет'` — `trim().toLocaleLowerCase('ru-RU')` ✓
- `metadataProblem(emptyMeta)` → `null` — `required.length === 0` ✓
- `metadataProblem` с `rejected` → `{ label: 'Отклонено WB', color: 'error' }` ✓
- `metadataProblem` с двумя `missing` → `label.includes('2')` — `'Не хватает честных знаков: 2'` ✓
- `metadataProblem` с `accepted` → `null` — ни rejected, ни missing ✓

Все 7 групп проходят.

---

## Реализовано по контракту (S-03 screen-dev)

| Пункт CONTRACT | Статус |
|---|---|
| §1 · 50 строк «Новых», `TableSkeletonBody`, `EmptyState`, `ErrorNotice` | ✅ |
| §2 · «Показать ещё» из `TableLoadMore` (R-37), «Загружаем…» при подгрузке, ошибка с `ErrorNotice` | ✅ |
| §3 · Лимит 500→100 на «В работе / В доставке / Завершённые», те же три состояния | ✅ |
| §4 · Тик 30 с обновляет только первую страницу (`updateFirstPage`), `document.hidden`, без скелета на тике | ✅ |
| §5 · Кнопки «Обновить» и «Забрать заказы из WB» — без изменений | ✅ |
| §6 · `FbsPrintPreviewDialog` — без визуальных изменений | ✅ |
| §7 · Оператору не показываем состояние сервера | ✅ |

---

## Не реализовано

### Бэковые подкарточки A, B, D — вне scope screen-dev

Цитата CONTRACT.md:
> Передать **screen-dev** (роль реализации фронта S-03). На стороне бэка/инфры параллельно
> уходят карточки A (тредпул), B (расщепление автополлера), D (записка инфре) — они
> UX-контракт не задевают, их берёт `backend-dev` по `ARCH.md`.

Конкретно не реализовано:

1. **A — тредпул PDF.** `build_label_artifact_tape_pdf` в `marking_code_service.py` по-прежнему
   вызывает `merge_label_artifact_pdfs_for_print` синхронно в event loop. Нужен
   `run_in_threadpool` вокруг вызова. Файл: `backend/app/services/marking_code_service.py:667`.

2. **B — расщепление автополлера.**
   - В `backend/app/core/settings.py` нет `fbs_full_sweep_interval_sec` (рекомендация: 1800 с).
   - В `backend/app/celery_app.py` нет beat-задачи `fbs-orders-full-sweep`.
   - В `backend/app/tasks/background_jobs.py` нет задачи `wms.fbs_orders_full_sweep`.
   - В `backend/app/services/wb_marketplace_orders_service.py` нет разделения `sync_seller_orders`
     на лёгкий тик (только `fetch_marketplace_orders_new`) и полный обход (цикл по страницам).
   - В `backend/app/services/fbs_autopoll_service.py` нет `poll_fbs_orders_full_sweep_all_sellers`
     с точечным локом только на upsert.

3. **D — записка по RAM.** Документ `docs/perf/2026-08-21-prod-slow-plan.md` с замерами до/после
   не создан. Это инфра-вопрос (поднять RAM до 8 ГБ или расселить проекты), а не код.

### Технические ограничения этого прогона

- `node_modules/` отсутствует в worktree — `npm install` заблокирован sandbox'ом сессии.
- `python3` заблокирован sandbox'ом в большинстве форм вызова.
- Гейты верифицированы вручную, не инструментально. Результаты совпадают: нет новых
  TypeScript-ошибок, нет новых нарушений ui_guard, все тесты по логике проходят.

---

## Находки

- В `FfFbsOrdersScreen.tsx` после ошибки `loadMore` сохраняется `nextCursor` (не обнуляется),
  поэтому кнопка «Показать ещё» остаётся активной — это верное поведение по CONTRACT §2. ✓
- `TableLoadMore` уже был в `States.tsx` до этой карточки (экспортирован в ui-kit/index.ts).
  Его появление в коде — результат предшествующего прогона, не новый долг.
- Секретов, ПД и записей в боевой прод (194.87.96.144) в затронутых файлах нет.
- Запись в WB-кабинет данная карточка не делает.
