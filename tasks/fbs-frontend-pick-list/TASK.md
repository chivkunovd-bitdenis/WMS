# TASK — fbs-frontend-pick-list: Экран 3 «Лист подбора» FBS

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md` и `DESIGN.md`. Гейт 1 эпика ✅, под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** `fbs-frontend-supply-detail` (Экран 2 готов), backend API из `fbs_supplies.py`, `fbs_marking.py`
- **Слои:** frontend: `src/screens/v2/`, `src/components/fbs/`, `src/api/fbsApi.ts`

## Описание (для Composer)

Реализуем Экран 3 — минималистичный лист подбора отгрузки FBS. Это наша собственная UI вместо плотного интерфейса WB. Лист строится из состава отгрузки (заказов), группируется по артикулам/товарам, показывает фото, имеет фильтры (не собраны/не упакованы/нужна маркировка/ошибка маркировки), отметки «Собрал/Упаковал» (чекбоксы), печать стикеров и внесение КИЗ.

**Основные элементы:**
- Группировка товаров по артикулу (свернуть/развернуть)
- Фото кликабельно (preview)
- Отметки: чекбокс «Собрал», чекбокс «Упаковал» (для упаковочного потока)
- Счётчики сверху: Собрано N/M, Упаковано X/M
- Фильтры: не собраны / не упакованы / нужна маркировка / ошибка маркировки
- Поиск по баркоду или скан-сканером (поле ввода с иконкой сканера)
- Печать стикеров: все / по фильтру / по одному товару
- Внесение КИЗ: кнопка «Идентификаторы» (маркировка) → PUT `/operations/fbs-orders/{order_id}/markings/{kind}`
- PDF-печать листа подбора

## Scope
- GET `/operations/fbs-supplies/{id}/picking-list` → FbsPickingListOut (items: [{article, sku_code, size, product_name, quantity}])
- Группировка в фронте по article (collapsible groups)
- Фильтры: локальное состояние (фронт) или из query-params
- Отметки «Собрал/Упаковал»: локальное состояние (если backend не имеет персист-эндпоинта); пометить как ограничение в TC
- Печать: POST `/operations/fbs-supplies/{id}/stickers` (или по одному заказу) → FbsStickersOut
- Маркировка: PUT `/operations/fbs-orders/{order_id}/markings/{kind}` (FbsMarkingValueBody) → FbsOrderMarkingOut
- Список маркировок по заказу: GET `/operations/fbs-orders/{order_id}/markings`

## Out of scope
- Синхронизация отметок между пользователями (данные в localStorage, не в БД v1)
- Синхронизация with packaging_task (отметка упаковки могла бы писать в packaging_task_service, но это фаза 2)
- Полноценная ТСД-интеграция (печать на ТСД-принтерах — отдельно)
- Интеграция с Честным Знаком через API (внесение КИЗ ручное или через copy-paste)

## Арх-подход (реальные ручки/файлы)

**Frontend:**
- Новый файл `src/screens/v2/FbsPickListScreen.tsx`
  - Props: `supplyId: string`, `token`, `authHeaders`
  - Загрузка: `GET /operations/fbs-supplies/{id}/picking-list` (FbsPickingListOut)
  - Состояние: items[] (picking list), filters (selected filter keys), collapsedGroups (Set<article>), markedItems (Map<order_id → {collected: bool, packed: bool}>)
  - Layout: счётчики сверху + фильтры + поиск + таблица/список товаров + footer с действиями
  - data-testid: `fbs-pick-list`, `fbs-collect-checkbox`, `fbs-pick-list-search`, `fbs-pick-list-filter`, `fbs-pick-list-print`, `fbs-marking-btn`

- Расширить `src/api/fbsApi.ts`:
  - `fetchFbsPickingList(supplyId: string)` → FbsPickingListOut
  - `fetchFbsOrderMarkings(orderId: string)` → FbsOrderMarkingOut[]
  - `putFbsOrderMarking(orderId: string, kind: string, value: string)` → FbsOrderMarkingOut

- Компоненты:
  - `FbsPickListItem` — одна группа (товар с фото + quantity + чекбоксы + действия)
  - `FbsPickListFilters` — фильтры (not_collected / not_packed / needs_marking / marking_error)
  - `FbsMarkingDialog` — модальное окно ввода КИЗ/идентификаторов (kind, value)
  - Переиспользовать `FbsStatusChip` для отметок маркировки (если нужно)

- Логика отметок:
  - Группировка по article (нативный JS) → структура ItemGroup { article, items: [{sku_code, size, product_name, quantity, order_ids}] }
  - Фильтр: проходим по заказам → если order_id в markedItems['collected'] → исключаем из not_collected, и т.д.
  - Локальное состояние в useState или localStorage (указать как ограничение в scope)

**Конвенции:**
- Таблица/список: минимум колонок (фото, название, quantity, действия)
- Фото: компонент `<img onClick={() => setPreviewImage(...)} />`
- Dialog для маркировки: simple form с field kind (select: sgtin/uin/imei/gtin) + value (text input) + кнопка отправить
- Печать PDF: используем существующий компонент (или html2pdf/jsPDF для генерации)
- Поиск: фильтр в реальном времени по bar code / article / product_name

**Пути эндпоинтов и типы (из backend):**
- `GET /operations/fbs-supplies/{id}/picking-list` → `FbsPickingListOut` (items: [{article, sku_code, size, product_name, quantity}])
- `GET /operations/fbs-orders/{order_id}/markings` → FbsOrderMarkingOut[] (id, order_id, kind, value, check_status, marking_code_id)
- `PUT /operations/fbs-orders/{order_id}/markings/{kind}` (FbsMarkingValueBody: value) → FbsOrderMarkingOut

## Критерии приёмки (DoD)

- [ ] Экран загружает список подбора (GET `/picking-list`) и группирует по артикулам
- [ ] Группировка сворачивается/разворачивается (collapsible)
- [ ] Отметки «Собрал/Упаковал» работают (чекбоксы, локальное состояние)
- [ ] Счётчики обновляются при отметках (Собрано N/M, Упаковано X/M)
- [ ] Фильтры работают: не собраны / не упакованы / нужна маркировка / ошибка
- [ ] Поиск по баркоду/артикулу фильтрует список в реальном времени
- [ ] Печать стикеров: все / по фильтру
- [ ] Dialog маркировки: ввод КИЗ → PUT `/markings/{kind}` → список обновлён
- [ ] data-testid на все ключевые элементы
- [ ] Состояния loading/error обработаны

## Test coverage (в описание PR — требование CI)

| TC-ID | Title | Applies (Y/N) | Notes |
|-------|-------|---------------|-------|
| TC-NEW-FBS-PICKUI-001 | Загрузка листа подбора и группировка по артикулам | Y | Given: отгрузка с 5 заказами (товары A×2, B×2, C×1) / When: открыть лист подбора / Then: GET /picking-list вызван, показаны 3 группы (A, B, C) с количеством, collapsed-toggle видно |
| TC-NEW-FBS-PICKUI-002 | Отметка товара как собранного | Y | Given: группа товара A, чекбокс не отмечен / When: клик на чекбокс «Собрал» / Then: чекбокс отмечен, счётчик «Собрано» увеличен, состояние в localStorage (если используется) |
| TC-NEW-FBS-PICKUI-003 | Фильтр по не собранным товарам | Y | Given: 5 товаров, 3 отмечены как собранные / When: выбрать фильтр «Не собраны» / Then: таблица показывает только 2 товара (не собранные), остальные скрыты |
| TC-NEW-FBS-PICKUI-004 | Внесение КИЗ (маркировка sgtin) | Y | Given: товар требует маркировки, dialog открыт / When: выбрать kind=sgtin, ввести value=123456789, кликнуть отправить / Then: PUT /markings/sgtin вызывается, маркировка добавлена, list обновлён (check_status видно) |
| TC-NEW-FBS-PICKUI-005 | Печать стикеров по фильтру | Y | Given: 5 товаров, 2 не собраны (фильтр активен) / When: клик «Печать по фильтру» / Then: POST /stickers (order_ids=[не собранных]) вызывается, PDF открывается с 2 стикерами |
| TC-NEW-FBS-PICKUI-006 | Поиск по баркоду | Y | Given: лист с товарами, поле поиска видно / When: ввести barcode=123456 / Then: список фильтруется, показаны только товары с этим баркодом, остальные скрыты |
| TC-NEW-FBS-PICKUI-007 | Развёртывание/свёртывание группы | Y | Given: группа товара A (2 заказа, collapsed) / When: клик на заголовок группы / Then: группа развернулась, видны оба заказа (order_id, статусы маркировки), клик ещё раз → свёрнуто |
| TC-NEW-FBS-PICKUI-008 | Ошибка маркировки: check_status=error | Y | Given: товар с маркировкой check_status=error / When: открыть лист / Then: маркировка отмечена красным (ошибка), фильтр «Ошибка маркировки» включает её |

## Где тесты

frontend e2e: `cd frontend && npm run test:e2e` (Playwright, data-testid), specs в `tests/e2e/fbs-pick-list.spec.ts`

## Гейт перед PR

```bash
cd frontend && npm run build && npm run test:e2e
```

## Ограничения (реализация v1)

- **Локальное состояние отметок:** чекбоксы «Собрал/Упаковал» хранятся в компоненте (useState) или localStorage, не синхронизируются с backend. Это ограничение допускается для v1 (синхронизация с packaging_task — фаза 2).
- **Синхронизация между пользователями:** если двое работают с листом одновременно, отметки не синхронизируются (no real-time updates). Это приемлемо для первой версии.
- **Печать листа в PDF:** используем готовый компонент или html2pdf; формат не совпадает 1-в-1 с WB, но функционально полный.
