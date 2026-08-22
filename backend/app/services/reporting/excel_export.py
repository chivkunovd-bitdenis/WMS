"""Экспорт данных отчётов в XLSX и CSV.

Лимит: 25 000 строк для экспорта (жёсткий: пользователь получает либо полный файл,
либо ошибку, а не пустой документ через минуту).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


EXPORT_LIMIT = 25000


class ExportLimitExceeded(Exception):
    """Превышен лимит на число строк для экспорта."""

    def __init__(self, row_count: int):
        self.row_count = row_count
        super().__init__(
            f"Больше {EXPORT_LIMIT} строк — разбейте на несколько периодов. "
            f"Текущий отбор: {row_count} строк."
        )


def export_to_xlsx(
    rows: list[dict[str, Any]],
    columns: list[str],
    title: str = "Report",
) -> bytes:
    """Экспортировать данные в XLSX.

    Args:
        rows: список строк с данными
        columns: список ключей колонок
        title: название листа

    Returns:
        Бинарные данные XLSX файла

    Raises:
        ExportLimitExceeded: если строк больше лимита
    """
    if len(rows) > EXPORT_LIMIT:
        raise ExportLimitExceeded(len(rows))

    try:
        import pandas as pd
        import openpyxl
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        raise ImportError("openpyxl and pandas are required for Excel export")

    # Подготовить данные
    data_for_df = []
    for row in rows:
        row_data = {}
        for col in columns:
            row_data[col] = row.get(col, "")
        data_for_df.append(row_data)

    # Создать DataFrame
    df = pd.DataFrame(data_for_df)

    # Создать XLSX с форматированием
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=title, index=False)

        # Применить форматирование
        worksheet = writer.sheets[title]
        header_fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        header_font = Font(bold=True)

        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font

        # Автоширина
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except TypeError:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)
    return output.getvalue()


def export_to_csv(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> str:
    """Экспортировать данные в CSV.

    Args:
        rows: список строк с данными
        columns: список ключей колонок

    Returns:
        CSV в виде строки (UTF-8 с BOM для кириллицы)

    Raises:
        ExportLimitExceeded: если строк больше лимита
    """
    if len(rows) > EXPORT_LIMIT:
        raise ExportLimitExceeded(len(rows))

    import csv

    output = io.StringIO()
    # Добавить BOM для UTF-8 (важно для кириллицы в Excel)
    output.write("﻿")

    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for row in rows:
        row_data = {}
        for col in columns:
            row_data[col] = row.get(col, "")
        writer.writerow(row_data)

    return output.getvalue()
