# Повторное code review · 01-catalog-box-lookup

ВЕРДИКТ: НАХОДКИ 1

Вердикт: **CHANGES_REQUESTED**.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts:561` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts:580` — ремонтный сценарий `S-16-TC-014` не доказывает восстановление готовности сканера и не ловит поздний перехват выделения первым одинаковым запросом. До обоих ответов сам `search.fill(barcode)` уже фокусирует поле и оставляет каретку в конце, поэтому проверки фокуса и позиции на строках 561–565 останутся зелёными, даже если убрать продуктовые `focus()`/`select()` после успешного поиска; после освобождения позднего первого ответа тест проверяет только фокус, но не выделение и не начатый следующий ввод. Конкретный пропущенный сценарий: оператор дважды отправляет один ШК, после второго ответа начинает вводить следующий код, а запоздалый первый ответ ошибочно выделяет новое значение; следующий пакет символов заменит уже набранный код, но текущий тест всё равно пройдёт. Цена — прежняя находка № 3 и назначенный кейс `S-16-TC-014` остаются без пользовательской защиты от потери поточного ввода.

## Проверено и нормально

- Предыдущий `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/REVIEW.md` использован как замороженный чек-лист; целиком прочитан ремонтный продуктовый diff `b19fe48d..f2d3b4ab` и назначенные `S-16-TC-001`–`S-16-TC-017` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/tests/cases/S-16.md`.
- Прежние находки № 1, № 2, № 4 и № 5 закрыты по существу: повтор списка ждёт успешный `GET` и скрытие скелетона; поздний отказ выполняется через сетевой `route.abort`; состояние полной раскладки проверяется при втором неразложенном коробе; заголовок приёмки утверждается с единственным знаком `№`.
- Ремонтный продуктовый diff меняет только `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`, который входит в прямо переданную границу карточки. Изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/` учтены как стадийные артефакты и не объявлены выходом за границы.
- Ремонт не добавляет новых операторских блокировок, записей в складские данные или изменений формата API; `git diff --check` для ремонтного диапазона проходит.

## Ограничение проверки

Целевой запуск трёх ремонтных Playwright-сценариев в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` не начался: локального исполняемого Playwright нет, а попытка разрешить пакет завершилась сетевой ошибкой `ENOTFOUND registry.npmjs.org`. Это ограничение окружения не считается отдельной находкой; в артефактах разработчика зафиксирован более ранний успешный целевой запуск.
