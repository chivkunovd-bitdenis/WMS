import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WarehouseContextSwitch, WarehouseNoContextState } from '../../ui-kit'
import { FfPackagingPage, FfPackagingTaskPanel, type PackagingTask } from './FfPackagingPage'

const reactHarness = vi.hoisted(() => ({
  cursor: 0,
  effects: [] as Array<() => void | (() => void)>,
  states: [] as unknown[],
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useCallback: <Callback extends (...args: never[]) => unknown>(callback: Callback) => callback,
    useEffect: (effect: () => void | (() => void)) => {
      reactHarness.effects.push(effect)
    },
    useState: (initial: unknown) => {
      const index = reactHarness.cursor
      reactHarness.cursor += 1
      if (reactHarness.states[index] === undefined) {
        reactHarness.states[index] = typeof initial === 'function'
          ? (initial as () => unknown)()
          : initial
      }
      const setState = (next: unknown) => {
        reactHarness.states[index] = typeof next === 'function'
          ? (next as (previous: unknown) => unknown)(reactHarness.states[index])
          : next
      }
      return [reactHarness.states[index], vi.fn(setState)]
    },
  }
})

const routeHarness = vi.hoisted(() => ({
  navigate: vi.fn(),
  taskId: null as string | null,
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useLocation: () => ({
      pathname: routeHarness.taskId ? `/app/ff/packaging/${routeHarness.taskId}` : '/app/ff/packaging',
      search: '',
      hash: '',
      state: null,
      key: 'test',
    }),
    useNavigate: () => routeHarness.navigate,
    useParams: () => routeHarness.taskId ? { taskId: routeHarness.taskId } : {},
  }
})

type TestElementProps = {
  children?: ReactNode
  options?: Array<{ id: string; name: string }>
  value?: string | null
  onChange?: (warehouseId: string) => void
  disabledReason?: string
  task?: PackagingTask
}

const warehouses = [
  { id: 'north', name: 'Склад Север' },
  { id: 'south', name: 'Склад Юг' },
]

const northTask = packagingTask({
  id: 'task-north',
  warehouseId: 'north',
  warehouseName: 'Склад Север',
  productName: 'Товар Севера',
})

const southTask = packagingTask({
  id: 'task-south',
  warehouseId: 'south',
  warehouseName: 'Склад Юг',
  productName: 'Товар Юга',
})

function packagingTask({
  id,
  warehouseId,
  warehouseName,
  productName,
}: {
  id: string
  warehouseId: string
  warehouseName: string
  productName: string
}): PackagingTask {
  return {
    id,
    document_number: id,
    warehouse_id: warehouseId,
    warehouse_name: warehouseName,
    warehouse_code: warehouseId,
    seller_name: 'Тестовый селлер',
    status: 'draft',
    marketplace_unload_request_id: null,
    inbound_intake_request_id: null,
    is_complete: false,
    lines: [{
      id: `${id}-line`,
      product_id: `${id}-product`,
      sku_code: `${id}-sku`,
      product_name: productName,
      storage_location_id: `${id}-location`,
      storage_location_code: warehouseId === 'north' ? 'N-01' : 'S-01',
      packaging_instructions: null,
      requires_honest_sign: false,
      qty_total: 1,
      qty_suggested_packed: 0,
      qty_confirmed_packed: 0,
      qty_need_pack: 1,
      qty_packed_in_task: 0,
      qty_done: 0,
      qty_marking_printed: 0,
      qty_marking_external: 0,
      qty_product_label_printed: 0,
      marking_available_count: 0,
      is_complete: false,
    }],
  }
}

function renderPage(selectedWarehouseId: string | null, onWarehouseChange = vi.fn()) {
  reactHarness.cursor = 0
  reactHarness.effects = []
  return FfPackagingPage({
    token: 'test-token',
    warehouses,
    selectedWarehouseId,
    onWarehouseChange,
  })
}

function runEffects(): void {
  const effects = reactHarness.effects.splice(0)
  effects.forEach((effect) => effect())
}

