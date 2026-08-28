# Ломающая проверка A-1 — ведомость хранения и общая матрица

Проверялся принятый финансовый контракт, а не то, какие private helpers сейчас
вызываются. Новые проверки принадлежат `backend/tests/test_storage_statement_matrix.py`
и `frontend/tests-e2e/storage.spec.ts`; production-код не менялся.

## Rework после code review

13. **A1-CR-001 — дробная аллокация не должна терять копейку** — слой:
    backend API + invoice integration; приоритет: P0. Цель: итог ведомости
    считается на той же seller/day границе округления, что и seller report и
    счёт. Предусловия: залогиненный admin, один seller/warehouse, два товара
    с фактическими `0.0049` литро-дня каждый и V2 seller rate 100 копеек.
    Действия: получить месячную ведомость, seller report и invoice preview по
    реальному подписанному token. Ожидаемый результат: report, invoice и
    ведомость равны 1 копейке; публичные SKU allocation в сумме дают total
    ведомости. Данные: `0.0049 + 0.0049 = 0.0098` литро-дня. Способ: pytest
    integration. Статус: автоматизирован, пройден после production rework:
    seller report, invoice preview и ведомость равны 1 копейке.

14. **A1-CR-002 — перекрёстная история A/B возвращает именно новую пару**
    — слой: backend API + tariff-matrix transaction; приоритет: P1. Цель:
    широкий post-save lookup не возвращает старые IDs. Предусловия: old common
    start B/rate 111, old seller start A/rate 222, draft на B; submit создаёт
    common start A/rate 333 и seller start B/rate 444. Действия: сохранить
    submit с revision и сверить public IDs/rates/dates и repriced draft rate.
    Ожидаемый результат: public IDs принадлежат DB-строкам 333/444, dates A/B,
    draft имеет 4.44. Данные: A = текущая московская дата, B = A+1; old V2
    timestamps записываются как UTC instants, как их пишет matrix service.
    Способ: pytest integration. Статус: автоматизирован, пройден после
    production rework с реальными UTC timestamps historical rows.

15. **A1-CR-003 — сумма warehouse-ведомостей равна seller report и счёту**
    — слой: backend API + invoice integration; приоритет: P0. Цель: дневное
    округление не может потерять или создать копейку при границе между двумя
    операционными складами. Предусловия: один залогиненный admin и seller, два
    operational warehouse, по одному товару и по `0.0049` литро-дня на каждом,
    V2 seller rate 100 копеек. Действия: получить обе ведомости за месяц,
    seller report и invoice preview по его реальному signed token. Ожидаемый
    результат: сумма публичных строк и итогов обеих ведомостей в копейках равна
    seller report и invoice; конкретный способ allocator не навязывается.
    Данные: `0.0049 + 0.0049 = 0.0098` литро-дня за московские сутки. Способ:
    pytest integration. Статус: автоматизирован, пройден после production
    rework (`test_fractional_warehouse_statements_sum_to_seller_report_and_invoice`).

16. **A1-CR-004 — фильтр склада не меняет уже рассчитанную аллокацию** —
    слой: backend API + invoice integration; приоритет: P0. Цель: параметр
    `warehouse_id` выбирает, что видит оператор, но не обрезает seller/day
    scope округления. Предусловия: один залогиненный admin и seller, два
    operational warehouse, по одному товару и по `0.0049` литро-дня на каждом,
    V2 seller rate 100 копеек. Действия: получить список без фильтра, затем
    отдельно с каждым `warehouse_id`, seller report и invoice preview по
    реальному signed token. Ожидаемый результат: у каждого statement его
    `total_amount` и публичные amounts строк одинаковы в filtered и unfiltered
    ответах; сумма unfiltered statements, report и invoice равна 1 копейке.
    Данные: `0.0049 + 0.0049 = 0.0098` литро-дня за московские сутки. Способ:
    pytest integration. Статус: автоматизирован, пройден после production
    rework (`test_warehouse_filter_preserves_cross_warehouse_fractional_allocation`,
    1 passed).

1. **TC-NEW-A1-001 — ведомость, seller report и preview счёта дают одну сумму**
   — слой: backend API + финансовая интеграция; приоритет: P0. Цель: исключить
   две цены на одно физическое хранение. Предусловия: залогиненный
   `fulfillment_admin`, один селлер, товар объёмом 1 л, два операционных склада
   и по одному черновику за июль 2026. Действия: задать напрямую в данных
   legacy warehouse rate 99 ₽, V2 common 2 ₽ и V2 seller override 3 ₽; получить
   обе ведомости, строку seller report и `POST /billing/invoices-v2/preview` с
   подписанным `storage_calculation_token`. Ожидаемый наблюдаемый результат:
   каждая ведомость показывает 93,00 ₽ и 3,00 ₽/л·день, их сумма 186,00 ₽,
   seller report и строка счёта — 18 600 копеек; 99 ₽ не участвуют. Данные:
   2 × 31 литро-день. Способ: pytest через реальный HTTP API и SQLite. Статус:
   автоматизирован, пройден (`test_statement_report_and_invoice_use_seller_matrix_rate_not_legacy_warehouse_rate`).

