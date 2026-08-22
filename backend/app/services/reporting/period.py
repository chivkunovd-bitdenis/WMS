"""Расчёт периодов и сравнений для отчётов.

Один фиксированный способ интерпретации даты начала и конца периода, чтобы
для каждого отчёта не приходилось шаманить с "сегодня в 00:00" vs
"вчера в 23:59:59".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class PeriodPreset(str, Enum):
    """Пресеты быстрого выбора периода."""
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    CUSTOM = "custom"


class CompareMode(str, Enum):
    """Режимы сравнения периодов."""
    NONE = "none"
    PREVIOUS = "previous"
    YEAR_AGO = "year_ago"
    CUSTOM = "custom"


@dataclass
class DateRange:
    """Диапазон дат: начало и конец включительно."""
    start: date
    end: date

    def days(self) -> int:
        """Количество дней в диапазоне (включительно)."""
        return (self.end - self.start).days + 1

    def to_datetimes_utc(self) -> tuple[datetime, datetime]:
        """Преобразовать в UTC datetimes.

        start -> 00:00:00 UTC, end -> 23:59:59.999999 UTC.
        """
        start_dt = datetime.combine(self.start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(self.end, datetime.max.time(), tzinfo=timezone.utc)
        return start_dt, end_dt


@dataclass
class ReportingPeriod:
    """Полный период отчёта с возможностью сравнения.

    Атрибуты:
        current: текущий диапазон
        compare_mode: режим сравнения (none, previous, year_ago, custom)
        compare: сравниваемый диапазон (если compare_mode != none)
        month_to_date: накопительно с начала месяца
        year_to_date: накопительно с начала года
    """
    current: DateRange
    compare_mode: CompareMode
    compare: DateRange | None = None
    month_to_date: DateRange | None = None
    year_to_date: DateRange | None = None

    @classmethod
    def from_preset(
        cls,
        preset: PeriodPreset | str,
        reference_date: date | None = None,
        compare_mode: CompareMode | str = CompareMode.PREVIOUS,
    ) -> ReportingPeriod:
        """Создать период из пресета.

        Args:
            preset: один из PeriodPreset
            reference_date: дата отсчёта (по умолчанию сегодня)
            compare_mode: режим сравнения

        Returns:
            Период с текущим диапазоном и сравнением (если запрошено)
        """
        if reference_date is None:
            reference_date = date.today()

        if isinstance(preset, str):
            preset = PeriodPreset(preset)
        if isinstance(compare_mode, str):
            compare_mode = CompareMode(compare_mode)

        # Текущий диапазон из пресета
        current = cls._range_from_preset(preset, reference_date)

        # Сравниваемый диапазон
        compare_range = None
        if compare_mode != CompareMode.NONE:
            compare_range = cls._compare_range(current, compare_mode)

        # Накопительно с начала месяца/года
        month_to_date = DateRange(
            start=date(reference_date.year, reference_date.month, 1),
            end=reference_date,
        )
        year_to_date = DateRange(
            start=date(reference_date.year, 1, 1),
            end=reference_date,
        )

        return cls(
            current=current,
            compare_mode=compare_mode,
            compare=compare_range,
            month_to_date=month_to_date,
            year_to_date=year_to_date,
        )

    @classmethod
    def from_dates(
        cls,
        start: date,
        end: date,
        compare_mode: CompareMode | str = CompareMode.PREVIOUS,
        reference_date: date | None = None,
    ) -> ReportingPeriod:
        """Создать период из явных дат.

        Args:
            start: дата начала (включительно)
            end: дата конца (включительно)
            compare_mode: режим сравнения
            reference_date: дата отсчёта для MTD/YTD (по умолчанию сегодня)

        Returns:
            Период с текущим диапазоном и сравнением (если запрошено)
        """
        if reference_date is None:
            reference_date = date.today()

        if isinstance(compare_mode, str):
            compare_mode = CompareMode(compare_mode)

        current = DateRange(start=start, end=end)

        # Сравниваемый диапазон
        compare_range = None
        if compare_mode != CompareMode.NONE:
            compare_range = cls._compare_range(current, compare_mode)

        # Накопительно
        month_to_date = DateRange(
            start=date(reference_date.year, reference_date.month, 1),
            end=reference_date,
        )
        year_to_date = DateRange(
            start=date(reference_date.year, 1, 1),
            end=reference_date,
        )

        return cls(
            current=current,
            compare_mode=compare_mode,
            compare=compare_range,
            month_to_date=month_to_date,
            year_to_date=year_to_date,
        )

    @staticmethod
    def _range_from_preset(preset: PeriodPreset, reference: date) -> DateRange:
        """Расчитать DateRange из пресета."""
        if preset == PeriodPreset.TODAY:
            return DateRange(start=reference, end=reference)

        if preset == PeriodPreset.WEEK:
            # Неделя: понедельник (weekday=0) до воскресенья (weekday=6)
            days_since_monday = reference.weekday()
            week_start = reference - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            return DateRange(start=week_start, end=week_end)

        if preset == PeriodPreset.MONTH:
            # Месяц: 1-го до последнего дня
            month_start = date(reference.year, reference.month, 1)
            if reference.month == 12:
                month_end = date(reference.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(reference.year, reference.month + 1, 1) - timedelta(days=1)
            return DateRange(start=month_start, end=month_end)

        if preset == PeriodPreset.QUARTER:
            # Квартал: Q1=1-3, Q2=4-6, Q3=7-9, Q4=10-12
            quarter = (reference.month - 1) // 3 + 1
            q_start_month = (quarter - 1) * 3 + 1
            q_start = date(reference.year, q_start_month, 1)
            if quarter == 4:
                q_end = date(reference.year + 1, 1, 1) - timedelta(days=1)
            else:
                q_end = date(reference.year, q_start_month + 3, 1) - timedelta(days=1)
            return DateRange(start=q_start, end=q_end)

        if preset == PeriodPreset.YEAR:
            # Год: 1 января до 31 декабря
            year_start = date(reference.year, 1, 1)
            year_end = date(reference.year, 12, 31)
            return DateRange(start=year_start, end=year_end)

        raise ValueError(f"Неизвестный пресет: {preset}")

    @staticmethod
    def _compare_range(current: DateRange, mode: CompareMode) -> DateRange:
        """Расчитать диапазон для сравнения."""
        duration = current.days()

        if mode == CompareMode.PREVIOUS:
            # Предыдущий период такой же длины
            prev_end = current.start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=duration - 1)
            return DateRange(start=prev_start, end=prev_end)

        if mode == CompareMode.YEAR_AGO:
            # Год назад
            year_ago_start = current.start - timedelta(days=365)
            year_ago_end = current.end - timedelta(days=365)
            return DateRange(start=year_ago_start, end=year_ago_end)

        raise ValueError(f"Неизвестный режим сравнения: {mode}")
