# Screen Dev · 02-verdikt-screen · feature 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

Клиентский API содержит неизменяемый серверный вердикт WB. Утилита `metaStatusView`
использует только этот вердикт, выдаёт фиксированные подписи и тоны, переводит
известные причины на русский, сохраняет неизвестную причину безопасным текстом и
возвращает `disabledReason` для блокирующих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не пройден: в рабочей копии нет локального `tsc`, а сетевое получение пакета недоступно.
- `python3 scripts/ui/ui_guard.py` — не пройден: обнаружены нарушения baseline в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; файлы этой правки не затрагивались, baseline не обновлялся.
- `npm run test:unit` — не пройден: в рабочей копии отсутствует локальный `vitest`/зависимости frontend.

## Не реализовано

- Компоненты экранов не подключались: это следующий атомарный кусок контракта; текущая фича ограничена типом API и словарём отображения.
