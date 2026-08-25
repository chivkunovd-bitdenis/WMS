# defect-02 · Экран говорит «сдавать можно», когда Wildberries отказывает

## Дословно

> ### 2. Экран говорит «сдавать можно», когда Wildberries отказывает · ТЗ пишется
>
> Уточнение владельца в чате: блокировка на сдаче есть и работает, вопрос в том, чтобы
> показывать раньше — до передачи.
>
> Признак «сдавать можно» система выставляет по собственному оптимистичному предположению, а
> не по ответу маркетплейса. На бою по всем двадцати шести заданиям стояло «можно», пока
> Wildberries отказывал. Справочник вердиктов не знает ни одного реального значения — всё
> приходящее превращается в «неизвестно». Оператор узнаёт о проблеме в конце дня, на сдаче,
> когда чинить поздно.
>
> Должно стать: настоящий вердикт маркетплейса виден словами прямо в строке заказа сразу
> после привязки кода, человек чинит по ходу работы. Сдача разрешена только тогда, когда
> Wildberries подтвердил.

Источник — строки 31–44 в `night/volna-9.md`.

## Что сейчас

Проверил актуальное состояние ветки `pipeline-etalon` (это HEAD, шире `origin/etalon`
на два ещё не выкаченных коммита из соседней задачи defect-01 — `2453f44` и `bd9384f`).
Отдельного коммита именно по этой карточке нет: `git log --all` по «verdict / meta / marking»
даёт только чтение метаданных WB, отдельно от показа оператору.

**1. В строке заказа настоящего вердикта WB нет вообще.**

В сводном списке заказов (`FfFbsOrdersScreen.tsx`, вкладки «Новые» и «Активные») колонка
статуса маркировки показывает содержательную плашку только на вкладке `Просрочены`:

```tsx
// frontend/src/screens/v2/FfFbsOrdersScreen.tsx:344
function metadataProblem(order: FbsWorklistOrder): MetadataProblem | null {
  if (order.metadata.required.length === 0) return null
  const rejected = order.metadata.states.some((state) =>
    ['rejected', 'replacement_required'].includes(state.status),
  )
  if (rejected) return { label: 'Отклонено WB', color: 'error' }
  const missing = order.metadata.states.filter((s) => s.status === 'missing').length
  if (missing > 0) return { label: `Не хватает честных знаков: ${missing}`, color: 'error' }
  return null
}
// ...:1327 — рендер только при statusGroup === 'expired'
```

На «Новых» и «В работе» оператор видит `FbsStatusChip`, но не видит ни слов «Отклонено WB»,
ни причины, ни «Проверяется». Компоненты `FbsMarkingStatusChip` и `MarkingCheckStatusChip`
объявлены в `frontend/src/components/fbs/FbsChips.tsx:176,209`, но `grep` по репозиторию
показывает: **ни в одном экране они не рендерятся**, это мёртвый код.

В рабочем месте сборки (`FfFbsSupplyWorkspace.tsx`, строка КИЗ на этапе упаковки, файл
`~/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1920-1993`) в строке заказа видны только
фото, название, хвост внесённого кода и кнопки печати. Никакого «Отклонено WB / ждём WB /
причина: uinBadStatus» рядом с кодом нет.

`reason` в `metadata.states[]` уже приезжает с сервера (см. `_build_metadata` в
`backend/app/services/fbs_worklist_service.py:820-830`) — но во фронте единственное упоминание
`state.reason` (grep по всему `src/`) — это перечисление отклонений в модалке блокеров,
`FfFbsSupplyWorkspace.tsx:1425`. В самой строке оператора причина никогда не показывается.

**2. Признак «сдавать можно» на клиенте оптимистичен.**

```ts
// frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:137
const MARKING_ACCEPTED_STATUSES = [
  'accepted', 'assigned', 'pending', 'allowed_without_check', 'ok',
]
function isOrderMarkingReady(order) {
  if (order.metadata.required.length === 0) return true
  const accepted = order.metadata.states.filter((s) =>
    MARKING_ACCEPTED_STATUSES.includes(s.status),
  )
  return accepted.length >= order.metadata.required.length
}
```

`assigned` («код привязан локально, WB ещё не спрашивали») и `pending` («WB ответил, что
проверка не закончена») в этом списке — это и есть «собственное оптимистичное предположение».
Функция используется, чтобы решить, разрешить ли переходы дальше и подсвечивать ли заказ
готовым.

