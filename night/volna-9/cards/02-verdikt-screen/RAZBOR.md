# Разбор · 02-verdikt-screen

## Дословно

Из `night/volna-9.md`, строки 31–44:

> ### 2. Экран говорит «сдавать можно», когда Wildberries отказывает · ТЗ пишется
>
> Уточнение владельца в чате: блокировка на сдаче есть и работает, вопрос в том,
> чтобы показывать раньше — до передачи.
>
> Признак «сдавать можно» система выставляет по собственному оптимистичному
> предположению, а не по ответу маркетплейса. На бою по всем двадцати шести
> заданиям стояло «можно», пока Wildberries отказывал. Справочник вердиктов
> не знает ни одного реального значения — всё приходящее превращается в
> «неизвестно». Оператор узнаёт о проблеме в конце дня, на сдаче, когда чинить
> поздно.
>
> Должно стать: настоящий вердикт маркетплейса виден словами прямо в строке
> заказа сразу после привязки кода, человек чинит по ходу работы. Сдача
> разрешена только тогда, когда Wildberries подтвердил.

## Что сейчас

### Кто это уже трогал

По этой же теме уже уехала задача `20260821-wb-meta-verdict-read` — два коммита
в ветке `fix/wb-meta-method-20260821`, в бою (`origin/etalon`) их ещё нет:

- `bd9384f fix(wb): retain official FBS metadata verdicts` — читаем реальные
  `metaDetails` (`key`, `value`, `decision`, `reason`) из `POST /api/marketplace/v3/orders/meta`,
  сохраняем `reason` на записи маркировки. Ретрай на 429 ограничен.
- `2453f44 fix(wb): batch autopoll metadata reads` — автополлер собирает
  запрос пачкой до ста ID.

Это чинит **чтение** — про него отдельная карточка `01-wb-marking`.
**Эта карточка (02)** про два другие слоя, которые ни один из двух коммитов
не тронул:

1. **Справочник вердиктов** — как реальные ответы WB превращаются в наш `meta_status`.
2. **Показ вердикта в строке заказа + гейт сдачи.**

Ни в одной ветке, ни в задаче `20260821-wb-meta-verdict-read` изменений
`map_wb_decision_to_meta_status`, `_meta_details_from_wb`, `metadataProblem`
или UI-строки FBS не найдено (`git log --all -S ...`, `git log --all --grep=верд`).

### Справочник вердиктов действительно куц

`backend/app/services/fbs_marking_service.py:138–152`

```python
def map_wb_decision_to_meta_status(decision: str | None) -> str | None:
    ...
    mapping = {
        "accepted": META_STATUS_ACCEPTED,
        "filled": META_STATUS_ACCEPTED,
        "rejected": META_STATUS_REJECTED,
        "pending": META_STATUS_PENDING,
        "allowedwithoutcheck": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "allowed_without_check": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "replacementrequired": META_STATUS_REPLACEMENT_REQUIRED,
        "replacement_required": META_STATUS_REPLACEMENT_REQUIRED,
    }
    return mapping.get(key)
```

