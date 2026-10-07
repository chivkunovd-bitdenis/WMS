# Завершённая конечная матрица совместимости WMS-666

Аудит проверяет продукт `212f19d548496fef7baf75c83204b771e304281b`, а не макет.
Все новые файлы — тестовые инструменты и доказательства. `backend/app` и
`frontend/src` совпадают с этим срезом. Нет merge, deploy или изменений production.
Последний прочитанный эталон правил — `origin/etalon` `a5df04f1560de0eaaf855199065936cb22a222b1`.
Production checkout 212 сообщён ведущим; работающий образ этим аудитом не удостоверялся.

**NO-GO остаётся, теперь на основании фактической устаревшей печати.** В десяти
сценариях настоящий React передал в эмулятор старый CIS (полный код маркировки),
который на момент передачи уже отсутствовал у указанного заказа. Восьми сценариям
сканера соответствуют реальные PNG и отдельное декодирование DataMatrix; двум
ручной печати — фактически переданный браузеру HTML и декодирование его PNG.
Это проверка печатного содержимого вместе с текущей PostgreSQL-базой, а не только
успешного HTTP-запроса. Физическая бумага и внешние кабинеты не использовались.

Отдельно воспроизведена неверная подпись области действия Ozon: при выборе одного
из двух отправлений «Печать всего (2)» посылает только выбранный ID. Отсутствующая
общая WB-панель ручных действий — красная проверка предлагаемого объединения,
**не объявленная историческая регрессия**. Сам общий координатор ручной печати
нескольких поставок отсутствует; его отказоустойчивость нельзя принять по макету.

## Доказательства и результаты

| Набор | Фактический результат | Что является источником |
|---|---|---|
| Первый этап | 43 browser PASS; 72 frontend PASS; SQLite 37 PASS/8 PG-only skip; PG 21 PASS/2 FAIL; новый claim RED | [исходный отчёт](../README.md), прежние логи не перезапускались |
| Товарный barcode → настоящий pool → PNG/DB, оба входа | 2 PASS | `live-pool/result.json`; остальные четыре ошибки этого первого запуска — ошибка harness на пустом HTTP204, исправлена до достоверного race-прогона |
| Scan A → удаление → manual B, до/после claim, оба входа | 4 RED | `live-pool-races/result.json`; JSON каждого случая содержит полный payload и DB при dispatch |
| Scan A → замена КИЗ A, до/после claim, оба входа | 4 RED | `live-pool-replace/result.json` (3) и `live-pool-replace-last/result.json` (1); четвёртый запуск выделен после устранения reset-конфликта harness |
| Manual A → удаление → scan B → старый HTML A, оба входа | 2 RED | `live-manual-race/result.json`, `*-manual-output.html`, JSON с decoded CIS и актуальной DB |
| Быстрые два scan / смена флага после claim, оба входа | 4 PASS | `queue-flags/result.json`; первый intent сохраняет свои 2 копии, новый all-off scan инертен |
| Две поставки/два селлера, одинаковый barcode | 1 PASS | `multi-seller/result.json`; реальные два supply ID, разные product/seller pools, 2 разных CIS ×2 PNG |
| Selected/all/cancel/checkWB/clear/pack-all обычной поставки | 1 PASS | `controls/result.json` и подробный JSON; WB check всей поставки при selected=1 |
| Групповая WB общая панель | 1 RED предложения | `controls/result.json`, сохранён список реальных buttons/inputs; panel отсутствует |
| Частичная очистка, отказ второго, явный повтор | 1 PASS | `clear-partial/result.json`; первое удаление ровно1 раз, второе2, успешное не повторено |
| Ozon надпись all(2) против selected(1) | 1 RED продукта | `ozon-scope/result.json`, `last-requests.json`; настоящий UI, синтетическая HTTP-граница |
| 14 файлов backend, PostgreSQL | 305 PASS, 1 strict XFAIL, 0 skip | `actions-postgres.txt`, XML; 496.36s |
| Перенос и pending tape, исходные fixtures | 7 PASS, 16 FAIL, 0 skip | `transfer-postgres.txt`, XML; все16 падают на несуществующем actor UUID, не на логике переноса |
| Перенос с существующим тем же тестовым actor | 19 PASS, 0 skip | `transfer-postgres-valid-actor.txt`, XML; 10.03s; plugin создаёт User до вызова настоящего сервиса, не меняет ожиданий |
| Конструктор/количество/HTML/QR/Ozon frontend | 64 PASS, 7 файлов | `manual-frontend.txt`; 6.28s |
| Перенос frontend / ТЗ / товарная этикетка | 19 PASS, 3 файла, 4.50s | `transfer-document-frontend.txt`, отдельный целевой запуск |

