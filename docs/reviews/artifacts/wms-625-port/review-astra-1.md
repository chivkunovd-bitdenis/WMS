# WMS-625 — независимое перекрёстное ревью переноса, 03.10.2026

**Вердикт: FAIL. Четыре находки P0 и одна P1.** P0 используется в значении, заданном владельцем для этого ревью: дубль/потеря этикетки либо нарушение скана, печати или упаковки. Обычный успешный путь проходит тесты, но смена версии программы и отказ браузерного хранилища нарушают обязательные сценарии.

Проверена ветка `fix/wms625-on-etalon-20261003`, HEAD `a2b766393af0cf2a32294ab19430fb282dbcab9e`, diff от `0171375ae` по `frontend` и `.github`. Начальное рабочее дерево чистое. Изменения `tools/support_agent` из последующего etalon не включались. Продуктовый код не менялся; commit, push и deploy не выполнялись по прямому поручению владельца.

До анализа прочитаны целиком основной `/Users/deniscivkunov/Projects/WMS/AGENTS.md`, `owner-cases.md`, `failure-cases.md` и `docs/requirements/WMS-625.md`, включая раздел переноса 03.10. Историческая приёмка 01.10 не считалась приёмкой переноса. Программы прочитаны только на совместимость: старая Swift из `9a33b651c`, Python из `0171375ae`, соответствующие границы новой программы в HEAD. Проверка физической бумаги и всего PR #326 заново не выполнялась.

## F1 — P0. Закэшированный старый путь допускает две этикетки при откате новой Mac-программы

**Место:** `frontend/src/utils/durableDirectQr.ts:225–235`, особенно строка 234; выбор по кэшу — строка 150. Подключение к скану: `frontend/src/screens/v2/fbsSequentialPacking.ts:765–774`.

Сценарий: сайт запомнил protocol 1; в течение минуты оператор установил новую программу. Следующий QR отправляется через `dispatchLegacy`, новая программа сохраняет и принимает его, но HTTP-ответ теряется. Затем оператор возвращает старую Mac-программу и повторяет тот же скан. В браузере нет `dispatchStartedAt`, `result`, `acceptedReceipt` или `legacyAcceptedAt`: перед старым запросом сохраняется только вход, а результат пишется исключительно после успешного ответа. Поэтому проверка в строке 229 не срабатывает и тот же ключ уходит старой программе повторно.

Это **не** повтор внутри одного общего журнала. Новая Swift хранит новые задания в `jobs-v2/*.json` (`tools/print-agent/wms_print_direct_macos.swift:183`, `:228–229`), а старая `.4` читает `direct-jobs.json`; новая импортирует старый файл при запуске, но не записывает в него новые задания. Старая программа не знает ключ, принятый новой, и создаёт второй внешний экземпляр. Наличие `context` в обоих запросах этого не исправляет. Аналогичный первый шаг возможен при пропавшем ответе `/health` новой программы, без предварительного обновления со старой.

**Подтверждение:** адресный тест вызывает настоящий `dispatchDurableQr` и `printDirectQr`, моделируя два журнала согласно Swift-исходникам. Два POST с одним `review-scan` дали **два приёма в модель очереди**. Физическая печать не запускалась. После потери ответа серверная отметка `started` ещё не поставлена; повтор с тем же ключом разрешён существующей арендой WMS-631 (`backend/app/services/fbs_scan_auto_print_service.py:884–891`). Поэтому аренда этот случай не закрывает.

**Что требуется исправить:** нельзя считать фактическую версию принявшей программы установленной по минутному кэшу и терять границу возможной отправки при старом формате запроса. После неопределённого результата смена журнала должна обнаруживаться до повторной внешней отправки, при этом обычный повтор старой `.4/.5` обязан сохранить прежнюю работоспособность. Приёмка: этот сценарий даёт максимум одно задание очереди; положительный сценарий повторного POST в неизменную старую программу остаётся рабочим.

## F2 — P0. Новая программа делает IndexedDB обязательным условием скана → QR

**Место:** `frontend/src/utils/durableDirectQr.ts:242–249`, также `:268` и `:311`; ошибка хранилища формируется в `:33–54`.

Сценарий: `/health` возвращает protocol 2, но IndexedDB недоступна либо чтение/запись завершается ошибкой. `restoreDurableQr`/`prepareDurableQr` вызываются без обхода ошибки, поэтому QR вообще не отправляется, даже если сама программа полностью исправна и способна сохранить задание. При ошибке сохранения уже полученной квитанции упаковка также останавливается. В `finish()` печать ожидается до упаковки (`frontend/src/screens/v2/fbsSequentialPacking.ts:300–308`); незавершённый заказ остаётся pending, а следующий чужой штрихкод получает требование закончить предыдущий (`:496–497`).

