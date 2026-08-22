## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

В клиентский контракт добавлен безопасный серверный вердикт по умолчанию: если
живой ответ ещё не содержит `metadata.verdict`, заказ получает блокирующее
состояние `Нет ответа WB`, а не оптимистичное разрешение из локальных полей.
Ответы worklist и workspace нормализуются перед передачей в экран. Словарь
отображения сохраняет фиксированные подписи и тоны, переводит известные причины
на русский и безопасно показывает неизвестную причину как пришедший текст.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда запущена, но окружение не
  вернуло диагностический вывод или код завершения через оболочку инструмента;
  результат не удалось подтвердить как зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в
  несвязанных файлах: `src/components/WbProductPickerDialog.tsx`,
  `src/screens/v2/FfFbsSupplyWorkspace.tsx`,
  `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не изменял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Находки ревью, относящиеся к backend и экранным компонентам
  `FfFbsOrdersScreen.tsx`/`FfFbsSupplyWorkspace.tsx`, не исправлялись: они не
  входят в разрешённый атом фичи 3 и требуют отдельных карточек.
