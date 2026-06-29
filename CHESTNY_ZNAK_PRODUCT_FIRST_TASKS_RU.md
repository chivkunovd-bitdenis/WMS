# Честный Знак — переход на товар-центричную витрину (бэклог под Cursor Autopilot)

> **Контракт (читает orchestrator):**
> - Задача = строка таблицы; **id — первая ячейка**.
> - **Закрыто** = `.cursor/state/<id>.done` (создаёт orchestrator после verifier). **Таблицу не редактируем.**
> - **Заблокировано** = `.cursor/state/<id>.blocked` (3 фейла подряд).
> - **depends_on** — id-предшественники; задача runnable, когда все они `.done`.
> - **files** — что задача правит; две задачи с пересечением `files` **не** идут параллельно.
> - **gate** — команда проверки (зелёная = задача готова к `.done`).
> - Изоляция: каждый builder в `git worktree .cursor/wt/<id>`, коммит там.
> - Контекст/обоснование — ниже в «Детали задач». Берёшь **одну** задачу, не начинаешь следующую, пока текущая не зелёная.

## Зачем это (одно предложение)

Сейчас входная дверь блока ЧЗ — **пул** (технический объект). Делаем входную дверь **товаром**, а пул
оставляем уровнем глубже как «корзину кодов». Попутно чиним двойной счёт остатка на общих GTIN.

## Инварианты (НЕ нарушать — это рефактор представления, не модели)

- **И1.** Пул = одна ЧЗ-карточка = один GTIN. Не трогаем.
- **И2.** Связь «пул ↔ товары» — ручная M2M (`marking_pool_products`). Не трогаем.
- **И3.** Остаток физически считается **на пул**. «Личный/общий» — это **производное представление**, а
  не новое поле остатка. Запрещено переносить остаток на товар или плодить дубли кодов.
- **Определения (новые, только для UI/ответов):**
  - **Личный пул товара** — пул, к которому привязан **ровно один** товар (`linked_products_count == 1`).
  - **Общая корзина** — пул, к которому привязано **≥2** товаров (`linked_products_count >= 2`).
  - **Личный остаток товара** = сумма `available` по его личным пулам.
  - **Общие корзины товара** = список общих пулов, где он участвует (показываем тотал корзины и состав,
    **не** вливаем в личный остаток).
- Деление личный/общий определяется **автоматически** по числу привязанных товаров. Ручного флага нет.

## Карта экранов (целевая)

| ID | Экран | Маршрут (ФФ) | Было → Стало |
|----|-------|--------------|--------------|
| Э1 | Список **товаров** ЧЗ | `/app/ff/honest-sign` | был список пулов → станет список товаров |
| Э2 | Карточка **товара** | `/app/ff/honest-sign/product/:productId` | **новый** экран |
| Э3 | Карточка **пула/корзины** | `/app/ff/honest-sign/pool/:poolId` | остаётся, но вход из Э2; добавляем «общий на N товаров» |

## Задачи

