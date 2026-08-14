# Батч 02. Fixture/action execution checklist

## Как читать

Это исполнимый список для реального staging Browser-прогона. Он составлен по source inventory, но не является screen/action ledger и не содержит verdict по невиденному интерфейсу. До появления in-app Browser каждая строка имеет статус `NOT_RUN_BROWSER_UNAVAILABLE`. После прогона каждая выполненная строка должна перейти в отдельную строку `B02_SCREEN_ACTION_LEDGER_RU.md` со screenshot и точным outcome.

## A. Сессия и isolated fixtures

| ID | Роль / route / действие | Безопасный ожидаемый результат | Сейчас |
|---|---|---|---|
| B02-C001 | Подключить только in-app Browser, открыть staging | Видимый staging, без подмены другим browser | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C002 | Войти isolated synthetic seller из B01 | `/seller/documents`, только его tenant context | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C003 | Войти admin и открыть manual product create UI | Форма «Создать товар», без WB sync | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C004 | Manual product: submit пустых required name/SKU | Видимая понятная validation, mutation отсутствует | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C005 | Manual product: cancel после заполнения synthetic значений | Диалог закрыт, товар не создан | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C006 | Manual product: создать SKU-1 double-click | Ровно один товар либо явная duplicate-защита; screenshot/read-back | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C007 | Manual product: reload каталога | SKU-1 и seller binding сохранены | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C008 | Manual product: повторить SKU-1 и отдельно ШК SKU-1 | Явные duplicate SKU/barcode ошибки без второй записи | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C009 | Manual product: создать SKU-2 | Второй безопасный товар для sort/picker/document tests | `NOT_RUN_BROWSER_UNAVAILABLE` |

## B. Seller products populated

| ID | Route / CTA | Что проверить глазами и действием | Сейчас |
|---|---|---|---|
| B02-C010 | `/seller/products` populated, 1280×720 | Обе строки, tenant scope, SKU/ШК/название, нулевые остатки, overflow и доступность правых действий | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C011 | `/seller/products`, 1920×1080 DPR1 | Нет скрытых/обрезанных действий; compare 1280 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C012 | CTA «Синхронизировать товары» | Только видимый credentialless/disabled state; не нажимать WB sync | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C013 | FBS per-row/bulk controls | Только визуальный inventory; ничего не переключать и не менять shared-stock | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C014 | «ТЗ упаковки» open | Смысл полей, cancel, следующая роль ФФ | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C015 | ТЗ: безопасный текст + marking flag, save double-click | Одно сохранение, диалог закрыт либо busy-защита | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C016 | Reload/read-back ТЗ | Текст и flag восстановлены; populated gap B01-066 закрыт | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C017 | ТЗ wrong/empty/cancel recovery | Пустое значение трактуется предсказуемо, cancel не сохраняет draft | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C018 | CTA печати ТЗ | Проверить visible preview/outcome только если не отправляет на внешнее устройство; иначе NOT_RUN с причиной | `NOT_RUN_BROWSER_UNAVAILABLE` |

## C. Inbound draft и submit handoff

| ID | Route / действие | Что проверить | Сейчас |
|---|---|---|---|
| B02-C019 | `/seller/inbound/new` | Создаётся один draft, есть ID/status, дата/короба и понятная ориентация | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C020 | Немедленный reload `/seller/inbound/new`/detail | Нет второго скрытого draft; текущий draft доступен | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C021 | Date wrong/past/empty + recovery | Клиентская/серверная validation понятна, можно исправить | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C022 | Boxes `0`, negative, decimal, text + recovery | Только положительное целое либо ясная ошибка | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C023 | «Добавить товары» open/cancel | Picker populated только своими товарами; cancel без mutation | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C024 | Picker wrong qty `0`/negative/decimal/text | Понятная validation и восстановление | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C025 | Добавить SKU-1 и SKU-2 с количеством | Две строки, expected qty совпадает | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C026 | Повторно добавить SKU-1 | Нет второй строки; quantity либо суммируется предсказуемо, либо duplicate error | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C027 | Inline qty edit wrong input + recovery | Неверное не сохраняется; корректное значение сохраняется | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C028 | Delete line cancel/execute/re-add | Outcome и recovery ясны; без случайного удаления | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C029 | Save draft double-click | Ровно один durable state, busy/идемпотентная защита | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C030 | Browser reload/read-back draft | Date, boxes, lines/qty/status восстановлены | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C031 | Browser back/forward из draft | Возвращается список/detail без потери данных и orientation | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C032 | Submit с missing/invalid state | Блокировка/понятная error, status не меняется | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C033 | Submit double-click на валидном draft | Один переход `draft→submitted`; stock не проведён | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C034 | Reload/read-back submitted | Read-only state, точные lines/boxes/date, ясное «что подготовить/передать ФФ дальше» | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C035 | Попытка edit/delete submitted | Действия скрыты/disabled или coherent error; stock неизменен | `NOT_RUN_BROWSER_UNAVAILABLE` |