**Подтверждение:** два адресных теста, отдельно отказ чтения и записи: единственный запрос — `/health`, `/print` отсутствует, Promise печати отвергнут. В существующем наборе это поведение прямо закреплено тестом `does not contact native if storage cannot commit` в `durableDirectQr.test.ts` — зелёный тест здесь подтверждает несовпадение с текущим поручением, а не снимает его. Старая ветка ошибку хранилища обходит; значит, установка новой программы сама меняет доступность рабочего скана.

**Что требуется исправить:** выполнить прямое требование текущего ревью «IndexedDB недоступна/ошибка — скан не должен останавливаться» с сохранением ключа и проверки журнала программы. Нельзя просто обходить проверку неопределённого результата и тем самым создать F1. Старое R13 про обязательное сохранение в браузере требует согласования реализации с более поздним явным поручением владельца; здесь приоритет отдан этому поручению.

## F3 — P0. При кэше protocol 2 и фактически старой программе один сбой делает повтор невосстановимым

**Место:** `frontend/src/utils/durableDirectQr.ts:306–320`, затем `:229`; распознавание старой квитанции в `:277–282` работает только при успешно полученном ответе.

Сценарий: сайт недавно видел новую программу, оператор запустил старую. Её `GET /jobs/<key>` возвращает 404. Сайт сохраняет `dispatchStartedAt` и `nativeProtocol=2`, после чего посылает старой программе `/print`. Если ответ теряется, старый журнал уже может содержать нормальную квитанцию. Повтор в пределах минуты получает 404 на `/jobs` и падает на `missingHistory`; после истечения кэша или перезагрузки страницы старый путь падает на `versionLost`. Обычный повторный POST, которым production получил бы сохранённую квитанцию без второго экземпляра, больше никогда не выполняется.

Есть ещё более прямой вариант: старая программа вернула 409 «В системе не выбран принтер по умолчанию», то есть **вообще не передала** этикетку в очередь. После выбора принтера повтор блокируется тем же сохранённым флагом. Этикетка так и не выходит. Для запросов в этом ошибочно выбранном пути действует уже 15 секунд вместо прежних 30 (`:256`), что дополнительно повышает вероятность первого таймаута при старой программе.

**Подтверждение:** два адресных теста — потеря ответа после принятия и явный отказ до очереди. В обоих повтор запрещён как до, так и после сброса кэша; `/print` был вызван только один раз. Для первого случая модель старой программы сохраняет исходную квитанцию. Для второго случая не было ни одного приёма в очередь. Исходники `.4` подтверждают 404 для `/jobs`, 409 для отказа `/print` и возврат исходной квитанции по повторному ключу.

**Что требуется исправить:** смена протокола до фактической отправки не должна навсегда записывать ложное утверждение «отправлено программе с журналом v2». Нужны рабочие ветки восстановления обоих исходов без смены ключа, дубля или ручной очистки IndexedDB. Проверять не только успешную `{receipt}`, как существующий тест `program replaced by an older one after /health`.

## F4 — P0. Обновление старой программы после потери её ответа блокирует штатное восстановление заказа

**Место:** `frontend/src/utils/durableDirectQr.ts:201–207` и `:285–289`.

Сценарий: старая `.4` приняла этикетку и записала квитанцию, сайт не получил ответ. В браузере сохранились точные PNG, размер, заказ и ключ, но нет `legacyAcceptedAt`. Устанавливают новую программу. Она правильно импортирует исходную квитанцию как `legacy:true`; по прежнему ключу возвращаются эта квитанция и совпадающий хеш. Однако `diagnoseImportedLegacy` **безусловно бросает ошибку даже при совпадении хеша**. Каждый повтор снова завершится «упаковка не завершена». Ни сверка истории, ни повтор скана не меняют этот исход; автоматическая отправка новой копии не выполняется, но рабочее завершение упаковки потеряно.

**Подтверждение:** адресный тест с хешем `.4` (`|58.0x40.0`), тем же ключом и `old-1`: первый вызов через старую программу теряет ответ; два вызова после обновления одинаково отвергаются на совпавшей старой квитанции. Поведение импорта прочитано в новой Swift, строки 187–196. В старой production-цепочке повторный `/print` новой программе совместим со старым сайтом и возвращает импортированную квитанцию; отказ добавляет именно новый frontend-путь.