| id | depends_on | files | gate | task |
|----|-----------|-------|------|------|
| SVC-01 | - | backend/app/services/marking_code_service.py | cd backend && ruff check . && mypy . && pytest | Расширить inventory: считать личный остаток (пулы с 1 товаром) и список общих корзин на товар; убрать двойной счёт общих пулов |
| SVC-02 | SVC-01 | backend/app/services/marking_code_service.py | cd backend && ruff check . && mypy . && pytest | В list-rows пулов отдавать `linked_products_count` и флаг `is_shared` |
| API-01 | SVC-01 | backend/app/api/marking_codes.py | cd backend && ruff check . && mypy . && pytest | `/inventory` отдаёт `personal_available` + `shared_baskets[]` на товар; новый GET `/products/{id}/marking-overview` |
| API-02 | SVC-02,API-01 | backend/app/api/marking_codes.py | cd backend && ruff check . && mypy . && pytest | В PoolListItemOut/PoolDetailOut добавить `is_shared`, `linked_products_count`, состав `shared_with` |
| LIST-01 | API-01 | frontend/src/screens/shared/HonestSignScreen.tsx | cd frontend && npm run build | Переделать главный экран в список товаров: товар · личный · общая корзина(чип) · прогноз; клик → карточка товара |
| PROD-01 | API-01,API-02 | frontend/src/screens/shared/HonestSignProductPage.tsx | cd frontend && npm run build | Новый экран карточки товара: личный остаток, раздел «Откуда коды» (личные пулы + общие корзины со ссылками) |
| PROD-02 | PROD-01 | frontend/src/screens/shared/HonestSignProductPage.tsx | cd frontend && npm run build | Вкладки «Коды» и «Лента» в карточке товара на готовых ручках `/products/{id}/codes` и `/ledger?product_id=` |
| POOL-01 | API-02 | frontend/src/screens/shared/HonestSignPoolPage.tsx | cd frontend && npm run build | Переименовать смысл пула в «корзину»: бейдж «общий на N товаров», на вкладке «Товары» — состав и пометка про общий расход |
| APP-01 | PROD-01 | frontend/src/App.tsx | cd frontend && npm run build | Добавить маршрут `/honest-sign/product/:productId` (ФФ и селлер), смонтировать HonestSignProductPage |
| E2E-01 | LIST-01,PROD-01,PROD-02,POOL-01,APP-01 | frontend/tests/e2e/honest-sign.spec.ts | cd frontend && npm run test:e2e | e2e сценарий: товары → личный/общий корректны → клик в товар → переход в корзину; общий пул не задвоен |

<!--
Дорожки:
- BE: SVC-01 → SVC-02 → (API-01,API-02) — один сервис-файл + один api-файл, две цепочки, API ждёт SVC.
- FE: LIST-01 (свой файл) ∥ PROD-01 (новый файл) ∥ POOL-01 (свой файл) — параллельно, после API.
- CROSS: APP-01 после PROD-01; E2E-01 в самом конце.
Параллелизм реальный: после API-02 три FE-дорожки идут одновременно → старт 3 агентов хватит.
-->

---

# Детали задач

Для каждой: **Цель / Что сделать / Acceptance / Тест**. Слои по AGENTS.md. Definition of Done общий:
ruff+mypy+pytest зелёные (BE), `npm run build` зелёный (FE), добавлены тесты из «Тест», инварианты целы.

## SVC-01 — личный остаток + общие корзины в inventory

**Цель.** Чтобы остаток не задваивался на общих GTIN и появилась основа для товар-витрины.
**Сейчас (баг).** В `list_inventory` цикл `for pool_id, product_id in pool_links` прибавляет полный
`available_by_pool[pool_id]` **каждому** привязанному товару → общий пул 1000 на 5 товаров даёт по 1000
каждому (итого 5000).
**Что сделать.**
- Посчитать `linked_count[pool_id]` = число товаров пула (из `marking_pool_products`).
- Ввести в `ProductMarkingInventoryRow` (или новый dataclass-обёртку) поля:
  - `personal_available: int` — сумма `available` по пулам товара, где `linked_count == 1`.
  - `personal_printed: int` — аналогично для printed.
  - `shared_baskets: list[SharedBasketRow]`, где `SharedBasketRow = {pool_id, gtin, title, available, printed, products_count}` — по пулам товара с `linked_count >= 2`.
- `available_count`/`printed_count` оставить для обратной совместимости, но переопределить семантику:
  `available_count = personal_available` (НЕ суммировать общие). Общие — только в `shared_baskets`.
- Не ломать `unlinked_available_count`.
**Acceptance.** Дано: пул A (1 товар, 100 КМ available), пул B (товары X,Y,Z, 1000 КМ available), X∈A,B.
Когда: `list_inventory`. Тогда: у X `personal_available=100`, `shared_baskets=[{B,1000,products_count:3}]`;
у Y,Z `personal_available=0`, та же корзина B. Сумма personal по всем товарам не превышает реальные КМ.
**Тест.** pytest: кейс выше (нет задвоения); товар только в общем пуле → personal=0 + одна корзина;
товар в двух личных пулах → personal суммируется; пустой селлер → пусто.

## SVC-02 — флаг общего пула в строках пулов

