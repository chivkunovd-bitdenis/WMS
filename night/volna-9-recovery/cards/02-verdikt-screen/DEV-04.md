## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`

В существующей зоне «Статус» вердикт WB теперь отображается для строк всех
вкладок, а не только «Просроченных». Локальный статус заказа больше не может
заменить блокирующий вердикт WB; причина отказа и текст «Сдача пока недоступна»
остаются в `TextCell`, без новой колонки и без заливки строки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, диагностик нет.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх нарушений в несвязанных
  файлах: `src/components/WbProductPickerDialog.tsx`,
  `src/screens/v2/FfFbsSupplyWorkspace.tsx`,
  `src/screens/v2/SellerInboundDraftScreen.tsx`. Новых нарушений в изменённом
  `FfFbsOrdersScreen.tsx` не добавлено; его показатели улучшились.
- `npm run test:unit` — красный: в окружении отсутствует команда `vitest`.
- Playwright для названных сценариев не запускался: локальная зависимость
  Playwright в этом окружении недоступна.

## Не реализовано

- Находки 1–5 из `REVIEW.md` относятся к backend или
  `FfFbsSupplyWorkspace.tsx`, которые не входят в разрешённые файлы этого
  атома; их исправление оставлено соответствующим карточкам.
- Полное исправление находки 6 для строк поставок невозможно в рамках
  разрешённых файлов: worklist поставок не содержит заказных WB-вердиктов, а
  изменение API-типа или `FfFbsSupplyWorkspace.tsx` выходит за границы атома.
