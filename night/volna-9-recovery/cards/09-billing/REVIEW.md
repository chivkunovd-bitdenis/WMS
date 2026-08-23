# 09-billing — повторное содержательное ревью ремонта

ВЕРДИКТ: НАХОДКИ 3

Вердикт: **CHANGES_REQUESTED**.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py:49-102` — тест модели не переведён на утверждённый контракт целых копеек: он по-прежнему создаёт `rate` и `amount` как `Decimal("10.00")` и ожидает дробный результат, хотя `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py:173-174` теперь объявляет оба поля целочисленными. Конкретный сценарий уже воспроизводится: запуск переданных billing-наборов падает на первом `session.commit()` с `sqlite3.ProgrammingError: type 'decimal.Decimal' is not supported`, поэтому проверки дубля исходного события и второго сторно вообще не выполняются. Цена: обязательный backend-набор красный (`1 failed, 39 passed`), а защита неизменяемого финансового журнала остаётся без работающего модельного теста. Это пропуск первого ревью, заявленный по разрешённому исключению для фактически непроходящей сборки/тестового набора.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py:62-78`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py:137,161-174,202-208`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py:104-105,173-174`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py:51-58,100-117` — ремонт переводит весь разрешённый API-диапазон в копейки, но хранит ставку и сумму в PostgreSQL `INTEGER` с пределом `2 147 483 647`. Вход `21474836.48` проходит текущий `TariffCreateBody` и превращается в `2147483648` копеек; PostgreSQL отвергнет запись до ответа `201`. Та же граница ломается при дооценке гораздо меньшей ставки, умноженной на большое фактическое количество. Цена: формально допустимый тариф завершается необработанной серверной ошибкой, ранее неоценённая работа остаётся без цены и месячный счёт продолжает блокироваться; SQLite-тесты дефект не показывают из-за другого диапазона целого типа.

3. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py:214-261`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts:19-113`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/tests/cases/S-31.md:171-182`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/CASES.md:24-26` — новые проверки не сопоставлены с назначенными кейсами: backend ссылается на отсутствующие `S-31-TC-017` и `S-31-TC-018`, денежный E2E — на незарегистрированный `TC-NEW-017`, а оба профильных E2E помечены `S-31-TC-013`, который по базе проверяет незакрытое хранение, а не реквизиты. Сценарий поломки: отчёт по кейсам засчитывает профильные переходы как покрытие storage-блокировки и не может найти спецификацию для денежных и профильных тестов. Цена: тесты проверяют полезное поведение, но машинная и ручная трассировка даёт ложный результат о том, какой контракт ими защищён.

## Проверено и нормально

- Замороженный чек-лист предыдущего `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/REVIEW.md` проверен по ремонтному diff `8b3722e1..0f7c7346`: все шесть прежних находок закрыты по существу — рублёвый ввод и дооценка переводятся в копейки, экран и печать показывают деньги один раз, обе профильные причины ведут к нужным полям, описание блокировок разделено, месяцы берутся по Москве.
- Ремонтные продуктовые файлы сверены с переданными границами; файлы `night/`, база кейсов и обязательное шестипольное описание блокировок считались стадийными/ролевыми артефактами и не объявлялись выходом за экран.
- Tenant-изоляция, серверные причины `missing_ff_profile`/`missing_seller_profile`, нулевая ставка, дооценка `document`/`item`/`liter_day`, отрицательное сторно и сохранение раздельных месяцев вкладок проверены по коду и адресным тестам; новых списаний, резервов или уходов остатков в минус ремонт не добавляет.
- `ruff` и `mypy` по ремонтным backend-файлам пройдены; frontend production build и 16 адресных unit-тестов пройдены. Playwright не дошёл до тестов из-за запрета окружения на bind `127.0.0.1:18000` (`operation not permitted`), а не из-за тестового утверждения.

## Технические проверки

- `git diff --check 8b3722e1..0f7c7346` — замечаний нет.
- `pytest -q` по восьми billing-наборам — `1 failed, 39 passed`; падение полностью относится к находке 1.
- `npx tsc --noEmit -p tsconfig.app.json` и `npm run build` — пройдены.
- `npx vitest run src/ui-kit/Cells.test.ts src/screens/ff/FfBillingScreen.test.ts src/screens/ff/FfSettingsScreen.test.ts` — `16 passed`.
- `npm run test:e2e -- billing-invoices.spec.ts` — webServer не смог открыть `127.0.0.1:18000` из-за `operation not permitted`; браузерные утверждения не выполнялись.