**Цель.** Чтобы списки/карточка пула знали, личный он или общий.
**Что сделать.** В `PoolListRow` (и источник `PoolDetail`) добавить `linked_products_count: int` и
производный `is_shared: bool = linked_products_count >= 2`. Заполнять из `marking_pool_products`.
**Acceptance.** Пул с 1 товаром → `is_shared=False`; с ≥2 → `True`; с 0 товаров → `False`.
**Тест.** pytest на三 кейса (0/1/2 товара).

## API-01 — выдача товар-центричных данных

**Цель.** Фронт получает личный/общий на товар.
**Что сделать.**
- `MarkingInventoryRowOut` дополнить: `personal_available`, `shared_baskets[]`
  (`{pool_id, gtin, title, available, products_count}`). `available_count` оставить = personal.
- Новый `GET /operations/marking-codes/products/{product_id}/marking-overview` →
  `{product:{id,sku_code,name,requires_honest_sign}, personal_pools:[{pool_id,gtin,title,available,printed,loaded}], shared_baskets:[{pool_id,gtin,title,available,products_count}]}`.
  Мультитенантно + scope по seller (как соседние ручки).
**Acceptance.** GET inventory отдаёт у товара X personal+корзины как в SVC-01. GET marking-overview по X
возвращает его личные пулы и общие корзины раздельно. Чужой tenant/seller → 404/403 как принято.
**Тест.** pytest (httpx): форма ответа inventory; overview по товару с личным+общим; изоляция tenant.

## API-02 — общий флаг и состав в ответах пула

**Цель.** Карточка пула показывает «общий на N товаров» и состав.
**Что сделать.** В `PoolListItemOut` и `PoolDetailOut` добавить `is_shared: bool`,
`linked_products_count: int`. В `PoolDetailOut` — `shared_with: [{id,sku_code,name}]` (товары пула; при
общем пуле это и есть состав корзины). Заполнять из SVC-02.
**Acceptance.** Ответ пула с 3 товарами: `is_shared=true`, `linked_products_count=3`, `shared_with` из 3.
**Тест.** pytest: общий и личный пул в ответах list+detail.

## LIST-01 — главный экран = список товаров

**Цель.** Входная дверь — товары, без жаргона «пул».
**Что сделать (в `HonestSignScreen.tsx`).**
- Источник данных — `/inventory` (вместо `/pools`). Тип строки — товар.
- Колонки: **Товар** (sku + название) · **Личный остаток** (`personal_available`) · **Общая корзина**
  (чип `🧺 {available} · на {products_count} тов.` на каждую корзину; если нет — «—») · **Напечатано** ·
  **Прогноз** (если есть; для товара без личного пула прогноз «по корзине», см. ниже).
- Заголовок/описание переписать в товарных терминах (убрать слово «пул» с витрины).
- KPI-карточки пересчитать по товарам (доступно личных всего, на исходе, брак — оставить если есть в данных).
- Поиск: по sku/названию. Фильтр «на исходе/пусто» — по личному остатку.
- Клик по строке → `navigate('/app/ff/honest-sign/product/{productId}')`.
- Кнопки «Загрузить КМ» и «Лента расхода» сохранить.
**Acceptance.** Открываю экран → вижу товары, у общего GTIN остаток НЕ задвоен (личный и чип корзины
раздельно). Клик по товару ведёт на карточку товара.
**Тест.** e2e (в E2E-01): список товаров рендерится; общий пул показан чипом, а не вкладывается в личный.

## PROD-01 — карточка товара (новый экран)

**Цель.** Вся детализация по товару; пулы — здесь, как «откуда коды».
**Что сделать (новый `HonestSignProductPage.tsx`, по образцу `HonestSignPoolPage.tsx` и эталона
`FfProductsCatalogScreen.tsx`).**
- Хедер: название товара, sku, бейдж «Нужен ЧЗ».
- Сводка: «Доступно личных: {personal_available}» + «Доступ к общим корзинам: N».
- Раздел **«Откуда коды»**: список `personal_pools` (загрузка/итерация: title, loaded, available, ссылка
  на пул) и `shared_baskets` (title, available, «делится с N товарами», ссылка на пул `…/pool/{id}`).