**Что требуется исправить:** завершать исходное намерение по достаточно проверенной импортированной квитанции, не выдавая её за физическую бумагу и не разрешая чужой ключ/другое изображение. Если для части импортированных записей данных недостаточно, нужен работающий адресный способ завершить сверку; вечная ошибка при доказанном совпадении исходной этикетки не выполняет договор переноса.

## F5 — P1. Старый путь получил ожидание `/health` до печати; ошибка запроса не кэшируется

**Место:** `frontend/src/utils/durableDirectQr.ts:149–159`, вызов в `:240`, ранний возврат уже запущенного задания только в `:223`.

Каждый первый QR, а затем первый QR после истечения минуты сначала ждёт `GET /health` с таймаутом 3 секунды, и только потом отправляет production-POST с его 30 секундами. Это новый этап ожидания для требования «сканируешь ШК — QR сразу вылез». Если `/health` зависает или падает по сети, `catch` возвращает 1 **до записи кэша**, поэтому новый запрос повторяется на каждой следующей попытке, а не раз в минуту. `.4` внутри `/health` вызывает `defaultPrinter()`/`lpstat`; отдельное замедление этого запроса не должно задерживать рабочую отправку этикетки.

Даже серверное «уже запущено» проходит через `nativeProtocol` прежде, чем старый путь возвращает управление. Следовательно, утверждение «старую программу ни о чём не спрашивают» неверно: её не спрашивают о задании, но могут снова ждать `/health`. Существующие тесты исключают `/health` из подсчёта и не ловят это отличие.

**Подтверждение:** адресный тест удерживает ответ `/health`: старый POST не начинается до завершения этой проверки. После ошибки `io.protocol` остаётся пустым, следующая попытка с `requireExisting=true` повторяет запрос. Это конечная дополнительная задержка, поэтому P1, а не утверждение о бесконечном зависании.

**Что требуется исправить:** убрать проверку возможностей программы из критического пути немедленной старой печати либо обеспечить эквивалентное прежнему поведение; ошибки определения версии также должны иметь оговорённое кэширование. Повторная проверка должна измерять момент первого `/print`, а не только количество POST после завершения всей функции.

## Что проверено и что сохранилось

Старые Swift/Python читают нужные поля JSON по имени и не отвергают дополнительный `context`: само добавление поля совместимо. Для уверенно выбранного protocol 1 остаются настоящий `printDirectQr`, один POST, последовательная очередь запросов, 30-секундный таймаут POST и прежние тексты его ошибок. Обнаруженные выше ожидание и переходы между версиями не позволяют распространить это на все сценарии.

При неизменной новой программе обычная потеря ответа восстанавливается по `/jobs/<тот же ключ>` без второго POST; сохраняются точное изображение и размер. Простой перезапуск с сохранённым журналом использует тот же контракт. При выключении программы до POST новый GET завершается ограниченным таймаутом и не ставит отметку отправки: следующий запуск может продолжить. При исчезновении журнала после возможной отправки безопасный запрет слепого повтора сам по себе не считается дефектом; F3 отличается тем, что v2-журнала у фактической старой программы не было изначально.

Снятые галки WMS-643 отсекают вызов печати до нового транспорта. ЧЗ, копии ЧЗ и прямая копия КИЗ продолжают использовать прежний `send`/`sendCopies`; `reconcileStarted` передан только в зависимость QR, для прочих пользователей `startClaimedAutomaticPrint` он отсутствует. Исходники привязки КИЗ, «Назад», фильтра WMS-636 и экран `FfFbsSupplyWorkspace.tsx` не изменены относительно базы. Правки JSX, новые окна, элементы дизайна и новые проверки ожидания WB в diff отсутствуют. В `.github` добавлены зависимости/тесты упаковки программы, вызовов скана там нет.

Для одного ключа две вкладки по-прежнему опираются на серверную аренду, сравнение при транзакционной записи IndexedDB и идемпотентность программы (повторный ключ не создаёт второе задание в том же журнале). Backend и выбор ключа QR в контроллере не менялись. Отдельного доказанного дефекта именно одновременных вкладок в diff не найдено. **Два настоящих браузерных процесса с настоящим backend не запускались**: это чтение контракта и локальные проверки, не полноценная складская приёмка. F1 показывает предел защиты одного ключа при смене журналов.

## Исполненные проверки

