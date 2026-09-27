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

describe('WMS-497 F1: защита от повторной печати держится до фактического print()', () => {
  it('второй клик после ответа API, но до iframe.onload/таймера — один запрос, один print(); после завершения повтор снова доступен', async () => {
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
