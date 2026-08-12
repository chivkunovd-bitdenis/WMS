# Манифест продуктового ревью WMS

## Что проверяется

Это независимое read-only ревью продукта глазами реального оператора склада и селлера. Область охватывает оба веб-портала, роли, все фактические маршруты, мобильный ТСД-клиент, а также сквозные процессы приёмки, размещения, остатков, перемещений, упаковки, маркировки, отгрузки на маркетплейс, FBS/FBW, биллинга, настроек и фоновых статусов.

Ревью не меняет приложение. Локальный код читается на runtime-базе `a39530c5137deb31e189c2136b613d01093af87b`; два последующих commit в ветке содержат только регламент ревью. Mobile рассматривается отдельно на заявленном HEAD `09aa479fd8e311a8155c92074ab2f4a6ec843da4` с обязательной оговоркой о наличии пользовательского dirty worktree.

## Источники и порядок доказательств

1. Полностью прочитаны корневой `AGENTS.md`, четыре регламента `docs/reviews/system-wide/*.md`, действующие MVP/process/scenario/test-case/UI документы и утверждённые FBS-документы.
2. Статический inventory маршрутов и действий получен из runtime-базы, но сам по себе не засчитывает экран как пройденный.
3. Runtime и API проверяются только на staging. Production и локальный functional runtime не используются.
4. Визуальный проход выполняется в реальном Browser оркестратором по независимому чек-листу продуктового агента. Каждый переданный screenshot продуктовый агент лично открывает через `view_image` и выносит собственное заключение. Поэтому в реестре разделены `interaction executor` и `visual adjudicator`.
5. Экран без лично просмотренного screenshot получает `NOT_RUN`, даже если его JSX, DOM, Storybook или API изучены.

## Gate развернутой версии

Staging отвечает на frontend, `/api/health` и OpenAPI. Railway deployment metadata доказывает развернутую revision `44fe72e` для доступного web/API deployment. Это не эталон ревью `a39530c`: runtime-наблюдения относятся только к staging revision `44fe72e`, а static findings — только к `a39530c`, пока они отдельно не воспроизведены в Browser.

Gate остаётся частичным: отдельный worker deployment в доступном staging scope отсутствует, а текущая schema revision не опубликована напрямую и может быть лишь выведена косвенно. Поэтому отчёт не заявляет полного frontend/API/worker/schema alignment и явно маркирует static-only candidates.

## Безопасность данных

Разрешённые staging credentials применяются только для входа и нигде не публикуются. Секретные значения, cookies, Authorization headers, коды маркировки и формы credentials не попадают в артефакты. Мутации допускаются только на выделенных synthetic test objects с доказанным cleanup/recovery; иначе сценарий получает `BLOCKED_SHARED_DATA`.

Offline-анализ мобильного signing artifact ограничен Git/FS metadata. Ключ не используется, не экспортируется и не исследуется как credential.

## Артефакты

- `01_BROWSER_EXECUTION_CHECKLIST_RU.md` — порядок реального Browser-прохода;
- `02_ROLE_PROCESS_MAP_RU.md` — роли и физические процессы;
- `03_ROUTE_ACTION_INVENTORY_RU.md` — маршруты и действия каждого экрана;
- `04_SCENARIO_MATRIX_RU.md` — normal/empty/error/retry/reload/partial coverage;
- `05_SCREENSHOT_MANIFEST_RU.md` — снимки, личный просмотр и verdict;
- `06_FINDINGS_REGISTER_RU.md` — подтверждённые дефекты, кандидаты и ограничения;
- `07_FINAL_PRODUCT_REVIEW_RU.md` — итоговый вывод после завершения evidence-пакета.

## Статусы

- `PASS` — действие реально выполнено, результат и reload доказаны;
- `PASS_EMPTY` — пустое состояние реально показано и даёт понятный смысл/следующий шаг;
- `FAIL` — воспроизводимый продуктовый дефект;
- `NOT_RUN` — нет реального экранного доказательства;
- `BLOCKED_AUTH_ROLE` — нет разрешённой credential нужной роли;
- `BLOCKED_SHARED_DATA` — небезопасно менять общий staging object;
- `BLOCKED_NO_FAULT_FIXTURE` — нет безопасного способа вызвать failure;
- `RETEST_VIEWPORT` — контент виден, но размер/масштаб evidence не позволяет судить о layout.