- Данные из `GET /products/{id}/marking-overview`.
- Вкладки «Коды»/«Лента» — заголовки вкладок завести здесь (контент в PROD-02).
**Acceptance.** Открываю карточку товара X → вижу личные пулы и общие корзины раздельно, клик по корзине
ведёт в карточку пула.
**Тест.** e2e (в E2E-01): переход список→товар→корзина.

## PROD-02 — вкладки «Коды» и «Лента» в карточке товара

**Цель.** Полная детализация по товару без захода в пул.
**Что сделать (в `HonestSignProductPage.tsx`, ручки уже готовы на бэке).**
- Вкладка **«Коды»**: `GET /operations/marking-codes/products/{productId}/codes` — таблица как в
  `HonestSignPoolPage` (КМ, статус, дата), фильтр по статусу.
- Вкладка **«Лента»**: `GET /operations/marking-codes/ledger?product_id={productId}&limit=5` — превью
  последних событий + ссылка «Вся лента товара» (`/honest-sign/ledger?product_id={id}`).
- Переиспользовать `codeStatusLabel`/`ledgerEventLabel` и существующие табличные паттерны.
**Acceptance.** На карточке товара вкладки «Коды» и «Лента» показывают данные именно этого товара.
**Тест.** e2e (в E2E-01): открыть вкладку «Коды» товара → видны его КМ.

## POOL-01 — карточка пула как «корзина»

**Цель.** Пул перестаёт быть входной дверью и честно подписан, когда он общий.
**Что сделать (в `HonestSignPoolPage.tsx`).**
- В хедер при `is_shared` добавить бейдж «Общая корзина · на {linked_products_count} товаров».
- На вкладке «Товары»: показать `shared_with` как состав корзины; алерт уже есть
  («Остаток КМ общий на весь пул») — уточнить текст: при общем пуле «расходуется по факту отгрузки,
  не делится поровну между товарами».
- Кнопку «Назад» оставить, но смысл — назад к товару/списку (роут не меняем здесь, меняет APP-01).
- Поведение для личного пула (1 товар) — без бейджа, как сейчас.
**Acceptance.** Общий пул показывает бейдж и состав; личный — без бейджа.
**Тест.** e2e (в E2E-01): на общем пуле виден бейдж «на N товаров».

## APP-01 — маршрут карточки товара

**Цель.** Смонтировать новый экран.
**Что сделать (в `App.tsx`).** Добавить route `ff/honest-sign/product/:productId` (и аналог для селлера,
если есть ветка `/seller/honest-sign`) → `<HonestSignProductPage token={token} testIdPrefix="ff-honest-sign-product" />`.
Импорт компонента. Не ломать существующие роуты пула/ленты/импорта.
**Acceptance.** Прямой переход по `/app/ff/honest-sign/product/<id>` рендерит карточку товара.
**Тест.** покрывается E2E-01.

## E2E-01 — сквозной сценарий

**Цель.** Зафиксировать новую навигацию и отсутствие двойного счёта.
**Что сделать.** e2e: засидить товар X (личный пул 100) + общую корзину B (X,Y,Z, 1000). Шаги:
1) Открыть `/honest-sign` → у X личный 100 и чип корзины «на 3 тов.»; сумма личных по товарам без задвоения.
2) Клик по X → карточка товара, видны личный пул и корзина B.
3) Клик по корзине B → карточка пула с бейджем «Общая корзина · на 3 товаров».
**Acceptance.** Все три шага зелёные.
**Тест.** этот спек и есть тест.

---

## Запуск (новый чат Cursor)

```text
orchestrator, continuous, queue mode, 3 агента. backlog: CHESTNY_ZNAK_PRODUCT_FIRST_TASKS_RU.md
Worker pool: 1 id = 1 builder, refill on free slot.
Изоляция: git worktree .cursor/wt/<id> на задачу, коммит в нём.
Готово = touch .cursor/state/<id>.done после verifier. Бэклог не редактировать.
builder → verifier → fix (max 3).
```
