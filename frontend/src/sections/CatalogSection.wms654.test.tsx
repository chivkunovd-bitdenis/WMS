// @vitest-environment jsdom
import { act, type ComponentProps, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { CatalogSection } from './CatalogSection'
import { FfWarehouseMapScreen } from '../screens/ff/warehouse-map/FfWarehouseMapScreen'

// Import the same three real icons directly; avoid loading the entire icon catalog.
vi.mock('@mui/icons-material', async () => ({
  DeleteOutlined: (await import('@mui/icons-material/DeleteOutlined')).default,
  EditOutlined: (await import('@mui/icons-material/EditOutlined')).default,
  PrintOutlined: (await import('@mui/icons-material/PrintOutlined')).default,
}))

// Barcode drawing is an external canvas boundary; the real print dialog stays mounted.
vi.mock('jsbarcode', () => ({ default: vi.fn() }))

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

async function render(node: ReactNode) {
  if (!root) {
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
  }
  await act(async () => root!.render(node))
}
async function click(element: Element | null) {
  expect(element, 'Visible action must be present').not.toBeNull()
  await act(async () => (element as HTMLElement).click())
}
function testId(id: string) {
  return document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
}
function field(label: string): HTMLInputElement | null {
  const labels = [...document.querySelectorAll<HTMLLabelElement>('label')]
  const found = labels.find(element => element.textContent?.replace(/\s*\*$/, '').trim() === label)
  return (found?.control ?? found?.querySelector('input')) as HTMLInputElement | null ?? null
}
function requiredField(label: string) {
  const input = field(label)
  expect(input, `Form must expose ${label}`).not.toBeNull()
  return input!
}
async function input(element: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
function preview() {
  const input = testId('location-code')?.querySelector('input')
  return input?.value ?? testId('warehouse-map-cell-preview')?.textContent?.replace('Код ячейки: ', '').trim()
}
async function selectSide2() {
  const toggle = testId('location-side-2')
  if (toggle) return click(toggle)
  const nativeSelect = document.querySelector<HTMLSelectElement>('[role="dialog"] select')
  if (nativeSelect) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(nativeSelect, '2')
      nativeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    return
  }
  const combobox = document.querySelector<HTMLElement>('[role="dialog"] [role="combobox"]')
  expect(combobox).not.toBeNull()
  await act(async () => combobox!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const option = [...document.querySelectorAll('[role="option"]')].find(x => x.textContent === 'Сторона 2')
  await click(option ?? null)
}

function catalogProps(): ComponentProps<typeof CatalogSection> {
  const noop = () => undefined
  return {
    isFulfillmentAdmin: true, catalogBusy: false, catalogError: null,
    sellers: [], warehouses: [{ id: 'wh', name: 'Основной', code: 'main' }],
    locations: [{ id: 'old', code: 'OLD-01', warehouse_id: 'wh', barcode: 'LOC-OLD' }],
    selectedWarehouseId: 'wh', setSelectedWarehouseId: noop, products: [],
    onCreateWarehouse: noop, onCreateLocation: vi.fn(async () => true),
    onRenameWarehouse: vi.fn(async () => true), onDeleteWarehouse: vi.fn(async () => true),
    onRenameLocation: vi.fn(async () => true), onDeleteLocation: vi.fn(async () => true),
    onLoadLocationBalances: vi.fn(async () => []), onListWarehouseRacks: vi.fn(async () => ['А', 'Б']),
    onSuggestLocation: vi.fn(async () => null), onCreateProduct: noop,
    wbSellerId: null, setWbSellerId: noop, wbHasContentToken: false, wbHasSuppliesToken: false,
    wbTokensBusy: false, wbSyncBusy: false, wbSuppliesSyncBusy: false, wbLinkBusy: false,
    wbJobStatus: null, wbJobResult: null, wbSuppliesJobStatus: null, wbSuppliesJobResult: null,
    wbImportedCards: [], wbImportedSupplies: [], onSaveWbTokens: noop,
    onStartWbCardsSyncJob: noop, onStartWbSuppliesSyncJob: noop, onLinkProductToWb: noop,
  }
}
function mapProps(): ComponentProps<typeof FfWarehouseMapScreen> {
  return {
    data: { warehouses: [{ id: 'wh', name: 'Основной' }], sellers: [], categories: [],
      cells: [], unassigned: [], journal: [] },
    loading: false, error: null, warehouseId: 'wh',
    onWarehouseChange: vi.fn(), onMove: vi.fn(), onCreateCell: vi.fn(),
    onCreateWarehouse: vi.fn(), onPrintCell: vi.fn(), onInventory: vi.fn(), historyFor: () => [],
  }
}

async function configure(useSides: boolean, useTiers: boolean) {
  expect(requiredField('Учитывать стороны').checked).toBe(true)
  expect(requiredField('Учитывать ярусы').checked).toBe(true)
  expect(requiredField('Ярус').value).toBe('1')
  const defaultSide = testId('location-side-1')
  if (defaultSide) expect(defaultSide.getAttribute('aria-pressed')).toBe('true')
  else expect(field('Сторона')?.value).toBe('1')
  await input(requiredField('Стеллаж'), 'А')
  await selectSide2()
  await input(requiredField('Ярус'), '3')
  if (!useSides) await click(requiredField('Учитывать стороны'))
  if (!useTiers) await click(requiredField('Учитывать ярусы'))
  expect(field('Ярус') !== null).toBe(useTiers)
  expect(document.querySelector('[aria-label="side"]') !== null || testId('warehouse-map-cell-side') !== null || field('Сторона') !== null).toBe(useSides)
  await input(requiredField('Позиция'), '4')
}

function assertCoordinates(value: unknown, useSides: boolean, useTiers: boolean, code: string) {
  expect(value).toEqual(expect.objectContaining({ rack_name: 'А', position: 4 }))
  const body = value as Record<string, unknown>
  expect(body.side ?? null).toBe(useSides ? 2 : null)
  expect(body.tier ?? null).toBe(useTiers ? 3 : null)
  if (!useSides) expect(body.side === null || body.use_sides === false).toBe(true)
  if (!useTiers) expect(body.tier === null || body.use_tiers === false).toBe(true)
  if ('code' in body) expect(body.code).toBe(code)
}

const combinations = [
  [false, false, 'А 4'], [true, false, 'А 2.4'],
  [false, true, 'А 3.4'], [true, true, 'А 2.3.4'],
] as const

describe('WMS-654 actual CatalogSection contract', () => {
  it.each(combinations)('C6 independent coordinates sides=%s tiers=%s', async (sides, tiers, code) => {
    const props = catalogProps()
    await render(<CatalogSection {...props} />)
    await click(testId('create-location'))
    await configure(sides, tiers)
    expect(preview()).toBe(code)
    await click(testId('location-submit'))
    expect(props.onCreateLocation).toHaveBeenCalledTimes(1)
    assertCoordinates(vi.mocked(props.onCreateLocation).mock.calls[0][0], sides, tiers, code)
  })

  it('C7 failure keeps inputs, retry allows correction and refresh keeps neighboring cells', async () => {
    const props = catalogProps()
    vi.mocked(props.onCreateLocation).mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    await render(<CatalogSection {...props} />)
    await click(testId('create-location'))
    await configure(true, true)
    await click(testId('location-submit'))
    expect(testId('location-form')).not.toBeNull()
    expect(requiredField('Ярус').value).toBe('3')
    expect(requiredField('Позиция').value).toBe('4')
    await input(requiredField('Позиция'), '5')
    expect(preview()).toBe('А 2.3.5')
    await click(testId('location-submit'))
    expect(props.onCreateLocation).toHaveBeenCalledTimes(2)
    expect(vi.mocked(props.onCreateLocation).mock.calls[1][0]).toEqual(expect.objectContaining({ position: 5, tier: 3, side: 2 }))
    await render(<CatalogSection {...props} locations={[...props.locations,
      { id: 'new', code: 'А 2.3.5', warehouse_id: 'wh', barcode: 'LOC-NEW' }]} />)
    const rows = [...document.querySelectorAll('[data-testid="location-row"]')].map(x => x.textContent)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toContain('OLD-01')
    expect(rows[0]).toContain('LOC-OLD')
    expect(rows[1]).toContain('А 2.3.5')
    expect(rows[1]).toContain('LOC-NEW')
  })

  it('C4/C7 manual position survives suggestion response and context change does not reuse it', async () => {
    const props = catalogProps()
    let resolveSuggestion!: (value: { position: number; code: string }) => void
    vi.mocked(props.onSuggestLocation).mockImplementation(() => new Promise(resolve => { resolveSuggestion = resolve }))
    await render(<CatalogSection {...props} />)
    await click(testId('create-location'))
    await input(requiredField('Стеллаж'), 'А')
    await input(requiredField('Позиция'), '42')
    await act(async () => resolveSuggestion({ position: 2, code: 'А 1.1.2' }))
    expect(requiredField('Позиция').value).toBe('42')
    expect(preview()).toBe('А 1.1.42')
    await input(requiredField('Стеллаж'), 'Б')
    await act(async () => resolveSuggestion({ position: 7, code: 'Б 1.1.7' }))
    expect(requiredField('Позиция').value).toBe('7')
    expect(preview()).toBe('Б 1.1.7')
  })

  it('C2/C7 late response from a previous row cannot overwrite the current suggestion', async () => {
    const props = catalogProps()
    const pending: Array<(value: { position: number; code: string }) => void> = []
    vi.mocked(props.onSuggestLocation).mockImplementation(() => new Promise(resolve => pending.push(resolve)))
    await render(<CatalogSection {...props} />)
    await click(testId('create-location'))
    await input(requiredField('Стеллаж'), 'А')
    await input(requiredField('Стеллаж'), 'Б')
    expect(pending).toHaveLength(2)
    await act(async () => pending[1]({ position: 7, code: 'Б 1.1.7' }))
    await act(async () => pending[0]({ position: 99, code: 'А 1.1.99' }))
    expect(preview()).toBe('Б 1.1.7')
    expect(requiredField('Позиция').value).toBe('7')
  })

  it('C10 refreshed saved cell prints its original barcode through existing dialog', async () => {
    const props = catalogProps()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ fillRect: vi.fn() } as unknown as CanvasRenderingContext2D)
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,test')
    await render(<CatalogSection {...props} />)
    const saved = { id: 'new', code: 'А 2.3.4', warehouse_id: 'wh', barcode: 'LOC-PERSISTED' }
    await render(<CatalogSection {...props} locations={[...props.locations, saved]} />)
    const row = document.querySelector('[data-location-id="new"]')!
    await click(row.querySelector('[data-testid="location-print"]'))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 80)) })
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('LOC-PERSISTED')
    expect((testId('location-print-action') as HTMLButtonElement).disabled).toBe(false)
    const { default: barcode } = await import('jsbarcode')
    expect(barcode).toHaveBeenCalledWith(expect.any(HTMLCanvasElement), 'LOC-PERSISTED', expect.any(Object))
    expect(props.onRenameLocation).not.toHaveBeenCalled()
    expect(props.onDeleteLocation).not.toHaveBeenCalled()
  })
})