Второй этап браузера: **21 выполненный случай: 9 PASS, 10 RED актуальности
печати, 1 RED Ozon, 1 RED отсутствующей панели**. Это счёт сценариев, а не число
assertions. Старые2 обычных pool PASS включены в эти21; четыре инфраструктурных
ошибки первоначального запуска исключены, их raw-log сохранён. Результаты не
складываются в процент «надёжности».

Strict XFAIL `test_gs_restore_does_not_reparse_a_code_that_already_parses`
воспроизвёл известный дефект нормализации: серийник, оканчивающийся шаблоном91xx,
в уже разделённом GS1 может переразбираться с выдуманным полем91. Это отдельный
остаточный дефект продукта, не новая регрессия объединения. XFAIL — выполненная
проверка с ожидаемым падением, не пропуск и не успешное поведение.

Два прежних PG FAIL оставлены отдельно: `[unbind]` ожидает applied вместо
нормативного available; `unbind_then_waiting_tape...` требует другой CIS, хотя
WMS-518 разрешает повторную выдачу возвращённого полного кода. Ни один из них не
позволяет старому payload печатать код после изменения его привязки.

## Конечный перечень действий и пересечений

Обозначения: **S** — отдельная поставка, **G** — сборочное задание; **A** —
`actions-postgres.xml`, **T** — `transfer-postgres-valid-actor.xml`, **F** —
`manual-frontend.txt`, **C** — прежний frontend72/browser43. Имена тестов ниже
находятся в выполненных наборах. PASS относится к указанному слою и сценарию;
живые WB/Ozon и бумага вынесены в последние строки. Строки со смежными коробами
покрывают переходы из упаковки, не расширяют предмет до всей WMS.

