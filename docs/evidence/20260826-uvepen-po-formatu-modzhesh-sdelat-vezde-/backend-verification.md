# Доказательства · WB-совместимые ШК коробов

Дата финальной проверки: 27.08.2026.

## Проверка результата

Целевой набор охватывает общий генератор `WHB`/`INB`, API-ответы, уникальность,
старые сохранённые форматы и реальную печать Code 128 на 58x40 мм при 203 dpi.
FBS строго исключён из изменения.

```text
23 passed in 0.57s
```

Ruff по всем изменённым Python-файлам:

```text
All checks passed!
```

Mypy для нового общего модуля и полный mypy:

```text
Success: no issues found in 1 source file
Success: no issues found in 307 source files
```

Примеры реально сгенерированных значений:

```text
INB INB-CP2AXF4WG3JQSZ 18 True
```

Проверка отсутствия изменений FBS относительно `origin/etalon`:

```text
git diff origin/etalon -- \
  backend/app/services/fbs_packing_box_service.py \
  backend/tests/test_fbs_packing_box.py
# пустой вывод
```

Получение и печать официальных QR грузомест и QR поставки FBS не изменялись.

## Физическая читаемость

Первый вариант на 30 символов остановлен review: он формально разрешён WB, но
слишком плотный для Code 128 на стандартной этикетке. Финальный вариант содержит
14 Crockford Base32 символов после префикса, всего 18 символов и 70 случайных битов.

Playwright берёт настоящий `internalBox` renderer и печатный HTML, растрирует
58x40 мм при `203/96` device scale и декодирует результат ZXing:

```text
TC-NEW-INTERNAL-LABEL-01: actual batch print HTML decoded at 58x40/203 dpi
Single print action: exercised by full E2E and uses the same production internalBox helper
TC-NEW-INTERNAL-LABEL-02: 4 worst patterns + 256 deterministic codes decoded
negative canary WHB-A8SB4F33NCXJ506A: decode rejected
2 passed in 32.3s
```

## Полные гейты после rework

```text
Ruff: All checks passed!
Mypy: Success: no issues found in 307 source files
Pytest: 1054 passed, 5 skipped in 732.94s (0:12:12)
Frontend production build: passed
Playwright: 202 passed, 7 skipped in 14.4m
```

## Живой браузер

- `inbound-box-live.png` — один документ одновременно показывает старый сохранённый
  30-символьный короб и новый `INB-CP2AXF4WG3JQSZ`; оба значения читаются полностью.
- `inbound-box-label-live.png` — диалог печати нового короба открывается с размером
  по умолчанию 58x40 мм.

После двух неуспешных попыток подключения свежий независимый судья прошёл сценарий
в живом Browser при 1280x720 и выдал `PRODUCT_BROWSER_APPROVED`: новый и старый
коды видны полностью, печать нового короба открывается на 58x40 мм, горизонтального
переполнения нет, FBS-вкладки работают без ошибок и предупреждений в консоли.

## Повторное code review · 27.08.2026

Сильная изолированная модель нашла и после rework перепроверила два тестовых дефекта:

- e2e ожидал старый `INB-` + 12 hex-символов;
- mocked lookup не доказывал сканирование старых сохранённых ШК.

После финального rework regex точно проверяет 70-битный суффикс
`[0-9A-HJKMNP-TV-Z]{14}`, а старые `WHB-ABCDEF123456` и
`INB-ABCDEF123456` реально сохраняются в SQLite и проходят production
`attach_existing_box_by_barcode`.

```text
23 passed in 0.57s
Ruff: All checks passed!
Final rereview: CODE_REVIEW_PASSED, no P0/P1/P2 findings
```
