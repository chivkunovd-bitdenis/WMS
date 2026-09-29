// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'

const { fetchFbsWorkspace } = vi.hoisted(() => ({ fetchFbsWorkspace: vi.fn() }))
vi.mock('./fbsApi', () => ({ fetchFbsWorkspace, getFbsPickOptions: vi.fn() }))
vi.mock('./FfFbsAssemblyPick', () => ({ FfFbsAssemblyPick: () => <div data-testid="mock-group-pick" /> }))
vi.mock('./FfFbsSupplyWorkspace', () => ({
  FfFbsSupplyWorkspace: ({ supplyId }: { supplyId: string }) => <div data-testid={`mock-packing-${supplyId}`} />,
}))
vi.mock('../../hooks/useScanIntake', () => ({ useScanIntake: () => ({ bindRoot: () => undefined }) }))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const authHeaders = () => ({ Authorization: 'Bearer test' })
const supplyIds = ['supply-a', 'supply-b']

function workspace(id: string, picked: number, total = 2): FbsWorkspace {
  return {
    supply: {
      id, marketplace: 'wb', name: id, wb_supply_id: id,
      seller: { id: id, name: `Селлер ${id}` }, wb_warehouse: { id: 507, name: 'Коледино' },
    },
    progress: { picked, total, packed: 0, metadata_ready: 0, stickers_ready: 0 },
    orders: [],
  } as unknown as FbsWorkspace
}

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  window.sessionStorage.clear()
  fetchFbsWorkspace.mockReset()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

async function openAssembly() {
  await act(async () => {
    root.render(<FfFbsSupplyAssembly
      token="test" authHeaders={authHeaders} supplyIds={supplyIds} open onClose={() => undefined}
    />)
  })
}

describe('WMS-588 R7: reopening an assembly task', () => {
  it.each([null, 'composition', 'picking'] as const)(
    'opens packing when every supply is picked, even with saved %s stage',
    async (savedStage) => {
      if (savedStage) window.sessionStorage.setItem('wms:fbs:assembly:supply-a,supply-b:stage', savedStage)
      fetchFbsWorkspace.mockImplementation(async (_token, _headers, id: string) => workspace(id, 2))

      await openAssembly()

      expect(fetchFbsWorkspace).toHaveBeenCalledTimes(2)
      expect(document.querySelector('[data-testid="fbs-assembly-packing"]')).not.toBeNull()
      expect(document.querySelector('[data-testid="mock-packing-supply-a"]')).not.toBeNull()
      expect(document.querySelector('[data-testid="mock-packing-supply-b"]')).not.toBeNull()
      expect(document.querySelector('[data-testid="fbs-assembly-composition"]')).toBeNull()

      const pickingTab = [...document.querySelectorAll<HTMLElement>('[role="tab"]')]
        .find((tab) => tab.textContent === 'Подбор')
      await act(async () => pickingTab?.click())
      expect(document.querySelector('[data-testid="fbs-pick-unified"]')).not.toBeNull()
    },
  )

  it('keeps the saved stage when one supply is unfinished or empty', async () => {
    window.sessionStorage.setItem('wms:fbs:assembly:supply-a,supply-b:stage', 'picking')
    fetchFbsWorkspace.mockImplementation(async (_token, _headers, id: string) => (
      id === 'supply-a' ? workspace(id, 2) : workspace(id, 1)
    ))

    await openAssembly()

    expect(document.querySelector('[data-testid="fbs-pick-unified"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="fbs-assembly-packing"]')).toBeNull()
  })
})