Реальные значения `decision` из ручки [WB v3 orders/meta](https://dev.wildberries.ru/docs/openapi/orders-fbs)
и мартовского обновления [news 302](https://dev.wildberries.ru/news/302) —
`filled`, `pending`, `required`, `optional`, `notRequired`
(в живом тесте `backend/tests/test_wildberries_marketplace_fbs_client.py:103–140`
уже фигурируют четыре — `filled/required/pending/optional`). Из них справочник
знает три (`filled/pending/accepted`), про `required/optional/notRequired`
не знает вовсе.

Что происходит с неизвестным `decision`:

- `_meta_details_from_wb` (`fbs_marking_service.py:256–269`) на такой отдаёт
  `META_STATUS_UNKNOWN` (в `order.meta_details_json`). На фронте союз
  `state.status` в `frontend/src/screens/v2/fbsApi.ts:151–172` **`'unknown'` не содержит**,
  строка молчит.
- `_apply_meta_detail_to_marking` (`fbs_marking_service.py:465–482`) на такой
  же ответ пойдёт через `derive_meta_status` и с `has_value=True` вернёт
  `META_STATUS_ASSIGNED`. То есть «WB требует» (`required`) и «WB не нужен»
  (`notRequired`) кладутся в одну корзину — ни одно из этих значений
  оператор словами не увидит.

### Оптимистичный признак «сдавать можно» именно здесь

Стрчка `"filled": META_STATUS_ACCEPTED`. По документации WB `filled` означает
«селлер прислал значение», а не «WB признал его валидным» — как раз для
таких случаев в ответе появляется `reason` (`uinBadStatus` и т.п.). У нас же
такое пробрасывается сразу в `ACCEPTED`, а дальше:

- `compute_delivery_allowed` (`fbs_marking_service.py:286–301`) считает
  `_META_DELIVERY_OK = {ACCEPTED, ALLOWED_WITHOUT_CHECK}` — то есть заказ с
  `filled+reason=uinBadStatus` попадает под «сдавать можно».
- `order.metadata_delivery_allowed` сохраняется в `_sync_order_meta_from_wb`
  (`fbs_marking_service.py:526`) и потом читается сервером на сдаче
  (`fbs_shipment_service.py:500`) и фронтом через поле
  `metadata.delivery_allowed` (`fbsApi.ts:170`).

По владельцу «на бою по всем 26 заданиям стояло „можно“ пока WB отказывал» —
это и есть механика: WB возвращал `filled` с плохим `reason`, мы штамповали
`ACCEPTED`, а на реальной сдаче WB не пропускал.

Тот же паттерн повторяется в `derive_meta_status`
(`fbs_marking_service.py:155–177`) — при `check_status == CHECK_STATUS_OK`
без учёта `decision/reason` возвращается `META_STATUS_ACCEPTED`. Раньше
`check_status` вообще ставился нашим кодом (задача 01), с этого и «зелёный»
пузырь на всём.

### Что видит оператор в строке заказа сейчас

`frontend/src/screens/v2/FfFbsOrdersScreen.tsx:342–355`:

```ts
function metadataProblem(order): { label; color } | null {
  if (order.metadata.required.length === 0) return null
  const rejected = order.metadata.states.some((state) =>
    ['rejected', 'replacement_required'].includes(state.status),
  )
  if (rejected) return { label: 'Отклонено WB', color: 'error' }
  const missing = order.metadata.states.filter((s) => s.status === 'missing').length
  if (missing > 0) return { label: `Не хватает честных знаков: ${missing}`, color: 'error' }
  return null
}
```

Строка знает только два повода поднять красный чип: `rejected/replacement_required`
и `missing`. Всё остальное — `pending`, `assigned`, `accepted`,
`allowed_without_check`, `sending`, `unknown` — молча ничего не рисует.
`reason` от WB (`state.reason`, `mark.reason` — уже приходят с бэка
`fbs_worklist_service.py:820–829`) в строке **не показывается никогда**.

Проверил и второй экран, где живёт та же строка — `FfFbsSupplyWorkspace.tsx`.
Там метаданные считываются функцией `isOrderMarkingReady`
(`FfFbsSupplyWorkspace.tsx:140–144`) с ещё более оптимистичной трактовкой:
`MARKING_ACCEPTED_STATUSES = ['accepted', 'assigned', 'pending',
'allowed_without_check', 'ok']` (строка 137). То есть `pending` и `assigned`
здесь тоже считаются «готово». Вердикт словами не показывается ни в
одной ячейке строки — только хвост кода (`kizTail`), никакого «WB: ждёт
проверки» или «WB: код не подходит по причине X».

### Гейт сдачи сейчас

Он есть на обоих слоях:

- Сервер: `fbs_shipment_service._build_delivery_checks` (`fbs_shipment_service.py:500`)
  падает с `marking_not_allowed`, если `compute_delivery_allowed` вернул False.
- Фронт: `canDeliverFbsSupply` (`fbsApi.ts:1036–1038`) режет по статусу
  поставки, а per-заказный признак приезжает в `order.metadata.delivery_allowed`.

Оба слоя опираются на **тот же `compute_delivery_allowed`**, поэтому
проблема не в гейте самом по себе, а в том, что `_META_DELIVERY_OK` включает
`ACCEPTED`, а `ACCEPTED` штампуется на `filled` — оптимистично.

### Блокировки экрана S-03

`docs/blockers/S-03.md` в реестре есть, разобран. По теме задачи ближе всего
Б-13 («Передать в доставку» — только `packed`) и РС-1 (расхождение слоёв про
`_DELIVER_BLOCKED_SUPPLY_STATUSES`), но они про статус поставки, а не про
маркировочный вердикт. Отдельной блокировки «строка не показывает вердикт
WB» в реестре нет — потому что до сих пор такого элемента в UI не было.

## Что должно быть

Три вещи по разным слоям, но одна задача.

**1. Справочник вердиктов знает все живые значения WB.**
Расширить `map_wb_decision_to_meta_status` тремя пропущенными:
`required`, `optional`, `notRequired`. Проверить приведение из camelCase:
у WB именно `notRequired` (сейчас `_normalize` схлопнет в `notrequired` и
не найдёт ключа — надо явно добавить). Значения:

- `required` → отдельный статус «WB требует, ещё не прислали» (сегодня
  для этого используется `META_STATUS_MISSING`, но по смыслу это разные
  вещи: «WB считает, что должно быть, но пока не пришло» ≠ «мы не
  знаем, нужно ли»).
- `optional` → «можно приложить, необязательно» — этот `kind` вообще
  не должен блокировать сдачу; сейчас он попадает в
  `required`+`ASSIGNED`/`UNKNOWN` и мешает.
- `notRequired` → тот же смысл, что `optional`, но явное «WB не требует».

Признак «WB подтвердил» отрывается от `filled`. `filled` без `reason`
и без явного одобрения — это `META_STATUS_PENDING`, а не `ACCEPTED`.
`ACCEPTED` штампуется только по явному одобрению WB (сейчас в живых
ответах его нет — значит по-настоящему готовым остаётся только
`ALLOWED_WITHOUT_CHECK` до тех пор, пока не увидим реального
`decision`, означающего «принято»; см. допущение ниже).

**2. Гейт сдачи только по WB-подтверждению.**
`compute_delivery_allowed` возвращает True только когда все required
маркировки в `{ACCEPTED, ALLOWED_WITHOUT_CHECK}` и ни у одной нет
непустого `reason`. Наличие `reason` — сигнал, что WB что-то не так с
кодом, даже если формально `filled`. `order.metadata_delivery_allowed`
пересчитывается сразу после каждого обновления метаданных
(`_sync_order_meta_from_wb`, `attach_order_meta_to_wb_and_sync`,
`fbs_order_tape_print_service.py:457,508`).

**3. Строка заказа показывает вердикт WB словами.**
В `frontend/src/screens/v2/FfFbsOrdersScreen.tsx` рядом с чипом
маркировки — короткая понятная фраза по каждому `required`/`optional`
`kind`: «Честный знак: WB проверяет», «Честный знак: WB не принял —
{перевод reason}», «Честный знак: WB требует, не пришёл», «Честный знак:
WB подтвердил», «Разрешено без проверки». Показываем сразу после
привязки кода, до сдачи. Появляется словарь `metaStatus.ts` рядом с
`markingStatus.ts` (перевод статусов и известных `reason`
из WB — сегодня в UI переводов нет вообще).

Тот же вердикт словами едет в `FfFbsSupplyWorkspace.tsx` рядом со
строкой упаковки заказа: `MARKING_ACCEPTED_STATUSES` перестаёт считать
`pending`/`assigned` «готово», иначе оператор всё равно проваливается
на сдачу с «сдавать можно» в UI и `marking_not_allowed` на сервере.

Признак «получилось»: 
- В браузере на живой поставке с `filled+reason=uinBadStatus` в строке
  видно **красным** «WB не принял: неверный статус УИН» до того, как
  оператор доходит до сдачи. Сдача при этом на этой поставке
  недоступна — гейт бьёт заранее.
- В `map_wb_decision_to_meta_status` для всех decisions из живого
  ответа WB (тест `test_fetch_orders_meta_batch_exact_contract_and_parse`)
  результат — не `None` и не `UNKNOWN`.

## Тип

ТИП: фича

## Экраны

- `S-03` — FBS-заказы + workspace поставки. Файлы в реестре:
  `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`,
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`,
  `frontend/src/screens/v2/fbsApi.ts` (общий с S-04).

Новый экран не нужен — правим существующий.

## Вопросы и допущения

**Допущение 1.** Реального значения `decision`, которое WB отдаёт как
«принял, всё ок», в живых ответах пока не видели (в тесте
`test_fetch_orders_meta_batch_exact_contract_and_parse` — `filled`,
`required`, `pending`, `optional`; в списке из [news 302](https://dev.wildberries.ru/news/302)
— то же плюс `notRequired`). До появления такого значения считаю: `filled`
без `reason` — `PENDING` (в UI: «WB проверяет»), `filled` с `reason` —
`REJECTED` (в UI: «WB не принял: …»). Если WB когда-нибудь начнёт слать
`verified/passed/accepted`, добавим маппинг в тот же словарь без
изменения UI-слоя. Ошибиться в сторону «WB ещё не подтвердил» безопаснее,
чем ложное «сдавать можно»: гейт держит.

**Допущение 2.** Перевод известных `reason` в человеческие фразы
(`uinBadStatus` → «неверный статус УИН», и т.п.) кладу в
`frontend/src/utils/metaStatus.ts` по образцу `markingStatus.ts`.
Неизвестный `reason` показываю как есть, чтобы оператор всё же имел
подсказку и мог позвонить продавцу или в поддержку WB.

**Допущение 3.** Для `kind`, у которого WB прислал `optional`
или `notRequired`, состояние строки — «WB: код необязателен» серым,
без блокировки сдачи. Такой `kind` больше не участвует в
`compute_delivery_allowed`, даже если он был в
`order.required_meta_json` (список требований от WB — момент во времени;
для конкретного заказа `decision` мог сообщить, что он не нужен).

Владельцу вопросов не задаю — все три пункта из его же формулировки
«настоящий вердикт словами», «сдача только по WB», «справочник знает
живые значения», и трактовки выбраны в пользу более осторожного
поведения (никогда не показать «можно», пока WB не сказал явно).
