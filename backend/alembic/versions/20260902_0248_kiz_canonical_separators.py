"""Привести хранимые ЧЗ-коды к каноническому виду разделителей.

Разделители GS — это разметка, а не данные. Один и тот же физический код склад
сохранял и с ними, и без: на бою из 42 привязанных к заказам кодов 16 лежали в
старом виде, в пуле — 51 из 2886. Пока представления разные, уникальные индексы
по сырой строке не мешают привязать один физический КИЗ дважды: две записи с
одинаковым содержимым и разной расстановкой разделителей для базы — разные
строки.

Миграция приводит старые записи к тому же виду, в котором сохраняются новые.
После неё существующие индексы (uq_marking_codes_tenant_cis и
uq_fbs_order_markings_tenant_kind_value) снова дают настоящую гарантию, и
отдельный функциональный индекс не нужен.

⛔ Трогаем только записи, где приведение НЕ меняет содержимое и где прочтение
однозначно. Код, который читается двумя законными способами (серийник сам
оканчивается на «91» плюс четыре символа), пропускаем: подвинуть у него границы
полей — значит отправить в WB другой логический код при тех же байтах. На
боевой базе таких ноль, но правило важнее сегодняшних данных.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "20260902_0248"
down_revision = "20260902_0247"
branch_labels = None
depends_on = None

_GS = "\x1d"

Normalizer = Callable[[str], tuple[str, Any]]
Alternative = Callable[[str], str | None]


def _canonical(value: str, normalize: Normalizer, alternative: Alternative) -> str | None:
    """Канонический вид или None, если трогать нельзя."""
    if not value:
        return None
    try:
        normalized, _hints = normalize(value)
    except Exception:
        return None
    if normalized == value:
        return None
    if normalized.replace(_GS, "") != value.replace(_GS, ""):
        return None
    if alternative(value) is not None:
        return None
    return normalized


def _rewrite(
    table: str,
    id_column: str,
    value_column: str,
    normalize: Normalizer,
    alternative: Alternative,
    where: str = "",
) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT {id_column}, {value_column} FROM {table} {where}")
    ).fetchall()
    for row_id, value in rows:
        canonical = _canonical(value or "", normalize, alternative)
        if canonical is None:
            continue
        # Место может быть уже занято каноническим близнецом: тогда переписывать
        # нельзя — уникальный индекс не пустит, а терять запись мы не имеем
        # права. Такие случаи разбираются руками; на бою их нет.
        taken = bind.execute(
            sa.text(
                f"SELECT 1 FROM {table} "
                f"WHERE {value_column} = :v AND {id_column} <> :id LIMIT 1"
            ),
            {"v": canonical, "id": row_id},
        ).first()
        if taken is not None:
            continue
        bind.execute(
            sa.text(f"UPDATE {table} SET {value_column} = :v WHERE {id_column} = :id"),
            {"v": canonical, "id": row_id},
        )


def upgrade() -> None:
    # Разбор кода живёт в сервисе, и повторять его здесь копией — верный способ
    # получить две расходящиеся правды. Но жёсткая зависимость миграции от кода
    # приложения тоже опасна: сервис через полгода переедет, а миграция обязана
    # накатываться вечно. Поэтому импорт мягкий: не нашёлся — схему не ломаем,
    # данные оставляем как есть и говорим об этом вслух.
    try:
        from app.services.fbs_kiz_service import (
            alternative_cis_reading,
            normalize_scanned_cis,
        )
    except Exception:
        print(
            "20260902_0248: разбор ЧЗ недоступен — приведение разделителей "
            "пропущено, схема не тронута"
        )
        return

    _rewrite(
        "marking_codes",
        "id",
        "cis_code",
        normalize_scanned_cis,
        alternative_cis_reading,
    )
    _rewrite(
        "fbs_order_markings",
        "id",
        "value",
        normalize_scanned_cis,
        alternative_cis_reading,
        where="WHERE kind = 'sgtin'",
    )


def downgrade() -> None:
    # Обратного хода нет и не нужно: канонический вид — то же значение с
    # правильной разметкой, откатывать его к «как повезло» бессмысленно.
    pass