| Проверка | Результат |
|---|---|
| Запрошенный набор Vitest: `durableDirectQr.test.ts`, `fbsSequentialPacking*`, `fbsKizAutoReprint.test.ts`, `fbsScanAutoPrint*` | 8 файлов, **162/162 PASS**, 6.48 с. |
| `npx tsc --noEmit -p tsconfig.app.json` | **PASS**, exit 0, ошибок нет. |
| Адресные проверки ревью | **7/7 воспроизведены**, 249 мс на итоговый запуск; в воспроизводителе валидная PNG из native fixture. Семь сценариев фиксируют наблюдаемые дефекты F1–F5. Зелёный результат этих проверок означает воспроизведение ошибки, а не соответствие требованиям. |
| Дополнительные DOM-проверки scan / WMS-636 / assembly | Первый прогон: **44 PASS / 4 FAIL** за 399.49 с; scan — 23/23, assembly — 18/18; WMS-636 — 3/7. В WMS-636 сначала R5 превысил 5 секунд, затем упали R6/R7, R10/R11 и C10 с предупреждениями overlapping act. Сравнение с базой не выполнялось: эти падения **не объявляются дефектом переноса**. Изолированный повтор WMS-636: **7/7 PASS**, exit 0, 92.86 с (из них сбор зависимостей 86.16 с). Повторного падения нет; первый прогон сохранён как ограничение проверки. |

Первая точная команда Vitest остановилась до тестов: `EPERM` на `node_modules/.vite-temp`, поскольку зависимости — ссылка во внешний, недоступный для записи каталог. Повтор выполнен с единственным дополнительным параметром `--configLoader runner`, без правок конфигурации или зависимостей. Точная успешно исполненная команда:

```sh
cd frontend
npx vitest run --configLoader runner src/utils/durableDirectQr.test.ts src/screens/v2/fbsSequentialPacking* src/screens/v2/fbsKizAutoReprint.test.ts src/screens/v2/fbsScanAutoPrint*
npx tsc --noEmit -p tsconfig.app.json
```

Проверки не обращались к рабочему принтеру, не выполняли операции production и не доказывают физический выход бумаги. Сохранённый ниже воспроизводитель использует настоящий frontend-транспорт, но подменяет сеть и хранилище; сценарий двух журналов подтверждён чтением Swift, а не запуском двух реальных Mac-программ.

## Заключение

Перенос **не проходит** перекрёстное ревью. До выпуска нужно закрыть F1–F4 и устранить лишнее ожидание F5, сохранив старый production-повтор и действующую защиту от дубля. После исправлений повторно проверить именно отказ хранения, потерю ответа и оба направления смены версии, включая неверный минутный кэш. Положительные 162 теста и проверка типов этих сценариев не заменяют. P2 не заявлены.

Отчёт оставлен локальным файлом, без commit/push по прямому запрету владельца. Код HEAD не изменён.

## Воспроизводитель адресных проверок

