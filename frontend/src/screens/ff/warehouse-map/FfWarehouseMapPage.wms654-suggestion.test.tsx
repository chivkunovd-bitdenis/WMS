// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { FfWarehouseMapPage } from './FfWarehouseMapPage'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
  root = null
  host = null
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

async function renderPage() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(<FfWarehouseMapPage token="test-token" warehouses={[{ id: 'wh-current', name: 'Основной' }]} isAdmin />)
  })
}

async function settle() {
  await act(async () => { await Promise.resolve() })
}

function response(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mapFixture() {
  return {
    warehouses: [{ id: 'wh-current', name: 'Основной' }],
    sellers: [], categories: [],
    // This code belongs to side 1 without a tier. Its text is ambiguous with
    // a tier-1 address, therefore only the server's coordinate-aware result is
    // authoritative for the dialog below.
    cells: [{ id: 'side-only', code: 'А 1.9', barcode: 'LOC-1', qty: 0, children: [] }],
    unassigned: [], journal: [],
  }
}

function testId(id: string) {
  return document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
}

function requiredField(label: string) {
  const labels = [...document.querySelectorAll<HTMLLabelElement>('label')]
  const control = labels.find((element) => element.textContent?.replace(/\s*\*$/, '').trim() === label)?.control
  expect(control, `Visible form must expose ${label}`).not.toBeNull()
  return control as HTMLInputElement
}

async function click(element: Element | null) {
  expect(element, 'Visible action must be present').not.toBeNull()
  await act(async () => (element as HTMLElement).click())
}

async function input(element: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

function suggestionUrls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls
    .map(([input]) => String(input))
    .filter((url) => url.includes('/locations/suggest'))
    .map((url) => new URL(url, 'http://wms.test'))
}

describe('WMS-654 real warehouse-map suggestion contract', () => {
  it('C2 uses the server suggestion scoped to active side/tier instead of ambiguous map code text', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/warehouses/wh-current/map')) return response(mapFixture())
      if (url.includes('/locations/suggest')) return response({ position: 1, code: 'А 1.1' })
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await renderPage()
    await settle()
    await click(testId('warehouse-map-create-cell'))
    await input(requiredField('Стеллаж'), 'А')
    await click(requiredField('Учитывать стороны'))
    await settle()

    const urls = suggestionUrls(fetchMock)
    const active = urls.at(-1)
    expect(active, 'The real page must request the authoritative suggestion').toBeDefined()
    expect(active!.pathname).toBe('/api/warehouses/wh-current/locations/suggest')
    expect(active!.searchParams.get('rack_name')).toBe('А')
    expect(active!.searchParams.get('use_sides')).toBe('false')
    expect(active!.searchParams.get('use_tiers')).toBe('true')
    expect(active!.searchParams.has('side')).toBe(false)
    expect(active!.searchParams.get('tier')).toBe('1')
    expect(requiredField('Позиция').value).toBe('1')
    expect(testId('warehouse-map-cell-preview')?.textContent).toContain('А 1.1')
  })

  it('C7 ignores a late previous-rack response and keeps the manual position in the current row', async () => {
    const pending: Array<(value: Response) => void> = []
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/warehouses/wh-current/map')) return Promise.resolve(response(mapFixture()))
      if (url.includes('/locations/suggest')) return new Promise<Response>((resolve) => pending.push(resolve))
      return Promise.reject(new Error(`Unexpected request: ${url}`))
    })
    vi.stubGlobal('fetch', fetchMock)

    await renderPage()
    await settle()
    await click(testId('warehouse-map-create-cell'))
    await input(requiredField('Стеллаж'), 'А')
    await input(requiredField('Стеллаж'), 'Б')
    await input(requiredField('Позиция'), '42')

    expect(suggestionUrls(fetchMock)).toHaveLength(2)
    await act(async () => pending[1]!(response({ position: 7, code: 'Б 1.1.7' })))
    await act(async () => pending[0]!(response({ position: 99, code: 'А 1.1.99' })))

    expect(requiredField('Позиция').value).toBe('42')
    expect(testId('warehouse-map-cell-preview')?.textContent).toContain('Б 1.1.42')
  })
})
