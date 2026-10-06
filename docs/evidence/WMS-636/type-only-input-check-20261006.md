# WMS-636: тип существующего поля скана

Исходная отдельная type-only коррекция — `83393272775a5a87d6301e95c2716948022b9a6d`: одна строка `querySelector<HTMLInputElement>` в `FfFbsSupplyWorkspace.wms636.dom.test.tsx`. Никакие assertions, действия, параметры или ожидания не менялись. Устраняет фактический TS2339 из CI3 `37465305907` на общем `9922250590c527a06f37bd8122e18cec10d6d1ed`: прежний querySelector возвращал Element, у которого TypeScript не обещает focus().

Проверка проведена в собственном переиспользованном permanent worktree, ветка `codex/wms636-typecheck-validation-20261006`, дерево общего992225 с точной этой дельтой — `4d4d8a92b` (сохранённый cherry-pick833). Чужой общий кандидат не редактировался.

Полный `npx --no-install tsc --noEmit -p tsconfig.app.json` из frontend — **PASS**, exit0,14.11с. Полный `npm run build` — **PASS**, exit0,16.35с. Предупреждение о размерах крупных bundle chunks остаётся предупреждением, ошибок сборки нет. Повтор Vitest для generic type не нужен: emitted runtime JavaScript всего файла до/после побайтно совпадает.

Использован существующий node_modules из `wms672-673-analyst-20261006/frontend` через symlink, без установки новых пакетов. Package-lock совпал побайтно с общим кандидатом: SHA256 `4ec9fd6b9291d52f2c3534bc3fb4ebbfd24a9d029f3d3d01127e43404c01984c`; установленные TypeScript6.0.2,Vite8.0.8,pdf-lib1.17.1. Полный общий CI и deployment здесь не выполнялись.