| ID | Действие / экран | Область, пул, фактические изменения | Выполненная проверка и результат |
|---|---|---|---|
| M01 | WB товарный scan, S/G | 1 физическая единица текущей поставки; tenant/seller/product pool; binding→print→pack | `live-pool`: 2 PASS, настоящий PNG/DB |
| M02 | WB стикер заказа, S/G | строго названный заказ; ждёт operator CIS, не выдаёт pool | C `realQrFlags` 27 PASS, явно print_chz=false |
| M03 | Operator CIS, S/G | validate без записи; commit привязки, статус WB отдельно | A `test_fbs_kiz_validate_normalizes_and_does_not_write`, commit_success, partial_success PASS |
| M04 | QR / ЧЗ / перепечатка — шесть режимов | none, QR, pool, QR+pool, copy, QR+copy; pool приоритетнее copy | C flags/controller PASS; pool настоящий M01, не подмена стикером |
| M05 | Количество копий ±, фокус/скан | N1…10 одного CIS; не расход N кодов | F `FbsScanPrintToggles`6 PASS, C copies8 PASS, M01 PNG×2 одинаковы |
| M06 | Смена flags/N при активном intent | принятый intent и следующий scan различаются | `queue-flags`4 PASS + C snapshot/copies PASS |
| M07 | Быстрые сканы, двойной intent/replay | очередь порядков, один request-key не выбирает соседа | `queue-flags` rapid2 PASS; прежние backend concurrent replay/distinct и C held receipt PASS |
| M08 | Два оператора, pool конкуренция | один code не связан с двумя заказами одновременно | прежний PG two_orders_claim и tape row locks PASS; M12–M16 проверяют отдельно старую печать |
| M09 | Несколько поставок/селлеров | совпадающий barcode не смешивает pool; переход после exhausted | `multi-seller` PASS, API вернул C0 для первого/C2 для второго, четыре декодированных PNG |
| M10 | Tenant/supply/seller/warehouse границы | чужой код/заказ/склад недоступен; остаток другого склада не конвертируется | прежний scan claims scope PASS; A owner_mismatches, foreign_supply, packaging_other_warehouse PASS |
| M11 | Точная перепечатка bound КИЗ | тот же полный CIS, exact marking ID; новый pool не расходуется | прежние atomic_reprint replaced/cancelled/concurrent/tenant PASS; QR-only Ozon inline exact PASS; F public exact entry PASS |
| M12 | Scan→delete→manual до claim, S/G | code возвращён и выдан B; old A недействителен | `live-pool-races`2 RED: старый CIS ушёл в PNG |
| M13 | Scan→delete→manual после claim, S/G | тот же риск в окне claim→dispatch | `live-pool-races`2 RED |
| M14 | Scan→replace до claim, S/G | у A новый D, очередь содержит C | `live-pool-replace`2 RED |
| M15 | Scan→replace после claim, S/G | выданный claim не подтверждает актуальность dispatch | replace main+last2 RED |
| M16 | Manual→delete→scan другого заказа, S/G | старый HTML A содержит C, фактическая DB уже B | `live-manual-race`2 RED, декодирован реальный HTML |
| M17 | Ручная ЧЗ/ШК строки, S/G | 1 заказ; pool только недостающий; existing bindings повторяются | reverse2 доказывают настоящий вход/рендер; прежний missing_codes PASS; нет выдачи новых кодов для копий |
| M18 | Ручная selected/all, S | selected IDs либо все; QR/ЧЗ/ШК состав ленты | `controls` PASS:1→2 scope и реальные записи DB |
| M19 | Предпросмотр / отмена конструктора | до confirm нет binding/печати; после prepare отмена не отменяет уже отправленную бумагу | `controls` cancel PASS (ноль mutations), F confirmOrder и HTML launch/timeout PASS |
| M20 | Порядок блоков/размер/ориентация/нулевой ЧЗ | layout/copies, QR-only не требует pool, Ozon barcode нужен только label | F14 availability6 + printMarkingCodeLabel PASS; размеры JSON не доказательство бумаги |
| M21 | Повтор ручной ленты, shortage/partial | reuse existing; pending accepted остаётся, definite reject исключается | прежний tape concurrency/missing PASS; `test_wms560_tape_pending_kiz`4 PASS (исходный transfer набор) |
| M22 | QR строки / повтор QR | asset конкретного заказа; print opened и applied раздельны | A `test_fbs_print_assets`7 PASS, C QR image equality/retry PASS |
| M23 | Проверить в WB, S | **вся поставка**, не выбранные строки; readback statuses | `controls` actual-click PASS; A partial/omitted/rejected readers PASS |
| M24 | Очистить ЧЗ selected, S | последовательный DELETE, pool return; не pack-undo | `controls` PASS; `clear-partial` PASS: стоп на503, успех сохранён, повтор только остатка |
| M25 | Отмена/замена КИЗ строки, S/G | снимает/заменяет binding, восстановление прежнего при отказе WB | A delete_wb_error, replacement_restores_old, restore_also_fails PASS; M12–16 очередь RED |
| M26 | Назад / сброс выбора scan | отменяется соответствующий шаг; не физический возврат со списанием | C undo/recovery PASS; A `test_packaging_fact_contract`, WMS518 cancellation, WMS635 undo PASS |
| M27 | Всё упаковано, S | все packingOrders, независимо от selected; учётный факт | `controls` actual-click PASS; A mass/repeat/manualpack PASS |
| M28 | Printed vs packed vs stock | печать не упаковка; упаковка не списание/переход WB | A packaging integration/fact/fulfillment PASS; readonly stock snapshots сохранены в browser |
| M29 | Перенести selected в другую поставку | сохраняет CIS, sticker, picking/packing; idempotent request; unknown readback | T19 PASS с валидным actor; UI `FbsTransferSupplyDialog` отдельный выполненный тест |
| M30 | Сдать без Честного знака | явный skip; не новая выдача кода; повтор existing допустим | A `test_fbs_skip_reprint` PASS, прежний skipped_tape_without_codes PASS |
| M31 | Отказ КИЗ / фильтр отказов | rejected не accepted; order identity сохраняется | A active_over_rejected, pool_counts_replacement, readback decisions PASS; C реальный экран+geometry |
| M32 | Переходы упаковка/короба/отгрузка | упаковка не gate и не возврат на picking | A packing_box navigation и packaging deliver_without_packaging PASS |
| M33 | Короба WB create/QR/retry | группы коробов, не новый физический group при timeout | A `test_fbs_packing_box`49 PASS, включая concurrent/partial/lost/readback/scope |
| M34 | Ozon scan / позиции | собственный posting/position, WB product scan неприменим | прежний `product_scan_is_wb_only` PASS; A Ozon positions/process/assembly PASS |
| M35 | Ozon ручная label/КИЗ | точные order_product_ids, actual Ozon barcode; полный CIS set | F position/barcode + A Ozon positions/process PASS; inline exact старый PASS |
| M36 | Ozon общий print-all при selected | надпись all(2), фактически1 | `ozon-scope` RED настоящего UI; синтетический ответ API не меняет исходящий scope |
| M37 | Ozon короба/PDF/ошибка отправки | position exclusivity, ordered PDF, finite recovery, full-code set | A `test_ozon_box_assembly`, `test_ozon_fbs_process_contract` PASS; F PDF pair order/copies PASS |
| M38 | Потеря ответа / reload / remount | то же печатное намерение; неизвестный outcome не слепой повтор | C lost-ack/remount9 PASS; A uncertain_initial_write + T unknown_create/partial/crash PASS |
| M39 | ТЗ / товарная этикетка | печать текущих product/seller instructions, не pool allocation | выполненный `transfer-document-frontend` renderer tests; физический лист см. M43 |
| M40 | Общая ручная панель WB, G | selected/all/clear/checkWB/pack-all как общее действие | `controls` RED отсутствия panel; отдельные строки доступны |
| M41 | Общий multi-supply/seller manual coordinator, partial/cancel/reload | требуемого batch coordinator ещё нет | FAIL реализации: M40 доказывает отсутствие входа; макет исключён; нечего запускать как существующий продукт |
| M42 | Живые WB/Ozon ответы и кабинеты | реальные external side effects | Внешняя граница: поручение запрещает реальные складские мутации/кабинеты. Тестовый контур принудительно запрещает внешний HTTP; выполнены synthetic rejection/unknown/readback |
| M43 | Драйвер/OS/физическая бумага | фактическая подача этикетки и размеры | Внешняя граница: в разрешённом изолированном контуре только emulator/HTML print hook, физического принтера нет. PNG/CIS/копии доказаны, бумага не заявлена |

