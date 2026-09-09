# WMS-410 — независимая проверка отключения ООО Фэшн

09.09.2026. Проверка только чтением; агент не менял production/staging, не вызывал stock PUT и не менял код приложения. Основную разрешённую владельцем операцию выполняет root.

## Проверка после первой завершённой операции

В 10:25:57Z DB подтвердила: 5425 товаров, effective WB/Ozon enabled = 0; ровно 34 товара имеют explicit Ozon=false, остальные 5391 сохранили WB=false/Ozon=NULL. Все 136 текущих syncitems этих 34 товаров на четырёх обслуживаемых WB-привязках имеют last_confirmed_amount=0. Две необслуживаемые привязки внешними вызовами не проверялись.

Фактическое чтение WB дало 110 нулевых позиций из 136. На 2103525 вернулись 26 положительных и 8 нулевых; на 2115687, 2115694, 2157148 — по 34 нулевых. Это FAIL подтверждения внешнего обнуления, несмотря на выключенные флаги и нули в DB. Сохранён [полный безопасный результат](https://github.com/chivkunovd-bitdenis/WMS/blob/2e61f8a33814217c1bb045803b744ecf22e54d6a/docs/reviews/artifacts/wms410-fashion-20260909/final-readonly.json). Исторический manifest 64 первоначально положительных позиций не сохранялся; проверяли все 136 текущих syncitems, не восстанавливали несуществующий manifest.

## Источник повторной записи

Ограниченный stage SQL не нашёл ООО Фэшн по UUID/имени, его товаров или какой-либо привязки к WB2103525. Runtime API base у Railway WMS — внутренний wb-emulator. В API-контейнере `/proc` показывал uvicorn и команду этой проверки; Railway inventory показывал WMS, web, wb-emulator, Postgres, без отдельного worker/beat. [Stage result](https://github.com/chivkunovd-bitdenis/WMS/blob/2e61f8a33814217c1bb045803b744ecf22e54d6a/docs/reviews/artifacts/wms410-fashion-20260909/stage-readonly.txt). Эти данные не подтверждают гипотезу stage-публикатора.

В production найден конкретный повторный PUT штатного `wms.fbs_stock_reconcile`:

- Локальный журнал root `slow-confirmed-operation.log` содержит c26b confirmed 26/26 zero и завершился с mtime 10:15:05Z.
- Worker получил reconcile в 10:15:22.739Z, выполнил PUT WB2103525 в 10:15:23.303Z (204), затем readback в 10:15:23.564Z (200).
- Все 26 соответствующих syncitems имеют положительный last_target_amount, прежний last_confirmed_amount=0, status=error/readback_mismatch и updated_at=10:15:23.567420Z. Набор chrtIDs точно совпадает с 26 положительными позициями позднего независимого WB-чтения. Значения совпадают у 25/26; для chrt1929366023 target=3, поздний WB=2. Причину разницы этой одной единицы не проверяли.
- Следующий журнал root `final-operation.log` (mtime 10:17:45Z) показывает c26b targeted=0: helper выбирает только положительный last_confirmed_amount, поэтому пропустил эти строки. Root сообщил, что первый административный скрипт завершился ошибкой expired ORM после успешного preclear и освободил lock до изменения product flags.

[Сохранённые строки worker](https://github.com/chivkunovd-bitdenis/WMS/blob/2e61f8a33814217c1bb045803b744ecf22e54d6a/docs/reviews/artifacts/wms410-fashion-20260909/prod-worker-scoped.log), [26 целей и статусы](https://github.com/chivkunovd-bitdenis/WMS/blob/2e61f8a33814217c1bb045803b744ecf22e54d6a/docs/reviews/artifacts/wms410-fashion-20260909/prod-2103525-targets.json), [production bindings и агрегаты](https://github.com/chivkunovd-bitdenis/WMS/blob/2e61f8a33814217c1bb045803b744ecf22e54d6a/docs/reviews/artifacts/wms410-fashion-20260909/prod-writer-readonly.txt).

Тело промежуточного worker readback не журналируется: известны HTTP200 и readback_mismatch, его точные значения неизвестны. Последующее чтение положительных остатков вместе с положительными целями и временной последовательностью связывает возврат с production reconcile между двумя административными проходами. После окончательного выключения логируются вызовы Fashion targeted=0 в 10:25:30 и 10:31:26; в прочитанном worker-фрагменте после 10:15 не было PUT2103525.

Это не доказательство другого аккаунта или обхода seller lock. В прочитанном коде reconcile использует штатный seller lock, а прерванный отдельный preclear уже отпустил его. Приложение не патчилось; DB last_confirmed не подделывался. Повторное итоговое чтение выполняется только после завершения root.

## Итоговое завершение и независимый PASS

После диагностики root завершил ту же разрешённую операцию: при уже выключенных флагах под seller lock прочитал 34 позиции WB2103525, отправил ноль только 26 фактически положительным через штатный WB-клиент и через 45 секунд получил 34 нуля. Это не изменение DB-показаний ради обхода helper. Другие склады повторно не записывались. Root сообщил exit0 `final-reconcile.log`.

Независимая проверка в **10:36:15.046239Z** повторно прочитала DB и все 136 позиций WB четырёх обслуживаемых складов: **PASS, 136/136 нулей, положительных 0, пропущенных 0**. Все 5425 product flags effective WB/Ozon off, 34 explicit Ozon=false, остальные 5391 legacy false/NULL; binding flags неизменны. [Итоговый JSON](artifacts/wms410-fashion-20260909/final-after-reconcile-readonly.json).

Не смешивать внешнее подтверждение с сохранённым статусом последней попытки: DB last_confirmed_amount=0 у 136, status confirmed у 110, error/readback_mismatch у 26; у этих 26 сохранены старые положительные last_target_amount. Скрипт независимой проверки отражает эти агрегаты отдельно, ничего не исправляет в DB. Пользовательское отключение и внешние нули подтверждены; старую диагностическую метадату не выдаём за 136 успешных статусов.
