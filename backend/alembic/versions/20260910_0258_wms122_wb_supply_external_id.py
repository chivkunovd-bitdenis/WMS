"""WMS-122: заполнить external_supply_id для WB-поставок и разобрать дубли.

Revision ID: 20260910_0258
Revises: 20260908_0257
Create Date: 2026-09-10

История задачи и почему так, а не «просто добавить unique».

Уникальное ограничение на таблице `fbs_supplies` уже есть — тройка
(seller_id, marketplace, external_supply_id), заведённая в 20260825_0102.
На WB-путях (импорт заказов из кабинета, `create_supply_from_orders` и
legacy WMS-создание) поле `external_supply_id` оставалось NULL, а
`wb_supply_id` — колонка рядом — заполнялось реальным WB-номером.
Postgres считает NULLы разными значениями в уникальных ограничениях, и
двух конкурентных импортов, попавших в тот же WB-номер, ограничение
не мешало. Плюс к этому обычный `SELECT ... WHERE wb_supply_id=?`
между сессиями не даёт защиты от гонки. 04.09.2026 на боевой базе так
и оказалось: восемь пар пустых черновиков под одинаковыми WB-номерами
поставок; тот же кабинет WB был подсоединён к двум локальным продавцам,
поэтому импорт положил один и тот же номер под каждым.

Правило владельца — не заводить журнал/счётчик/новую таблицу, если
задача решается имеющейся арифметикой. Здесь так и есть: колонка
`external_supply_id` уже задумывалась как стабильный внешний
идентификатор поставки, а Ozon-путь уже её заполняет `carriage_id`
после отгрузки. Поэтому:

1. Проставляем `external_supply_id = wb_supply_id` всем WB-строкам,
   у которых WB-номер валиден (не «PENDING-…», не пустой) и внешний
   идентификатор пуст. Это одна и та же величина в разных колонках —
   ровно тот случай, когда «один источник, а не два счётчика», о котором
   ругается CLAUDE.md.
2. Разбираем существующие дубли: для каждой тройки
   (seller_id, marketplace, external_supply_id) на WB, где вылезло больше
   одной строки, оставляем канонической самую старую по `created_at`.
   Проигравшим сбрасываем `external_supply_id` в NULL и в поле `name`
   дописываем префикс `[DUPLICATE→<uuid канонической>]`. Никакие
   служебные таблицы и колонки не заводятся; ряд остаётся в базе для
   аудита, но перестаёт конкурировать с канонической записью.
   Идентификатор строки в имени сохраняется потому, что модель уже
   разрешает произвольный текст в `name` (String(255)); писать в новое
   поле было бы той самой лишней сущностью.
3. Меняем уникальное ограничение так, чтобы оно распространялось только
   на непустые `external_supply_id`. В Postgres это делается через
   `CREATE UNIQUE INDEX ... WHERE external_supply_id IS NOT NULL`.
   NULLы (Ozon до отгрузки, некорректные WB-записи-инвалиды) остаются
   уникальными по-своему, а любая пара с одинаковым непустым внешним
   идентификатором — уже нет.

При даунгрейде убираем частичный индекс и возвращаем прежнее
ограничение вида «UNIQUE (seller_id, marketplace, external_supply_id)».
Восстанавливать заполненность/дубликатность обратно не пытаемся —
делать это молча значило бы возвращать данные, которые сознательно
разобрали.

Локальные тесты крутятся на SQLite (см. conftest.py). SQLite не умеет
частичный индекс синтаксисом Postgres 1-в-1: там используется тот же
`CREATE UNIQUE INDEX ... WHERE ...`, что в 3.30+ работает. Для
совместимости пишем обычный `op.create_index` с параметром
`postgresql_where` — Alembic сгенерирует правильную ветку под каждый
диалект (`sqlite_where` там же).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0258"
down_revision: str | Sequence[str] | None = "20260908_0257"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "fbs_supplies"
OLD_UNIQUE_NAME = "uq_fbs_supplies_seller_marketplace_external_supply"
NEW_INDEX_NAME = "uq_fbs_supplies_seller_marketplace_external_supply_notnull"


logger = logging.getLogger("alembic.wms122")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Разберём уже существующие дубли по WB-номеру ДО того, как что-то
    # заполним в external_supply_id. Иначе шаг backfill сам ткнётся в
    # существующее UNIQUE(seller_id, marketplace, external_supply_id) и
    # откатит транзакцию: постгрес считает NULLы уникальными, а два одинаковых
    # непустых значения — нет. То есть до дедупа он был инертен, но после
    # backfill'а без дедупа он бы включился и упал.
    duplicate_rows = bind.execute(
        sa.text(
            """
            SELECT seller_id, marketplace, wb_supply_id
              FROM fbs_supplies
             WHERE marketplace = 'wb'
               AND wb_supply_id IS NOT NULL
               AND wb_supply_id NOT LIKE 'PENDING-%'
               AND wb_supply_id <> ''
             GROUP BY seller_id, marketplace, wb_supply_id
             HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    total_losers = 0
    seller_counts: dict[str, int] = defaultdict(int)
    loser_ids: set[str] = set()
    for seller_id, marketplace, wb_supply_id in duplicate_rows:
        rows = bind.execute(
            sa.text(
                """
                SELECT id, name, created_at
                  FROM fbs_supplies
                 WHERE seller_id = :seller_id
                   AND marketplace = :marketplace
                   AND wb_supply_id = :wb_supply_id
                 ORDER BY created_at ASC, id ASC
                """
            ),
            {
                "seller_id": seller_id,
                "marketplace": marketplace,
                "wb_supply_id": wb_supply_id,
            },
        ).fetchall()
        if len(rows) <= 1:
            continue
        winner_id = rows[0][0]
        losers = rows[1:]
        for loser_id, loser_name, _created_at in losers:
            new_name = f"[DUPLICATE→{winner_id}] {loser_name or ''}".strip()
            # 255 — предел колонки name (см. models/fbs_supply.py:64).
            if len(new_name) > 255:
                new_name = new_name[:255]
            # external_supply_id у проигравших мы бы поставили в NULL,
            # но он и так NULL: backfill ещё не выполнялся. Оставляем NULL
            # и просто помечаем ряд, чтобы дальше backfill его пропустил.
            bind.execute(
                sa.text(
                    """
                    UPDATE fbs_supplies
                       SET name = :new_name
                     WHERE id = :loser_id
                    """
                ),
                {"new_name": new_name, "loser_id": loser_id},
            )
            loser_ids.add(str(loser_id))
            total_losers += 1
            seller_counts[str(seller_id)] += 1
            logger.warning(
                "WMS-122 duplicate quarantined: seller=%s marketplace=%s "
                "wb_supply_id=%s loser_id=%s winner_id=%s",
                seller_id,
                marketplace,
                wb_supply_id,
                loser_id,
                winner_id,
            )

    if total_losers:
        logger.warning(
            "WMS-122 quarantine summary: %d duplicate rows across %d sellers",
            total_losers,
            len(seller_counts),
        )

    # 2. Backfill external_supply_id для WB-строк.
    # PENDING-<uuid> — это плейсхолдер `create_supply_from_orders` на время
    # ожидания ответа WB. Такой ряд не является идентичностью поставки у WB,
    # поэтому в `external_supply_id` его не тянем.
    # Проигравшие карантинные ряды из шага 1 пропускаем: у них должна остаться
    # только пометка в имени, external_supply_id остаётся NULL, чтобы новый
    # частичный индекс их не задел.
    if loser_ids:
        bind.execute(
            sa.text(
                """
                UPDATE fbs_supplies
                   SET external_supply_id = wb_supply_id
                 WHERE marketplace = 'wb'
                   AND external_supply_id IS NULL
                   AND wb_supply_id IS NOT NULL
                   AND wb_supply_id NOT LIKE 'PENDING-%'
                   AND wb_supply_id <> ''
                   AND id NOT IN :loser_ids
                """
            ).bindparams(sa.bindparam("loser_ids", expanding=True)),
            {"loser_ids": list(loser_ids)},
        )
    else:
        bind.execute(
            sa.text(
                """
                UPDATE fbs_supplies
                   SET external_supply_id = wb_supply_id
                 WHERE marketplace = 'wb'
                   AND external_supply_id IS NULL
                   AND wb_supply_id IS NOT NULL
                   AND wb_supply_id NOT LIKE 'PENDING-%'
                   AND wb_supply_id <> ''
                """
            )
        )

    # 3. Меняем уникальное ограничение: с обычного UNIQUE
    # (в котором NULLы уникальны и конкуренция не ловилась) — на
    # частичный уникальный индекс, покрывающий только заполненные значения.
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.drop_constraint(OLD_UNIQUE_NAME, TABLE, type_="unique")
        op.create_index(
            NEW_INDEX_NAME,
            TABLE,
            ["seller_id", "marketplace", "external_supply_id"],
            unique=True,
            postgresql_where=sa.text("external_supply_id IS NOT NULL"),
        )
    else:
        # SQLite (тесты) поддерживает частичный UNIQUE INDEX начиная с 3.8.
        # batch_alter_table нужен, чтобы дропнуть unique-constraint, который
        # SQLite хранит внутри CREATE TABLE.
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_constraint(OLD_UNIQUE_NAME, type_="unique")
        op.create_index(
            NEW_INDEX_NAME,
            TABLE,
            ["seller_id", "marketplace", "external_supply_id"],
            unique=True,
            sqlite_where=sa.text("external_supply_id IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.drop_index(NEW_INDEX_NAME, table_name=TABLE)
        op.create_unique_constraint(
            OLD_UNIQUE_NAME,
            TABLE,
            ["seller_id", "marketplace", "external_supply_id"],
        )
    else:
        op.drop_index(NEW_INDEX_NAME, table_name=TABLE)
        with op.batch_alter_table(TABLE) as batch:
            batch.create_unique_constraint(
                OLD_UNIQUE_NAME,
                ["seller_id", "marketplace", "external_supply_id"],
            )
