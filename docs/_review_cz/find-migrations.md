# Ревью миграций Alembic (диапазон 4e82c6b..HEAD, маска 2026062*)

## Резюме
Найдено: **1 HIGH** (boolean `server_default=sa.text("0")` ломает `alembic upgrade` на PostgreSQL),
**1 LOW** (мусорный бинарник `tmp_alembic_test.sqlite` не в `.gitignore`),
**1 LOW/требует подтверждения** (нет DB-UNIQUE на пул `(tenant_id, seller_id, gtin)`).
Цепочка ревизий 0041→…→0052 — **линейная, без разрывов/дублей/циклов**. Бэкфилл старых кодов в пулы **есть** (0043). Симметрия up/down в целом корректна.

---

## [HIGH] `print_templates.is_default` — boolean DEFAULT `0` падает на PostgreSQL
- **Где:** backend/alembic/versions/20260626_0046_print_templates.py:29
- **Доказательство:**
```python
sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
```
- **Проблема:** Прод-СУБД — PostgreSQL (`app/core/settings.py:11`: `postgresql+psycopg_async://...`). В Postgres
  DDL `is_default boolean NOT NULL DEFAULT 0` падает с ошибкой
  `column "is_default" is of type boolean but default expression is of type integer`
  (Postgres не приводит integer-литерал `0` к boolean в default-выражении). Значит
  `alembic upgrade` на проде **упадёт на этой миграции**. Это единственная миграция в
  репозитории, использующая `sa.text("0")` для boolean — все остальные используют
  `sa.false()` / `sa.text("false")` (см. 0041:27, 0047:21, 0051:44, 0024, 0035 и др.), что
  подтверждает: это опечатка-выброс, а не осознанный SQLite-only стиль.
- **Фикс:** заменить на `server_default=sa.false()` (или `sa.text("false")`), как в соседних
  миграциях. SQLite такое тоже корректно проглотит, так что локальные тесты не сломаются.

---

## [LOW] Мусорный бинарник `tmp_alembic_test.sqlite` не игнорируется git
- **Где:** backend/tmp_alembic_test.sqlite (188 КБ), .gitignore
- **Доказательство:**
```
$ git status --short | grep alembic
?? backend/tmp_alembic_test.sqlite
$ grep sqlite .gitignore
28:backend/wms_pytest.sqlite
29:backend/tests/wms_pytest.sqlite      # tmp_alembic_test.sqlite НЕ перечислен
```
- **Проблема:** Файл untracked, но **не покрыт `.gitignore`** (там перечислены только
  `wms_pytest.sqlite`, `tests/wms_pytest.sqlite`, `alembic_autogen.db`). При `git add .`
  188-КБ бинарник попадёт в индекс/коммит. В диапазон 4e82c6b..HEAD он пока НЕ закоммичен
  (проверено `git log 4e82c6b..HEAD -- backend/tmp_alembic_test.sqlite` — пусто), поэтому LOW.
- **Фикс:** удалить файл (`rm "backend/tmp_alembic_test.sqlite"`) и добавить в `.gitignore`
  строку `backend/tmp_alembic_test.sqlite` (или обобщить: `backend/*.sqlite`).

---

## [LOW] Нет DB-UNIQUE на пул `(tenant_id, seller_id, gtin)` — требует подтверждения
- **Где:** backend/alembic/versions/20260626_0043_marking_pools.py:137-142 (только non-unique индекс)
- **Доказательство:**
```python
op.create_index(
    "ix_marking_pools_tenant_seller_gtin",
    "marking_pools",
    ["tenant_id", "seller_id", "gtin"],
    unique=False,          # <-- не UNIQUE
)
```
- **Проблема:** DESIGN (docs/CHESTNY_ZNAK_DESIGN_RU.md:74) фиксирует инвариант
  «один пул = один GTIN». Бэкфилл (`_backfill_marking_pools`) дедуплицирует пулы в памяти по
  ключу `(tenant_id, seller_id, gtin)`, поэтому **сам бэкфилл сирот не плодит и дублей не
  создаёт**. Но инвариант не закреплён на уровне БД: рантайм-код (создание пула при импорте)
  при гонке/повторе может создать второй пул на тот же GTIN, и БД это не предотвратит.
  Помечаю LOW/«требует подтверждения», т.к. это скорее замечание к инварианту, чем баг самой
  миграции — зависит от того, гарантирует ли уникальность сервисный слой.
- **Фикс (если инвариант обязателен):** сделать индекс `unique=True`
  (`UniqueConstraint("tenant_id","seller_id","gtin", name="uq_marking_pools_tenant_seller_gtin")`).
  Перед этим убедиться, что бэкфилл и существующие данные не содержат дублей.

---

## Что проверено и признано корректным (ЧИСТО)

- **Цепочка ревизий:** 0041→0042→0043→0044→0045→0046→0047→0048→0049→0050→0051→0052 —
  строго линейная, каждый `down_revision` указывает на предыдущую ревизию, дублей
  `down_revision` нет, циклов нет, разрывов нет.
- **Бэкфилл кодов в пулы (треб. п.3):** присутствует в 0043 (`_backfill_marking_pools`,
  строки 28-115). Переносит все `marking_codes` с `pool_id IS NULL` в пулы по
  `(tenant_id, seller_id, gtin)`, при пустом gtin берёт `extract_gtin_from_cis(cis_code)`
  (функция существует: `app/services/marking_code_service.py:347`), сиротами коды не
  остаются. Также заполняет `marking_pool_products`. Pre-existing колонки
  `gtin/product_id/cis_code/seller_id` созданы в 0041 — бэкфилл читает валидные поля.
- **Симметрия up/down:**
  - 0042: downgrade дропает 3 колонки + индекс + таблицу — симметрично.
  - 0043: downgrade дропает все 3 FK, 12 колонок, оба индекса/таблицы pools/pool_products —
    симметрично (бэкфилл данных при downgrade теряется, но это норма).
  - 0044/0048/0049: downgrade = `drop_table` (Postgres сам сносит зависимые индексы) — ок.
  - 0046/0051: индексы дропаются явно перед таблицей — ок.
  - 0047/0050/0052/0045: add_column ↔ drop_column — симметрично.
- **Nullability / FK-индексы (треб. п.4):** новые FK-колонки имеют индексы:
  `marking_codes.pool_id` → `ix_marking_codes_pool_id` (0043:242); все FK в
  pools/pool_products/code_events/reprint_requests проиндексированы. Новые NOT NULL-колонки
  на возможно непустых таблицах снабжены `server_default`:
  0047 `can_shift_lead` (`sa.false()`), 0052 `address_storage_enabled` (`true`),
  0044 `copies` (`"1"`). Колонки в 0043 на `marking_codes` все `nullable=True` (заполняются
  бэкфиллом/рантаймом) — падения на проде не будет.
  Исключение — см. HIGH-находку по `is_default` (default есть, но синтаксически неверный для PG).
- **Enum-типы:** PostgreSQL ENUM не создаются (статусы/типы хранятся как `String`), поэтому
  проблемы «enum не дропается в downgrade» здесь нет.
- **Согласованность с моделями SQLAlchemy:** `marking_pools` (модель marking_code.py:72-102),
  `marking_pool_products` (105-133, UNIQUE `uq_marking_pool_products_pool_product` совпадает),
  `marking_code.pool_id` (185-190, ondelete SET NULL совпадает),
  `forecast_days_threshold` (модель:87 ↔ миграция 0050), `print_templates.is_default`
  (модель:47 ↔ миграция 0046, кроме формата default) — типы/nullability колонок совпадают.
