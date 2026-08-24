# Доказательства · печать внутренних этикеток

- Chromium, `TC-NEW-INTERNAL-LABEL-01`: зелёный.
- Реальный HTML печати для двух коробов содержит две страницы `60 × 40 мм`,
  крупный `Code 128` шириной `100%`, оба внутренних кода и page break между
  этикетками.
- Вызван ровно один `window.print()`; iframe очищен событием `afterprint`, а не
  фиксированной задержкой.
- Вырезанный с device scale factor 4 PNG штрихкода, фактически отрисованный
  Chromium из print HTML, обратным декодером ZXing прочитан как исходный
  внутренний код короба.
- Фактический Chromium-crop штрихкода:
  [`internal-box-label-chromium-crop.png`](internal-box-label-chromium-crop.png).
- Полный Chromium-рендер той же ленты:
  [`internal-box-label-preview.png`](internal-box-label-preview.png).

Команда:

```bash
cd frontend
npm run test:e2e -- tests-e2e/ff-inbound-box-intake.spec.ts --grep TC-NEW-INTERNAL-LABEL-01
```