function findByType(node: ReactNode, component: unknown): ReactElement<TestElementProps> | null {
  if (!isValidElement<TestElementProps>(node)) return null
  if (node.type === component) return node

  for (const child of Children.toArray(node.props.children)) {
    const match = findByType(child, component)
    if (match) return match
  }
  return null
}

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!isValidElement<TestElementProps>(node)) return ''
  return Children.toArray(node.props.children).map(textContent).join('')
}

describe('FfPackagingPage warehouse queue contract', () => {
  beforeEach(() => {
    reactHarness.states = []
    routeHarness.navigate.mockReset()
    routeHarness.taskId = null
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('S-14-TC-001 uses the shared warehouse props and replaces the queue after a warehouse change', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/operations/packaging-tasks?')) {
        const task = new URL(url, 'http://wms.test').searchParams.get('warehouse_id') === 'south'
          ? southTask
          : northTask
        return new Response(JSON.stringify([task]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.includes('/operations/marking-codes/pending-marking?')) {
        return new Response(JSON.stringify({ rows: [], total: 0 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const onWarehouseChange = vi.fn()
    const northTree = renderPage('north', onWarehouseChange)
    const warehouseSwitch = findByType(northTree, WarehouseContextSwitch)
    expect(warehouseSwitch?.props.options).toEqual(warehouses)
    expect(warehouseSwitch?.props.value).toBe('north')

    warehouseSwitch?.props.onChange?.('south')
    expect(onWarehouseChange).toHaveBeenCalledWith('south')

    runEffects()
    await vi.waitFor(() => expect(reactHarness.states[0]).toEqual([northTask]))

    renderPage('south', onWarehouseChange)
    runEffects()
    await vi.waitFor(() => expect(reactHarness.states[0]).toEqual([southTask]))

    const southTree = renderPage('south', onWarehouseChange)
    const visibleQueue = textContent(southTree)
    expect(visibleQueue).toContain('Товар Юга')
    expect(visibleQueue).not.toContain('Товар Севера')

    const queueUrls = fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes('/operations/packaging-tasks?'))
    expect(queueUrls).toHaveLength(2)
    expect(new URL(queueUrls[0], 'http://wms.test').searchParams.get('warehouse_id')).toBe('north')
    expect(new URL(queueUrls[1], 'http://wms.test').searchParams.get('warehouse_id')).toBe('south')
  })

  it('S-14-TC-002 locks the direct-link task to its own warehouse without changing the session queue context', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/operations/packaging-tasks/task-north')) {
        return new Response(JSON.stringify(northTask), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.includes('/operations/packaging-tasks?')) {
        return new Response(JSON.stringify([southTask]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.includes('/operations/marking-codes/pending-marking?')) {
        return new Response(JSON.stringify({ rows: [], total: 0 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    routeHarness.taskId = northTask.id
    const onWarehouseChange = vi.fn()
    renderPage('south', onWarehouseChange)
    runEffects()
    await vi.waitFor(() => expect(reactHarness.states[1]).toEqual(northTask))

    const taskTree = renderPage('south', onWarehouseChange)
    const warehouseSwitch = findByType(taskTree, WarehouseContextSwitch)
    expect(warehouseSwitch?.props.value).toBe('north')
    expect(warehouseSwitch?.props.disabledReason).toBe('Склад закреплён: открыто задание упаковки')

    warehouseSwitch?.props.onChange?.('south')
    expect(onWarehouseChange).not.toHaveBeenCalled()

    const taskPanel = findByType(taskTree, FfPackagingTaskPanel)
    expect(taskPanel?.props.task).toEqual(northTask)
    expect(taskPanel?.props.task?.warehouse_name).toBe('Склад Север')
    expect(taskPanel?.props.task?.lines[0]?.product_name).toBe('Товар Севера')
  })

  it('does not request the queue and shows the existing empty state without warehouse context', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const tree = renderPage(null)
    expect(findByType(tree, WarehouseNoContextState)).not.toBeNull()

    runEffects()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
