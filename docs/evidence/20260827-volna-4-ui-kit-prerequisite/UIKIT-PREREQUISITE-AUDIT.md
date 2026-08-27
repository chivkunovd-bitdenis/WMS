# UI-kit prerequisite · Wave 4 invoices

**Статус:** `UIKIT_ACCEPTED` — см. `VERDICT.md` рядом.

Первая редакция получила `UIKIT_REWORK_REQUIRED`: тесты проверяли константы и
SSR-разметку вместо поведения. Закрыто браузерными проверками в
`frontend/tests-e2e/ui-kit-form-primitives.spec.ts`; попутно найден и удалён
мёртвый `DIALOG_ACCESSIBILITY`, который в MUI 9 не доходил до `Modal`.

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

- `npm run test:unit -- --run` — 214 passed, 35 files.
- `npx playwright test ui-kit-form-primitives` — 7 passed (живой браузер).
- `npx tsc -b` — success.
- `npm run build` — success.
- `python3 scripts/ui/ui_guard.py` — `новых отступлений нет`.
- `git diff --check` — success; staged diff ограничен этим prerequisite и его
  нарядом.

Независимый reviewer принял этот shared prerequisite: `UIKIT_ACCEPTED`.
