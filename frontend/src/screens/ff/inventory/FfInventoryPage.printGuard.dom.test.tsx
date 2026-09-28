// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { FfInventoryPage } from './FfInventoryPage'

// WMS-497, ревью Astra №1 (F1): второе нажатие «Печать листа» ПОСЛЕ ответа
// сервера, но ДО того, как браузер фактически вызвал печать (iframe должен
// сперва загрузиться, потом ждёт ещё 100 мс), не должно уходить вторым
// запросом и не должно открывать второе окно печати. До исправления
// printingRef снимался сразу после синхронного возврата printInventorySheet,
// то есть раньше, чем происходил сам print() — здесь воспроизводим точно
// этот промежуток на настоящем FfInventoryPage, а не на реконструкции кода.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const DOC_ID = '11111111-1111-4111-8111-111111111111'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

const listSummary = {
  id: DOC_ID,
  number: 'ИНВ-1111',
  status: 'draft',
  warehouse_name: 'Склад',
  fill_label: 'Все',
  created_at: '2026-09-27T10:00:00',
  created_by: 'Тест',
  lines: 0,
  counted: 0,
  discrepancies: 0,
  surplus: 0,
  shortage: 0,
}

const docDetail = {
  id: DOC_ID,
  number: 'ИНВ-1111',
  status: 'draft',
  warehouse_id: null,
  warehouse_name: 'Склад',
  fill: { mode: 'all', seller_id: null, category: null, object_label: null },
  created_at: '2026-09-27T10:00:00',
  created_by: 'Тест',
  posted_at: null,
  posted_by: null,
  comment: '',
  address_storage: true,
  cells: [],
}

const printSheetBody = {
  number: 'ИНВ-1111',
  created_at: '2026-09-27T10:00:00',
  created_by: 'Тест',
  filters: { object: true, warehouse_name: null, seller_name: null, category: null, product_articles: [] },
  rows: [],
}

let root: Root | null = null
let host: HTMLDivElement | null = null
async function mount(element: React.ReactElement) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(element)
  })
}
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const $ = (testId: string): HTMLElement => {
  const el = document.querySelector(`[data-testid="${testId}"]`)
  if (!el) throw new Error(`no element ${testId}`)
  return el as HTMLElement
}
async function click(testId: string) {
  await act(async () => {
    $(testId).click()
  })
}
const tick = () => act(async () => {
  await Promise.resolve()
})

