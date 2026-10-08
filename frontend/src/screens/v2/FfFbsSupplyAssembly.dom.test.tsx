// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'

const { fetchFbsWorkspace, ensureFbsStickers } = vi.hoisted(() => ({
  fetchFbsWorkspace: vi.fn(), ensureFbsStickers: vi.fn(),
}))
vi.mock('./fbsApi', () => ({ fetchFbsWorkspace, getFbsPickOptions: vi.fn() }))
vi.mock('./fbsStickerPrefetch', () => ({ ensureFbsStickers }))
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

function workspace(
  id: string,
  picked: number,
  total = 2,
  sellerName = `Селлер ${id}`,
  stickerCode: string | null = null,
  includeOrder = false,
): FbsWorkspace {
  return {
    supply: {
      id, marketplace: 'wb', name: id, wb_supply_id: id,
      seller: { id: id, name: sellerName }, wb_warehouse: { id: 507, name: 'Коледино' },
    },
    progress: { picked, total, packed: 0, metadata_ready: 0, stickers_ready: 0 },
    orders: !includeOrder ? [] : [{
      id: `order-${id}`, status: 'assembling', sticker: { code: stickerCode }, metadata: { states: [] },
    }],
  } as unknown as FbsWorkspace
}

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  window.sessionStorage.clear()
  fetchFbsWorkspace.mockReset()
  ensureFbsStickers.mockReset()
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

describe('WMS-666 grouped sticker preparation', () => {
  it('ignores a prefetch response from an earlier opening generation', async () => {
    let resolvePrefetch!: (result: { workspace: FbsWorkspace; errorMessage: null }) => void
    const pendingPrefetch = new Promise<{ workspace: FbsWorkspace; errorMessage: null }>((resolve) => {
      resolvePrefetch = resolve
    })
    ensureFbsStickers.mockReturnValue(pendingPrefetch)
    window.sessionStorage.setItem('wms:fbs:assembly:supply-a:stage', 'picking')
    fetchFbsWorkspace
      .mockResolvedValueOnce(workspace('supply-a', 0, 1, 'stale seller', null, true))
      .mockResolvedValueOnce(workspace('supply-a', 0, 1, 'current seller', 'QR-CURRENT', true))

    const render = (isOpen: boolean) => root.render(<FfFbsSupplyAssembly
      token="test" authHeaders={authHeaders} supplyIds={['supply-a']} open={isOpen} onClose={() => undefined}
    />)
    await act(async () => { render(true); await Promise.resolve(); await Promise.resolve() })
    expect(ensureFbsStickers).toHaveBeenCalledTimes(1)

    await act(async () => render(false))
    await act(async () => { render(true); await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(fetchFbsWorkspace).toHaveBeenCalledTimes(2)
    expect(document.body.textContent).toContain('current seller')

    await act(async () => {
      resolvePrefetch({ workspace: workspace('supply-a', 0, 1, 'stale seller', 'QR-STALE', true), errorMessage: null })
      await pendingPrefetch
    })
    expect(document.body.textContent).toContain('current seller')
    expect(document.body.textContent).not.toContain('stale seller')
  })

  it('does not prefetch stickers for a historical read-only WB supply', async () => {
    window.sessionStorage.setItem('wms:fbs:assembly:supply-a:stage', 'picking')
    const historical = {
      ...workspace('supply-a', 0, 1, 'historical seller', null, true),
      stage: 'tracking',
      supply: {
        ...workspace('supply-a', 0).supply,
        status: 'done',
      },
    } as FbsWorkspace
    fetchFbsWorkspace.mockResolvedValue(historical)

    await act(async () => { root.render(<FfFbsSupplyAssembly
      token="test" authHeaders={authHeaders} supplyIds={['supply-a']} open onClose={() => undefined}
    />); await Promise.resolve(); await Promise.resolve() })

    expect(document.querySelector('[data-testid="fbs-assembly"]')).not.toBeNull()
    expect(ensureFbsStickers).not.toHaveBeenCalled()
  })
})