## D. Documents populated, filters/sort/rows

| ID | Route / действие | Что проверить | Сейчас |
|---|---|---|---|
| B02-C036 | `/seller/documents` populated | Inbound row видна; B01-065 fixture gap закрыт | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C037 | Filter «Поставка» | Только inbound; терминология и empty/populated count | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C038 | Filter «Отгрузка на МП» | Только MP rows | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C039 | Filter «Акт расхождений» | Реальный empty/populated outcome, без предположений | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C040 | Sort new→old и old→new | Видимый фактический порядок минимум двух dated docs | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C041 | Click inbound row | Открывается точный `/seller/inbound/:id` | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C042 | Back/forward/reload row detail | Context и state сохраняются | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C043 | Click «Создать акт расхождений» | Сохранить точный видимый outcome; CTA presence не PASS | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C044 | Correction CTA double-click/recovery | Нет двойной mutation; после outcome можно продолжить | `NOT_RUN_BROWSER_UNAVAILABLE` |

## E. Seller-side MP draft only

| ID | Route/dialog/action | Что проверить | Сейчас |
|---|---|---|---|
| B02-C045 | «Создать отгрузку на МП» double-click | Ровно один seller draft/dialog; никакой внешней отгрузки | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C046 | MP dialog populated shell | Plan-only hint, date, WB warehouse field, own-product picker, close | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C047 | MP picker open/cancel/wrong qty | Нет mutation после cancel/error | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C048 | Add available SKU / no-stock outcome | Точный outcome при нулевом доступном stock; не создавать/не проводить stock | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C049 | MP plan save/edit/reload | Только если допустим при existing available synthetic stock; иначе `BLOCKED_FIXTURE` с точным полем | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C050 | MP row open/back from documents | Тот же draft ID и состояние | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C051 | Confirm/ship/unplan/cancel/external actions | `NOT_RUN_SAFETY`: не нажимать по контракту; перечислить, что видно/disabled | `NOT_RUN_BROWSER_UNAVAILABLE` |

## F. Settings, credentialless и safe non-secret

| ID | Route / действие | Что проверить | Сейчас |
|---|---|---|---|
| B02-C052 | `/seller/settings` | WB/ЧЗ cards, смысл состояния, active nav, seller context | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C053 | WB key status + sync CTA | Credentialless status и disabled sync; key dialog/save не открывать и не нажимать | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C054 | ЧЗ summary/edit open | Только по явному scope: поля видимы, credential values не читать/не вводить | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C055 | ЧЗ cancel after safe non-secret change | Изменение не сохраняется | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C056 | Save isolated safe non-secret field double-click | Одно сохранение; secret/token поля пусты и не отправлены | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C057 | Reload/read-back safe setting | Значение durable; success/recovery понятны | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C058 | Wrong non-secret input + recovery | Понятная validation, корректное значение затем сохраняется | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C059 | WB add/replace key, token entry, sync | `NOT_RUN_SAFETY`; не открывать/не вводить/не запускать | `NOT_RUN_BROWSER_UNAVAILABLE` |

## G. Evidence и закрытие

| ID | Артефакт | Требование | Сейчас |
|---|---|---|---|
| B02-C060 | 1280×720 и 1920×1080 DPR1 | Screenshot на каждый выполненный экран/CTA/error/reload в `evidence/b02/` | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C061 | Sanitized state/network log | Только URL, действие, status/outcome/ID; никаких credential values | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C062 | `B02_SCREEN_ACTION_LEDGER_RU.md` | Одна строка на route/tab/dialog/CTA/error/reload | `NOT_RUN_BROWSER_UNAVAILABLE` |
| B02-C063 | Findings/handoff | Только подтверждённые Browser evidence; точные remaining fixtures | `NOT_RUN_BROWSER_UNAVAILABLE` |

Всего checklist-пунктов: **63**. Это плановое число, не coverage count завершённого ledger.