/** Тот же роутер fetch нужен обоим сценариям (F1 и F2) — вынесен один раз. */
function stubFetchForOneDocument() {
  const printSheetRequests: Array<{ resolve: (body: unknown) => void }> = []
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/operations/inventory-counts')) {
      return Promise.resolve(new Response(JSON.stringify([listSummary]), { status: 200 }))
    }
    if (url.endsWith('/api/products/categories')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
    }
    if (url.endsWith('/api/products/ff-catalog')) {
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
    }
    if (url.endsWith(`/api/operations/inventory-counts/${DOC_ID}`)) {
      return Promise.resolve(new Response(JSON.stringify(docDetail), { status: 200 }))
    }
    if (url.endsWith(`/api/operations/inventory-counts/${DOC_ID}/print-sheet`)) {
      const d = deferred<Response>()
      printSheetRequests.push({
        resolve: (body) => d.resolve(new Response(JSON.stringify(body), { status: 200 })),
      })
      return d.promise
    }
    throw new Error(`неожиданный fetch: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return printSheetRequests
}

describe('WMS-497 F1: защита от повторной печати держится до фактического print()', () => {
  it('второй клик после ответа API, но до iframe.onload/таймера — один запрос, один print(); после завершения повтор снова доступен', async () => {
    const printSheetRequests = stubFetchForOneDocument()

    await mount(<FfInventoryPage token="t" sellers={[]} warehouses={[]} />)
    await click(`inv-open-${DOC_ID}`)
    await tick()
    expect($('inv-print-sheet')).toBeTruthy()

    // первый клик — уходит первый запрос к print-sheet
    await click('inv-print-sheet')
    expect(printSheetRequests).toHaveLength(1)

    // сервер ответил, но само окно печати ещё не готово: iframe только что
    // создан, onload и 100-миллисекундный таймер ещё не наступили.
    await act(async () => {
      printSheetRequests[0]!.resolve(printSheetBody)
    })
    const iframe = document.body.querySelector('iframe')
    expect(iframe).toBeTruthy()
    const frameWindow = iframe!.contentWindow as Window
    const printSpy = vi.spyOn(frameWindow, 'print').mockImplementation(() => {})
    vi.spyOn(frameWindow, 'focus').mockImplementation(() => {})

    // ВТОРОЙ клик именно в этом промежутке — второго запроса быть не должно.
    await click('inv-print-sheet')
    expect(printSheetRequests).toHaveLength(1)
    expect(printSpy).not.toHaveBeenCalled()

    // Даём iframe «догрузиться» и таймеру пройти — печать должна случиться ровно один раз.
    await act(async () => {
      ;(iframe as unknown as { onload: () => void }).onload()
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(printSpy).toHaveBeenCalledTimes(1)

    // Печать состоялась — намеренный повторный клик снова доступен и уходит новым запросом.
    await click('inv-print-sheet')
    expect(printSheetRequests).toHaveLength(2)
  })
})

// WMS-497, ревью Astra №2 (F2): если загрузка iframe обрывается раньше
// onload, промис раньше не разрешался никогда — кнопка оставалась
// заблокированной до перезагрузки страницы. Тот же настоящий компонент,
// что и в блоке F1 выше, только на этот раз iframe.onload вообще не вызываем.
describe('WMS-497 F2: обрыв загрузки iframe не блокирует кнопку навсегда', () => {
  it('onload не наступает → отказ по ограниченному ожиданию → кнопка снова доступна → новый запрос работает; поздний onload старой попытки не печатает', async () => {
    const printSheetRequests = stubFetchForOneDocument()

    await mount(<FfInventoryPage token="t" sellers={[]} warehouses={[]} />)
    await click(`inv-open-${DOC_ID}`)
    await tick()
    expect($('inv-print-sheet')).toBeTruthy()

    // Поддельные таймеры — уже здесь: printInventorySheet ставит свой
    // setTimeout ограниченного ожидания загрузки внутри обработчика клика,
    // и он обязан попасть под подмену с самого начала. Включать её позже
    // (после клика) бессмысленно — таймер к этому моменту уже поставлен
    // настоящим setTimeout и продвижением виртуального времени не тронется
    // (так и было в первой версии этого теста — кнопка оставалась disabled).
    vi.useFakeTimers()
    try {
      await click('inv-print-sheet')
      expect(printSheetRequests).toHaveLength(1)

      await act(async () => {
        printSheetRequests[0]!.resolve(printSheetBody)
      })
      const iframe = document.body.querySelector('iframe')
      expect(iframe).toBeTruthy()
      // Пока попытка «готовится» — кнопка отключена (F1: второй клик не проходит).
      expect(($('inv-print-sheet') as HTMLButtonElement).disabled).toBe(true)

      // Загрузка не наступает вовсе: ни onload, ни error.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20100)
      })

      // Отказ по ограниченному ожиданию — кнопка снова доступна, iframe убран.
      expect(($('inv-print-sheet') as HTMLButtonElement).disabled).toBe(false)
      expect(document.body.contains(iframe)).toBe(false)

      // Новый клик после отказа — новый (второй) запрос уходит по-настоящему.
      await click('inv-print-sheet')
      expect(printSheetRequests).toHaveLength(2)

      // Поздний onload СТАРОЙ (первой, уже брошенной) попытки печати не делает.
      const oldFrameWindow = iframe!.contentWindow as Window | null
      const printSpy = oldFrameWindow ? vi.spyOn(oldFrameWindow, 'print').mockImplementation(() => {}) : null
      expect((iframe as unknown as { onload: unknown }).onload).toBeNull()
      iframe!.dispatchEvent(new Event('load'))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200)
      })
      expect(printSpy ? printSpy.mock.calls.length : 0).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })
})

// WMS-497, ревью Astra №3 (F2, оставшаяся часть): отказ, пришедший ПОСЛЕ
// onload (когда таймер печати уже поставлен), должен отменять и его — иначе
// старая (уже брошенная) попытка печатает поверх новой. Ровно сценарий
// воспроизведения из отчёта ревью: попытка A получает onload, затем error
// через 50 мс — печатать должна только следующая попытка B, ни разу не A.
describe('WMS-497 F2 (оставшаяся часть): отказ после onload отменяет уже поставленную печать этой попытки', () => {
  it('A: onload → error(50 мс) — A не печатает, кнопка снова доступна; B: новый клик печатает один раз, A — ноль', async () => {
    const printSheetRequests = stubFetchForOneDocument()

    await mount(<FfInventoryPage token="t" sellers={[]} warehouses={[]} />)
    await click(`inv-open-${DOC_ID}`)
    await tick()
    expect($('inv-print-sheet')).toBeTruthy()

    vi.useFakeTimers()
    try {
      // Попытка A.
      await click('inv-print-sheet')
      expect(printSheetRequests).toHaveLength(1)
      await act(async () => {
        printSheetRequests[0]!.resolve(printSheetBody)
      })
      const iframeA = document.body.querySelector('iframe')!
      const printSpyA = vi.spyOn(iframeA.contentWindow as Window, 'print').mockImplementation(() => {})
      vi.spyOn(iframeA.contentWindow as Window, 'focus').mockImplementation(() => {})

      ;(iframeA as unknown as { onload: () => void }).onload()
      // Отказ приходит через 50 мс — таймер печати A (100 мс) уже поставлен,
      // но ещё не сработал.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50)
      })
      ;(iframeA as unknown as { onerror: () => void }).onerror()
      await tick()

      // A брошена — кнопка снова доступна, iframe A убран.
      expect(($('inv-print-sheet') as HTMLButtonElement).disabled).toBe(false)
      expect(document.body.contains(iframeA)).toBe(false)

      // Ждём дольше, чем был бы таймер печати A, — печати всё равно не случилось.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(printSpyA).not.toHaveBeenCalled()

      // Попытка B — новый клик, новый запрос, настоящая загрузка.
      await click('inv-print-sheet')
      expect(printSheetRequests).toHaveLength(2)
      await act(async () => {
        printSheetRequests[1]!.resolve(printSheetBody)
      })
      const iframeB = document.body.querySelector('iframe')!
      expect(iframeB).not.toBe(iframeA)
      const printSpyB = vi.spyOn(iframeB.contentWindow as Window, 'print').mockImplementation(() => {})
      vi.spyOn(iframeB.contentWindow as Window, 'focus').mockImplementation(() => {})

      ;(iframeB as unknown as { onload: () => void }).onload()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(150)
      })

      expect(printSpyB).toHaveBeenCalledTimes(1)
      expect(printSpyA).not.toHaveBeenCalled()
      expect(($('inv-print-sheet') as HTMLButtonElement).disabled).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