`FbsMarkingStatusChip` (даже несмотря на то, что не отрисован) в своём коде тоже засчитывает
`assigned` за «Проверена»: `frontend/src/components/fbs/FbsChips.tsx:182`. То есть даже если
чип вернуть на экран, он будет врать теми же словами.

**3. Справочник вердиктов на сервере действительно неполный.**

`backend/app/services/fbs_marking_service.py:138-152`:

```python
def map_wb_decision_to_meta_status(decision: str | None) -> str | None:
    mapping = {
        "accepted": META_STATUS_ACCEPTED,
        "filled":   META_STATUS_ACCEPTED,
        "rejected": META_STATUS_REJECTED,
        "pending":  META_STATUS_PENDING,
        "allowedwithoutcheck":   META_STATUS_ALLOWED_WITHOUT_CHECK,
        "allowed_without_check": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "replacementrequired":   META_STATUS_REPLACEMENT_REQUIRED,
        "replacement_required":  META_STATUS_REPLACEMENT_REQUIRED,
    }
    return mapping.get(key)
```

Реальный контракт WB по актуальной ручке `POST /api/marketplace/v3/orders/meta` (см. коммит
defect-01 `bd9384f` от 21.08.2026 и его тест
`backend/tests/test_wildberries_marketplace_fbs_client.py:107-140`) отдаёт как минимум четыре
значения `decision`: `filled`, `required`, `pending`, `optional`. Из них `required` и
`optional` в справочнике **отсутствуют**, поэтому `map_wb_decision_to_meta_status` вернёт
`None`, и `_meta_details_from_wb` (`fbs_marking_service.py:262`) положит их как
`META_STATUS_UNKNOWN` — ровно то, что владелец описал как «всё приходящее превращается в
неизвестно».

**4. Почему у 26 задач стояло «можно» при отказе WB.**

`order.metadata_delivery_allowed` пересчитывается в `compute_delivery_allowed`
(`fbs_marking_service.py:286-301`): true только если для каждого `required` есть маркировка
со статусом `accepted` или `allowed_without_check`. Однако до починки defect-01 живое чтение
вердиктов не работало (метод «не разрешён»), поэтому в БД оставался `has_value=True,
check_status=CHECK_STATUS_OK` от прошлых версий клиента → `derive_meta_status` (там же,
строка 155) → `META_STATUS_ACCEPTED` → `metadata_delivery_allowed = True`. `_metadata_ready`
в `fbs_workspace_service.py:339-353` этот флаг и читает как единственный источник правды и
возвращает True. На UI это превращается в «сдавать можно», хотя WB на самом деле отклонил.

**5. Что уже сделано и что нет.**

- defect-01 (`bd9384f` + `2453f44`, ветка `fix/wb-meta-method-20260821`, в бой не влито)
  чинит **чтение** ответов WB: `reason` начал сохраняться в `FbsOrderMarking.reason` и в
  `meta_details_json`. Показ оператору в строке заказа туда не входит.
- Блокировка на самой сдаче работает: `fbs_shipment_service.py:500` в
  `_evaluate_delivery_checks` возвращает `marking_not_allowed` («Метаданные WB не допускают
  передачу»), если `compute_delivery_allowed` = false. Именно об этом владелец говорит
  «блокировка есть» — но она поздняя.
- Ничего похожего на «строку с настоящим вердиктом WB в заказе» на всех ветках репозитория
  найти не удалось: `git log --all --grep 'verdict|meta|marking|сдав'` по интересующим
  файлам изменений не даёт.

## Что должно быть

Оператор в момент работы с заказом видит **словами** живое состояние маркировки от WB,
а не наше внутреннее «принято»:

1. В каждой строке заказа (на всех вкладках `FfFbsOrdersScreen` и в списке КИЗ в
   `FfFbsSupplyWorkspace`) рядом с кодом маркировки живёт короткая плашка вердикта:
   - `«Заполнено, ждём WB»` — decision=`pending` / статус `pending`;
   - `«Требуется от WB»` — decision=`required` / статус `assigned` при ещё не спрошенном WB;
   - `«Необязательно»` — decision=`optional`;
   - `«Принято WB»` — decision=`filled`/`accepted` / статус `accepted`;
   - `«Без проверки»` — статус `allowed_without_check`;
   - `«Отклонено WB»` (красным) — статусы `rejected`/`replacement_required`; ниже строкой —
     текст причины из `reason` (например «uinBadStatus»), если WB её вернул;
   - `«Не спрашивали WB»` — состояний нет вовсе / `unknown` (это редкое, если словарь
     полный).