describe('WMS-654 real map form openings', () => {
  it('C7 map creation failure keeps the form and selected coordinates for retry', async () => {
    const props = mapProps()
    const onCreate = vi.fn(async (_body: unknown) => false)
    await render(<FfWarehouseMapScreen {...props} onCreateCell={onCreate} />)
    await click(testId('warehouse-map-create-cell'))
    await configure(true, true)
    await click(testId('warehouse-map-cell-submit'))
    expect(onCreate).toHaveBeenCalledTimes(1)
    expect(testId('warehouse-map-cell-dialog')).not.toBeNull()
    expect(requiredField('Ярус').value).toBe('3')
    expect(requiredField('Позиция').value).toBe('4')
    await input(requiredField('Позиция'), '5')
    await click(testId('warehouse-map-cell-submit'))
    expect(onCreate).toHaveBeenCalledTimes(2)
    expect(onCreate.mock.calls[1][0]).toEqual(expect.objectContaining({ position: 5, tier: 3, side: 2 }))
  })
  for (const entry of ['warehouse-map-create-cell', 'warehouse-map-create-first-cell']) {
    it.each(combinations)(`C6 ${entry} sides=%s tiers=%s`, async (sides, tiers, code) => {
      const props = mapProps()
      await render(<FfWarehouseMapScreen {...props} />)
      await click(testId(entry))
      expect(testId('warehouse-map-cell-dialog')).not.toBeNull()
      await configure(sides, tiers)
      expect(preview()).toBe(code)
      await click(testId('warehouse-map-cell-submit'))
      expect(props.onCreateCell).toHaveBeenCalledTimes(1)
      assertCoordinates(vi.mocked(props.onCreateCell).mock.calls[0][0], sides, tiers, code)
    })
  }
})
