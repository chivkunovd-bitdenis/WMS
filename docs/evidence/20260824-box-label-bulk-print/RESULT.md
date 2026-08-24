# Доказательства · печать внутренних этикеток

- Chromium, `TC-NEW-INTERNAL-LABEL-01`: зелёный.
- Реальный HTML печати для двух коробов содержит две страницы `60 × 40 мм`,
  крупный `Code 128` шириной `100%`, оба внутренних кода и page break между
  этикетками.
- Вызван ровно один `window.print()`; iframe очищен событием `afterprint`, а не
  фиксированной задержкой.
- PNG первой фактически сформированной этикетки обратным декодером ZXing
  прочитан как исходный внутренний код короба.
- Скриншот Chromium-рендера этого же print HTML:
  [`internal-box-label-preview.png`](internal-box-label-preview.png).

Команда:

```bash
cd frontend
npm run test:e2e -- tests-e2e/ff-inbound-box-intake.spec.ts --grep TC-NEW-INTERNAL-LABEL-01
```