2. Плашка обновляется каждый раз, когда сервер синхронизировал вердикт с WB. Момент показа —
   сразу после привязки кода: пусть первая надпись будет «Ждём WB», а через 1–2 секунды
   после автосинка — реальный вердикт. Ждать конца дня оператор не должен.
3. Признак «сдавать можно» считать реальностью **только** по ответу WB:
   - на клиенте убрать `assigned` и `pending` из `MARKING_ACCEPTED_STATUSES` — принято лишь
     `accepted`/`allowed_without_check` (эти два уже используются в бэкендовом
     `_META_DELIVERY_OK`, `fbs_marking_service.py:59`);
   - соответственно `FbsMarkingStatusChip` должен считать «Проверена» по тому же правилу и
     наконец быть отрисован в строке;
   - `metadata_delivery_allowed` не должен уезжать в `True` без свежего вердикта WB — если
     `metadata_last_checked_at` пусто или decision неизвестен, показ и логика идут как
     «Ждём WB», а не как «сдавать можно».
4. Справочник decision пополнить всеми значениями текущего API: как минимум
   `required` → `META_STATUS_ASSIGNED` (WB требует, но не ответил проверкой) и
   `optional` → отдельный статус «необязательное» (не считается блокером сдачи). Прочие
   неизвестные значения писать в лог как «новый decision от WB» — чтобы не глохли молча.

Признак, по которому поймём, что получилось: оператор берёт заказ, у которого WB отвечает
`uinBadStatus/required`; в строке этого заказа сразу после сканирования КИЗ он видит
красным «Отклонено WB · uinBadStatus», а кнопка/переход к сдаче не считает такой заказ
готовым. На двадцати шести заданиях, что были у клиента 21.08, ни одно бы не встало на «можно»
при таком поведении.

Тип выбран `фича`, а не `баг`: задача требует нового UI-элемента в строке (плашка вердикта +
подпись с причиной), пересмотра словаря decision в клиенте WB и снятия оптимизма в двух
местах, где сейчас считается готовность. Это не одно точечное исправление, а видимый для
оператора кусок поведения, который нужно спроектировать (какие тексты, где именно рисовать,
какие цвета) — уровень «фичи» с макетом.

## Тип

ТИП: фича

## Экраны

- **S-03** `/app/ff/fbs` — `FfFbsOrdersScreen` (сводный список) и `FfFbsSupplyWorkspace`
  (карточка сборки поставки, строка КИЗ на этапе упаковки). Плюс общий модуль
  `frontend/src/components/fbs/FbsChips.tsx` — там `FbsMarkingStatusChip` и
  `MarkingCheckStatusChip` уже объявлены и требуют доработки/подключения.

Затрагиваются также серверные модули, но они не экраны:
`backend/app/services/fbs_marking_service.py`, `backend/app/services/fbs_worklist_service.py`,
`backend/app/services/wildberries_fbs_client.py`.

## Вопросы и допущения

- **Допущение по словам вердикта.** Тексты плашек («Ждём WB», «Требуется от WB», «Отклонено
  WB» и т. д.) — рабочая формулировка на основе действующих меток `FbsChips.tsx`
  (`Проверена / Не проверена / Требует исправления`) и словаря decision из живого ответа WB.
  Утром владелец при желании перепишет слова, механика не пострадает.
- **Допущение по `optional`.** Значение `optional` в API WB означает «поле разрешено, но не
  обязательно». Считаю, что такой decision **не** блокирует сдачу и не обязан к заполнению;
  соответствующий kind просто показывается серой пометкой «Необязательно». Если это неверно —
  правится в одной строке справочника.
- **Допущение по `required` без значения.** Если WB отвечает `decision=required`, а код ещё
  не привязан — считаю это блокером сдачи (эквивалент нынешнего `missing`). Если WB отвечает
  `required`, а код привязан — плашка «Ждём WB», сдача не разрешена, пока decision не станет
  `filled`.
- **Вопрос продакту (не блокирующий).** Показывать ли `reason` (например `uinBadStatus`)
  оператору **буквально как есть** — или подставлять человеческий перевод («Плохой статус
  УИН — код числится проданным»). Реализую как «raw reason рядом с плашкой», словарь
  переводов — отдельной задачей: сейчас важнее видимость факта, чем перевод.
- **Блокировки экрана S-03** уже описаны в `docs/blockers/S-03.md`. Новых запретов эта
  задача не вводит: `_META_DELIVERY_OK` и `compute_delivery_allowed` на бэкенде уже
  правильные и продолжат блокировать сдачу; правится только UI-показ и словарь decision.
  Отдельного блокера в реестр не добавляю.
