// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
import type { FbsAssemblyFrameControl } from './FbsAssemblySupplyFrame'
import { saveFbsAssemblyStage } from './fbsSupplyAssembly'

// WMS-636 C10: в «Сборке» N — сумма непринятых WB КИЗ по WB-поставкам, фильтр общий для рамок.

const { fetchWorkspace, frames } = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(), frames: new Map<string, FbsAssemblyFrameControl>(),
}))
vi.mock('./fbsApi', async (importOriginal) => ({
  ...await importOriginal<typeof import('./fbsApi')>(), fetchFbsWorkspace: fetchWorkspace,
}))
vi.mock('./FfFbsAssemblyPick', () => ({ FfFbsAssemblyPick: () => null }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FfFbsSupplyWorkspace', async () => {
  const { useEffect } = await import('react')
  return {
    FfFbsSupplyWorkspace: ({ supplyId, assemblyFrame }: { supplyId: string; assemblyFrame: FbsAssemblyFrameControl }) => {
      frames.set(supplyId, assemblyFrame)
      const register = assemblyFrame.registerScanner
      useEffect(() => {
        if (supplyId.startsWith('ozon')) return
        register?.(supplyId, { scan: vi.fn(), hasPending: () => false, hasSavedAttempt: () => false, view: () => null })
        return () => register?.(supplyId, null)
      }, [register, supplyId])
      return null
    },
  }
})

const state = (status: string) => ({ kind: 'sgtin', status, reason: status === 'rejected' ? 'КИЗ не введён в оборот' : null, value_tail: 'T' })
function workspace(id: string, statuses: string[]): FbsWorkspace {
  return {
    supply: { id, marketplace: id.startsWith('ozon') ? 'ozon' : 'wb', name: id, wb_supply_id: id,
      seller: { id, name: id }, wb_warehouse: { id: 1, name: 'Склад' } },
    progress: { picked: 1, total: 1, packed: 0, metadata_ready: 0, stickers_ready: 0 },
    orders: statuses.map((status, index) => ({ id: `${id}-${index}`, metadata: { required: ['sgtin'], optional: [], states: [state(status)] } })),
  } as unknown as FbsWorkspace
}
let data: Record<string, FbsWorkspace>
let root: Root
let host: HTMLDivElement
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
beforeEach(() => {
  window.sessionStorage.clear()
  frames.clear()
  data = {
    'wb-1': workspace('wb-1', ['rejected', 'accepted']),
    'wb-2': workspace('wb-2', ['accepted', 'replacement_required', 'rejected']),
    'ozon-1': workspace('ozon-1', ['rejected']),
  }
  fetchWorkspace.mockReset().mockImplementation(async (_token, _headers, id: string) => data[id])
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

const toggle = () => document.querySelector<HTMLElement>('[data-testid="fbs-wb-rejected-kiz-toggle"]')

describe('WMS-636 · «Сборка»', () => {
  it('C10/R1/R2/R7: N по WB-поставкам, фильтр общий; шапка у первой поставки с непринятыми, после скана — у поднятой', async () => {
    const ids = ['wb-1', 'ozon-1', 'wb-2']
    saveFbsAssemblyStage(ids, 'packing', window.sessionStorage)
    await act(async () => root.render(<FfFbsSupplyAssembly token="t" authHeaders={() => ({})} supplyIds={ids} open onClose={() => undefined} />))
    expect(toggle()!.textContent).toBe('3')
    expect(frames.get('wb-1')!.rejectedFilter).toEqual({ active: false, count: 3, headerSupplyId: 'wb-1' })

    await act(async () => toggle()!.click())
    expect(toggle()!.getAttribute('aria-pressed')).toBe('true')
    for (const id of ids) expect(frames.get(id)!.rejectedFilter).toMatchObject({ active: true, count: 3, headerSupplyId: 'wb-1' })

    await act(async () => frames.get('wb-2')!.onPromotePackingOrder!('wb-2', 'wb-2-0'))
    expect(frames.get('wb-1')!.rejectedFilter!.headerSupplyId).toBe('wb-2')

    await act(async () => toggle()!.click())
    expect(frames.get('wb-1')!.rejectedFilter!.active).toBe(false)
    await act(async () => toggle()!.click())

    // R7: все исправлены — треугольник исчез, фильтр выключился.
    await act(async () => {
      frames.get('wb-1')!.onWorkspaceChange(workspace('wb-1', ['accepted', 'accepted']))
      frames.get('wb-2')!.onWorkspaceChange(workspace('wb-2', ['accepted', 'pending', 'accepted']))
    })
    expect(toggle()).toBeNull()
    expect(frames.get('wb-1')!.rejectedFilter).toMatchObject({ active: false, count: 0 })
  })
})
