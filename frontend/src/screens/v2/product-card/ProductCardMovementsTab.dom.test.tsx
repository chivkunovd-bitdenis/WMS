// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ProductCardMovementsTab } from './ProductCardMovementsTab'
import type { MovementRow } from '../../../components/ProductMovementsTable'

// WMS-490 D4, R8–R9: вкладка «Движения» карточки товара — та же таблица, что
// в отчёте «Остатки и движения», но без периода и с догрузкой страниц вместо
// «показаны первые N». Здесь проверяется именно догрузка (без повторов и
// пропусков, без двойного запроса при быстром двойном нажатии) и пустое
// состояние. Основная разметка таблицы (колонки, ссылки на документы) —
// общий компонент `ProductMovementsTable`, его использует и отчёт без
// изменений (см. FfReportsPage.test.tsx).

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

function movement(id: string, quantity = 1): MovementRow {
  return {
    id,
    at: '2026-09-20T10:00:00+03:00',
    operation: 'Приёмка',
    quantity,
    document: { kind: 'inbound', id: `doc-${id}`, number: `ПРИЕМ-${id}` },
  }
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
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const $ = <T extends HTMLElement = HTMLElement>(testId: string): T => {
  const el = document.querySelector<T>(`[data-testid="${testId}"]`)
  if (!el) throw new Error(`no element ${testId}`)
  return el
}
const maybe = (testId: string) => document.querySelector(`[data-testid="${testId}"]`)
async function click(testId: string) {
  await act(async () => { $(testId).click() })
}
const tick = () => act(async () => { await Promise.resolve() })

/** Отложенный ответ: тест сам решает, когда именно он придёт. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function baseProps(overrides: Partial<Parameters<typeof ProductCardMovementsTab>[0]> = {}) {
  return {
    productId: 'p-1',
    token: 't',
    authHeaders: (t: string) => ({ Authorization: `Bearer ${t}` }),
    onNotFound: () => {},
    ...overrides,
  }
}

describe('WMS-490 R9: догрузка страниц', () => {
  it('первая страница, «Загрузить ещё», вторая страница — без повторов и пропусков, кнопка исчезает', async () => {
    const calls: string[] = []
    const fetchMock = vi.fn(async (url: string) => {
      calls.push(url)
      if (url.includes('page=2')) {
        return new Response(
          JSON.stringify({ rows: [movement('m3'), movement('m4')], truncated: false, total: 4, page: 2 }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({ rows: [movement('m1'), movement('m2')], truncated: true, total: 4, page: 1 }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    await mount(<ProductCardMovementsTab {...baseProps()} />)
    await tick()

    expect(document.body.textContent).toContain('ПРИЕМ-m1')
    expect(document.body.textContent).toContain('ПРИЕМ-m2')
    expect(document.body.textContent).not.toContain('ПРИЕМ-m3')
    expect($('product-card-movements-load-more')).not.toBeNull()

    await click('product-card-movements-load-more')
    await tick()

    expect(document.body.textContent).toContain('ПРИЕМ-m1')
    expect(document.body.textContent).toContain('ПРИЕМ-m2')
    expect(document.body.textContent).toContain('ПРИЕМ-m3')
    expect(document.body.textContent).toContain('ПРИЕМ-m4')
    // Каждая строка встречается ровно один раз — ни повторов, ни пропусков.
    for (const id of ['m1', 'm2', 'm3', 'm4']) {
      const occurrences = document.body.querySelectorAll(`[data-row-key="${id}"]`)
      expect(occurrences.length).toBe(1)
    }
    expect(maybe('product-card-movements-load-more')).toBeNull()
    expect(calls.filter((u) => u.includes('page=2')).length).toBe(1)
  })

  it('быстрое двойное нажатие «Загрузить ещё» уходит одним запросом', async () => {
    const secondPage = deferred<Response>()
    let secondPageCalls = 0
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('page=2')) {
        secondPageCalls += 1
        return secondPage.promise
      }
      return new Response(
        JSON.stringify({ rows: [movement('m1')], truncated: true, total: 3, page: 1 }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    await mount(<ProductCardMovementsTab {...baseProps()} />)
    await tick()

    // Два клика подряд без ожидания ответа между ними — ровно как быстрый
    // двойной щелчок оператора.
    await act(async () => {
      $('product-card-movements-load-more').click()
      $('product-card-movements-load-more').click()
    })

    expect(secondPageCalls).toBe(1)

    await act(async () => {
      secondPage.resolve(
        new Response(JSON.stringify({ rows: [movement('m2'), movement('m3')], truncated: false, total: 3, page: 2 }), { status: 200 }),
      )
      await secondPage.promise
    })
    await tick()

    for (const id of ['m1', 'm2', 'm3']) {
      expect(document.body.querySelectorAll(`[data-row-key="${id}"]`).length).toBe(1)
    }
    expect(maybe('product-card-movements-load-more')).toBeNull()
  })
})

describe('WMS-490 R9: пустое состояние и ошибка', () => {
  it('у товара нет движений — таблица с заголовком «Движений нет», без кнопки догрузки', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ rows: [], truncated: false, total: 0, page: 1 }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await mount(<ProductCardMovementsTab {...baseProps()} />)
    await tick()

    expect(document.body.textContent).toContain('Движений нет')
    expect(maybe('product-card-movements-load-more')).toBeNull()
  })

  it('сбой первой страницы — сообщение об ошибке с повтором, а не пустая таблица', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: 'boom' }), { status: 500 }))
    vi.stubGlobal('fetch', fetchMock)

    await mount(<ProductCardMovementsTab {...baseProps()} />)
    await tick()

    expect($('product-card-movements-error')).not.toBeNull()
    expect(maybe('product-card-movements-tab')).toBeNull()
  })
})
