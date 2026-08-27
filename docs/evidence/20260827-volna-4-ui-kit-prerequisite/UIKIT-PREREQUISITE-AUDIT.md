# UI-kit prerequisite · Wave 4 invoices

**Статус:** `UIKIT_CANDIDATE` — ждёт независимого статического принятия.

## Найденный пробел

Контракт Wave 4 требует три общих элемента, которых до prerequisite не было в
`frontend/src/ui-kit/`: подписанный checkbox с понятной недоступностью,
диалог с управлением фокусом и закрытием по Escape, и денежное поле, которое
не преобразует введённую сумму в JavaScript number.

## Добавленная общая граница

- `CheckboxInput`: label, error/helper, `aria-describedby`, loading и видимая
  причина disabled-state.
- `AppDialog`: стандартный MUI dialog, который удерживает фокус и вызывает
  `onClose` при Escape; заголовок связан через `aria-labelledby`.
- `MoneyInput`: строковая десятичная сумма, только 0–2 знака после точки;
  отрицательное значение запрещается по умолчанию. Копейки не проходят через
  float до границы API.

Ни один экран, в том числе `FfBillingScreen`, этим prerequisite не изменён.

## Проверки автора

- `npm run test:unit -- --run src/ui-kit` — 27 passed, 6 files.
- `npx tsc -b` — success.
- `npm run build` — success.
- `python3 scripts/ui/ui_guard.py` — `новых отступлений нет`.
- `git diff --check` — success; staged diff ограничен этим prerequisite и его
  нарядом.

Независимый reviewer принимает или отклоняет этот shared prerequisite до
использования Wave 4.