Для повторения временно сохранить код ниже как `frontend/src/utils/wms625ReviewProbe.test.ts`, запустить `npx vitest run --configLoader runner src/utils/wms625ReviewProbe.test.ts` из `frontend`, затем удалить временный файл. В рамках ревью временный файл удалён после проверки; продуктовые исходники не менялись.

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { dispatchDurableQr, directQrHash, type DurableQrInput, type DurableQrAttempt, type QrAttemptStore, type DurableQrTransport } from './durableDirectQr'
import { printDirectQr } from './printDirectQr'
const input: DurableQrInput = { idempotencyKey: 'review-scan', imageDataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'review-scan', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 } }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
function memory() {
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = { get: async key => structuredClone(rows.get(key)), put: async attempt => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) } }
  return { rows, store }
}
function io(fetcher: typeof fetch): DurableQrTransport { return { fetch: fetcher, legacy: printDirectQr, wait: async () => {}, polls: 1, now: Date.now } }
afterEach(() => vi.unstubAllGlobals())
describe('WMS-625 independent review: reproduce defects, not desired behavior', () => {
  it.each(['read', 'write'])('v2 plus IndexedDB %s failure prevents first label', async kind => {
    const { store } = memory()
    if (kind === 'read') store.get = async () => { throw new Error('IndexedDB unavailable') }
    else store.put = async () => { throw new Error('IndexedDB unavailable') }
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json({ app: 'WMS Print Direct', protocolVersion: 2 }))
    await expect(dispatchDurableQr(input, store, io(fetcher))).rejects.toThrow('IndexedDB unavailable')
    expect(fetcher.mock.calls.map(([url]) => String(url))).toEqual(['http://127.0.0.1:17843/health'])
  })
  it('cached v2 replaced by old, lost response: every retry blocked despite old receipt', async () => {
    const { store, rows } = memory()
    let receipt: string | undefined
    let posts = 0
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith('/health')) return json({ app: 'WMS Print Direct', printer: 'old' })
      if (init?.method === 'POST') { posts++; receipt = 'old-1'; throw new TypeError('response lost') }
      return json({}, 404)
    })
    const transport = io(fetcher)
    transport.protocol = { value: 2, at: Date.now() }
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('Нет ответа WMS Print')
    expect(receipt).toBe('old-1')
    expect(rows.get(input.idempotencyKey)?.dispatchStartedAt).toBeGreaterThan(0)
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('не нашёл её в журнале')
    transport.protocol = undefined
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('с журналом заданий')
    expect(posts).toBe(1)
  })
  it('cached v2 replaced by old, known refusal before queue: installing printer still cannot recover', async () => {
    const { store } = memory()
    let posts = 0
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith('/health')) return json({ app: 'WMS Print Direct', printer: 'old' })
      if (init?.method === 'POST') { posts++; return json({ error: 'В системе не выбран принтер по умолчанию' }, 409) }
      return json({}, 404)
    })
    const transport = io(fetcher)
    transport.protocol = { value: 2, at: Date.now() }
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('не выбран принтер')
    // User configures the printer. GET /jobs still returns 404 on old agent.
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('не нашёл её в журнале')
    transport.protocol = undefined
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('с журналом заданий')
    expect(posts).toBe(1)
  })
  it('old cache reaches v2, lost answer, rollback old: same key makes TWO Mac queue jobs', async () => {
    const { store, rows } = memory()
    let version: 1 | 2 = 2
    let submissions = 0
    const modernJournal = new Set<string>(), oldJournal = new Set<string>()
    const fetcher = vi.fn<typeof fetch>(async (_url, init) => {
      const body = JSON.parse(String(init?.body))
      const journal = version === 2 ? modernJournal : oldJournal
      if (!journal.has(body.idempotencyKey)) { journal.add(body.idempotencyKey); submissions++ }
      if (version === 2) throw new TypeError('response lost')
      return json({ receipt: 'old-2' })
    })
    vi.stubGlobal('fetch', fetcher)
    const transport = io(fetcher)
    transport.protocol = { value: 1, at: Date.now() }
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('Нет ответа WMS Print')
    expect(rows.get(input.idempotencyKey)?.dispatchStartedAt).toBeUndefined()
    version = 1
    await dispatchDurableQr(input, store, transport)
    expect(submissions).toBe(2)
    expect(fetcher.mock.calls.map(([, init]) => JSON.parse(String(init?.body)).idempotencyKey)).toEqual(['review-scan', 'review-scan'])
  })
  it('old accepted, answer lost, update v2: matching imported receipt blocks recovery', async () => {
    const { store } = memory()
    let version: 1 | 2 = 1
    const hash = await directQrHash(input, '|58.0x40.0')
    let posts = 0
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith('/health')) return json(version === 1 ? { app: 'WMS Print Direct', printer: 'old' } : { app: 'WMS Print Direct', protocolVersion: 2 })
      if (init?.method === 'POST') { posts++; throw new TypeError('old accepted, response lost') }
      return json({ idempotencyKey: input.idempotencyKey, hash, status: 'accepted', receipt: 'old-1', legacy: true })
    })
    vi.stubGlobal('fetch', fetcher)
    const transport = io(fetcher)
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('Нет ответа WMS Print')
    version = 2
    transport.protocol = undefined
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('старую квитанцию исходной этикетки')
    await expect(dispatchDurableQr(input, store, transport)).rejects.toThrow('старую квитанцию исходной этикетки')
    expect(posts).toBe(1)
  })
  it('unanswered health blocks legacy print and is not cached, even for started jobs', async () => {
    const { store } = memory()
    let rejectHealth!: (reason: Error) => void
    const fetcher = vi.fn<typeof fetch>(() => new Promise((_resolve, reject) => { rejectHealth = reject }))
    const transport = io(fetcher)
    const legacy = vi.fn(async () => {})
    transport.legacy = legacy
    const promise = dispatchDurableQr(input, store, transport)
    await Promise.resolve()
    expect(legacy).not.toHaveBeenCalled()
    rejectHealth(new Error('health timeout'))
    await promise
    expect(legacy).toHaveBeenCalledTimes(1)
    expect(transport.protocol).toBeUndefined()
    fetcher.mockRejectedValue(new Error('health timeout'))
    await dispatchDurableQr(input, store, transport, true)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
```