Для M08/M12–16 второй оператор представлен независимым запросом настоящего API
при удерживаемом первом HTTP-ответе браузера. Это реальная межтранзакционная
конкуренция, а не две нарисованные кнопки. Две вкладки с независимыми локальными
хранилищами дополнительно представлены серверными atomic/replay tests и прежним
remount browser; физические рабочие места не имитируются как бумажное доказательство.
Отдельной кнопки «физический возврат товара» на этих экранах нет; M26 не переименован
в такой возврат. Списание остаётся только у проведённой отгрузки.

## Минимальная необходимая правка и повторная проверка

1. Pool claim должен проверять **текущие** order/marking/code в одной согласованной
   транзакции и возвращать payload подтверждённой привязки. Старый `printed_codes`
   не может сам разрешать печать. Сохранить legal pool return WMS-518.
2. Отдельно закрыть интервал после claim до dispatch, обе стороны manual↔scan и
   неизвестный результат уже принятого print job. Один recheck перед claim не
   исправляет восемь воспроизведённых поздних/ручных путей автоматически.
3. Ozon label должен точно обозначать selected/all либо callback должен соответствовать
   «всего». Конкретное объединение ещё требует реализации общего coordinator и
   проверки partial/retry на её настоящем коде; оно не исправлено этим аудитом.
4. Сохранить existing exact-reprint claims, tenant/seller/supply isolation, N копий
   одного CIS, ordered QR→ЧЗ→pack, unknown outcome recovery и независимость stock.
   После исправления прогнать эти красные случаи без изменения ожиданий, затем
   существующие72/43 и применимые PostgreSQL наборы. Это не перечень единственных
   возможных дефектов системы.

## Как воспроизвести и что не является PASS

Существующие зависимости переиспользованы. PostgreSQL17.10, отдельная локальная
`wms_test_666_compatibility_audit`; API16689, Vite16686, один Chrome16687.
Команды сохранены в [commands.sh](commands.sh). Не запускать сервер и pytest
одновременно на этой DB. `wms666_audit_server.py` отклоняет другие DB names и
блокирует внешние HTTP transport. `/seed` содержит только синтетические данные;
его auth headers намеренно не включаются в evidence.

Новый harness не подключён вместо обязательных CI-тестов и не исправляет продукт.
Существующий CI с43browser/native/emulator остаётся; он не покрывал товарный pool
сквозь актуальную DB и manual-HTML stale interval. Ветка аудита имеет намеренные
RED, полный CI и deployment не заявляются зелёными. Старый document gate FAIL
зафиксирован в `../document-gate.txt`; ссылки старых требований не ослаблены.

Недостоверные попытки не выданы за продукт: HTTP204 parser исправлен; один reset
остановлен до четвёртого replace и он повторён отдельно; ранний старт до готовности
API повторён. Transfer plugin при первой загрузке импортировал сервис до conftest:
попытка подключения к стандартной локальной DB была отвергнута до выполнения
тестов; импорты перенесены внутрь fixture. Достоверный19/19 использует только
явно указанную отдельную DB. Эти ошибки инструмента не включены в продуктовые RED.