2. **TC-NEW-A1-002 — индивидуальная V2 ставка приоритетнее common на всех
   складах селлера** — слой: backend service; приоритет: P0. Цель: не допустить,
   чтобы фильтр склада или common rate обошли seller override. Предусловия и
   данные — как в TC-NEW-A1-001. Действия: пересчитать все открытые draft через
   `reprice_open_storage_drafts`. Ожидаемый результат: в ответе ровно два
   черновика, оба используют rate=300; нет третьей или warehouse-scoped цены.
   Способ: pytest на сервисе поверх настоящей БД. Статус: автоматизирован,
   пройден.

3. **TC-NEW-A1-003 — зафиксированная ведомость остаётся финансовым снимком**
   — слой: backend API/ledger; приоритет: P0. Цель: смена матрицы не меняет
   закрытый месяц. Предусловия: две проверенные выше ведомости с seller rate
   3 ₽. Действия: зафиксировать каждую через API, затем закрыть старую seller
   версию 16 июля и добавить новую на 5 ₽, снова прочитать месяц. Ожидаемый
   результат: обе строки имеют `fixed`, всё ещё показывают 93,00 ₽ и 3,00 ₽,
   то есть читают immutable ledger snapshot. Данные: тот же июльский набор.
   Способ: pytest через API. Статус: автоматизирован, пройден.

4. **TC-NEW-A1-004 — legacy storage tariff не является fallback** — слой:
   backend API; приоритет: P0. Цель: старые warehouse rows остаются только
   историей. Предусловия: существует legacy ставка 99 ₽ и нет применимой V2.
   Действия: сформировать/прочитать ведомость и попытаться её зафиксировать.
   Ожидаемый результат: новая цена не вычисляется по 99 ₽, фиксация отвечает
   `tariff_not_found`. Данные: одна ведомость и чужой legacy warehouse row.
   Способ: существующий pytest
   `test_problem_current_month_and_zero_statement_fix_rules`. Статус:
   автоматизирован, ранее покрыт; в полном trio pytest в этом проходе не
   завершён из-за зависания старого набора, поэтому не отмечается как новый
   пройденный запуск.

5. **TC-NEW-A1-005 — фасад тарифа создаёт только V2 common/seller pair**
   — слой: backend API + транзакция; приоритет: P0. Цель: экран «Хранение» не
   создаёт второй источник цены. Предусловия: залогиненный admin, актуальная
   revision матрицы и селлер этого tenant. Действия: `POST
   /operations/storage/tariffs` с common и seller exception. Ожидаемый
   результат: общая и индивидуальная V2 строки с rate 500/300, ни одной
   `BillingTariffVersion(storage_liter_day)`, а public `warehouse_id` равен
   null. Данные: current Moscow date. Способ: pytest/реальная БД. Статус:
   автоматизирован, пройден.

6. **TC-NEW-A1-006 — stale revision не оставляет половину пары** — слой:
   backend API + параллельность/атомарность; приоритет: P0. Цель: при повторе
   с устаревшей ревизией нельзя сохранить common без seller rate. Предусловия:
   уже сохранена common версия, клиент держит прежнюю revision. Действия:
   отправить common+seller submit со stale revision. Ожидаемый результат: 409
   `billing_tariff_matrix_stale_revision`, seller V2 rows отсутствуют. Данные:
   ставка 2 ₽, затем конфликтующий submit 5 ₽/3 ₽. Способ: pytest. Статус:
   автоматизирован, пройден.

7. **TC-NEW-A1-007 — SQLite naive UTC boundary соответствует московской дате**
   — слой: backend unit; приоритет: P1. Цель: не сдвинуть rate на сутки после
   хранения timezone-aware timestamp в SQLite. Предусловия: SQLite вернул
   naive `2026-06-30 21:00`, то есть 00:00 1 июля в Москве. Действия: выбрать
   ставку на 30 июня и 1 июля. Ожидаемый результат: 30 июня ставки нет, 1 июля
   применяется seller override. Данные: common 2 ₽ и seller 3 ₽. Способ:
   pytest. Статус: автоматизирован, пройден.

8. **TC-NEW-A1-008 — диалог честно показывает общий scope и не посылает
   warehouse_id** — слой: frontend unit + browser E2E; приоритет: P0. Цель:
   оператор не принимает фильтр ведомости за область действия цены.
   Предусловия: admin на FfStoragePage. Действия: открыть прежний диалог,
   заполнить общую и seller ставку, сохранить. Ожидаемый результат: поле
   «Операционный склад» disabled со значением «Все операционные склады»;
   payload содержит revision, amount, valid_from и seller_exception, но не
   `warehouse_id`. Данные: revision 7, rates 1,25/1,50 и E2E seller fixture.
   Способ: Vitest + Playwright. Статус: автоматизирован, пройден (Vitest 7/7,
   `storage.spec.ts` 29/29).

