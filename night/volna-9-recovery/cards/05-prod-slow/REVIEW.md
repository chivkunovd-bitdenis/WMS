# Ревью · 05-prod-slow · проверка ремонта

Вердикт: CHANGES_REQUESTED.

ВЕРДИКТ: НАХОДКИ 1

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts:135` — ремонт пункта 1 предыдущего ревью убрал единственную проверку закрытия клавишей Esc: теперь и первое закрытие на строке 135, и повторное на строке 145 выполняются кликом по backdrop. Это расходится с назначенным `S-03-TC-018`, где сначала требуется Esc, а после повторного открытия — клик по затемнённой области. Сценарий поломки: обработка Esc в `Dialog` перестаёт закрывать состояние `preparing`, при этом backdrop продолжает работать — тест остаётся зелёным. Цена — один из двух обязательных штатных способов выхода из фоновой подготовки не защищён от регрессии; для закрытия ремонта нужно сохранить новые проверки отсутствия действий, вернуть Esc для первого закрытия и оставить backdrop для второго.

## Проверено и нормально

- Замороженный чек-лист предыдущего `REVIEW.md` проверен целиком. Пункт 1 закрыт в части запрета кнопки «Закрыть» и любых интерактивных действий внутри `marking-print-preparing`, а клик по backdrop теперь действительно присутствует; замечание выше относится только к потерянному покрытию Esc в ремонтном diff.
- Пункт 2 закрыт: Git blob `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/inventory.generated.ts` в `HEAD` совпадает с базовым `d62f9afb`, итогового продуктового diff по глобальному UI-инвентарю нет.
- Продуктовый diff после предыдущего вердикта прочитан полностью: вне `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts` изменены только стадийные артефакты ночного конвейера. Новых операторских блокировок, серверных правил, изменений данных или формата API ремонт не добавляет.
- `npx eslint tests-e2e/ff-marking-print-constructor.spec.ts`, `npx tsc --noEmit -p tsconfig.app.json`, адресный Playwright `--list` и `git diff --check 8bdf373c..HEAD` прошли. Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