9. **TC-NEW-A1-009 — права и пустое состояние** — слой: browser E2E; приоритет:
   P1. Цель: staff может видеть расчёт, но не менять цену; отсутствие тарифа не
   имитирует цену. Предусловия: fulfillment_staff, варианты без и с тарифом.
   Действия: открыть экран. Ожидаемый результат: guidance без tariff controls
   или read-only rows без кнопок изменения/фиксации. Данные: mocked storage
   summary. Способ: существующие `S-11-TC-012`. Статус: автоматизирован,
   пройден в запуске 29/29.

10. **TC-NEW-A1-010 — внешний/последующий сбой чтения не рисует ложный успех**
    — слой: browser E2E; приоритет: P1. Цель: восстановление после успешной
    записи тарифа и неуспешного refresh. Предусловия: POST тарифа возвращает
    201, следующий GET ведомостей временно отвечает 500. Действия: сохранить,
    затем нажать «Повторить». Ожидаемый результат: диалог остаётся с понятной
    ошибкой, повторный POST не происходит, после GET диалог закрывается и
    обновляется таблица. Данные: mock 201/500/200. Способ: `S-11-TC-017`.
    Статус: автоматизирован, пройден в запуске 29/29.

11. **TC-NEW-A1-011 — повтор фиксации и конкурирующий оператор** — слой:
    backend API/DB; приоритет: P1. Цель: две попытки фиксации не публикуют два
    ledger entry. Предусловия: прошлый расчётный месяц, залогиненный admin.
    Действия: выполнить два concurrent `POST .../fix`, затем получить печатную
    форму повторно. Ожидаемый результат: один ledger source, идентичная печать,
    fixed snapshot. Данные: один измеренный SKU. Способ: существующий
    `test_concurrent_fix_publishes_one_immutable_ledger_and_repeatable_print`.
    Статус: автоматизирован; повторный trio run не завершён, поэтому статус
    этого запуска не заявляется.

12. **TC-NEW-A1-012 — релевантная нагрузка при массовом пересчёте** — слой:
    service/database; приоритет: P2. Цель: оценить tenant-wide refresh всех
    draft без silent partial results. Предусловия: tenant с тысячами seller ×
    warehouse draft за перекрывающиеся периоды. Действия: common и seller
    submit, измерить время, число repriced rows, rollback при injected failure.
    Ожидаемый результат: полный список затронутых drafts или атомарная ошибка,
    без fixed rows. Данные: нагрузочная fixture ещё не определена владельцем.
    Способ: ручной/отдельный performance test. Статус: не автоматизирован и не
    запускался; это не блокирует функциональный verdict, но остаётся риском
    перед массовым tenant rollout.

## Выполнение

- `backend`: `ruff check tests/test_storage_statement_matrix.py` — pass;
  `mypy tests/test_storage_statement_matrix.py` — pass; `pytest -q
  tests/test_storage_statement_matrix.py` — **5 passed**.
- `frontend`: `npx vitest run src/screens/ff/FfStoragePage.test.ts` — **7
  passed**; `npx playwright test tests-e2e/storage.spec.ts` — **29 passed**
  (Playwright `.last-run.json`).
- Финальный backend clean run после A1-CR-001/002/003: `ruff check
  tests/test_storage_statement_service.py tests/test_storage_tariff_api.py
  tests/test_storage_statement_matrix.py` — pass; `pytest -q
  tests/test_storage_statement_service.py tests/test_storage_tariff_api.py
  tests/test_storage_statement_matrix.py` — **44 passed in 127.49s**.
- После A1-CR-004: `ruff check tests/test_storage_statement_matrix.py` — pass;
  standalone CR-004 — **1 passed**; `mypy
  tests/test_storage_statement_matrix.py` — pass.
- Финальный clean A-1 run после восстановления single-statement seam: `pytest
  -q tests/test_storage_statement_service.py tests/test_storage_tariff_api.py
  tests/test_storage_statement_matrix.py` — **45 passed in 68.25s**.
- Расширенный `mypy` с прежними `test_storage_statement_service.py` и
  `test_storage_tariff_api.py` останавливается на 10 существующих type errors
  `SimpleNamespace` в `test_storage_statement_service.py`; это не изменения
  A-1 и production-дефектом не является. Расширенный trio pytest был остановлен
  после более трёх минут и 18 тестов без финального результата, поэтому его
  нельзя считать пройденным.

## Вердикт

`TESTS_GREEN`: A1-CR-001, A1-CR-002, A1-CR-003 и A1-CR-004 проходят; после
восстановления single-statement seam обязательный clean A-1 pytest завершился
**45 passed in 68.25s**. Scoped ruff и mypy нового test file также прошли.
Полные project-wide backend gates, frontend build и Product Browser Review этим
verdict не подменяются.
