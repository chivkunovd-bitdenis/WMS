// @vitest-environment jsdom
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import { useScanIntake } from '../../hooks/useScanIntake'
import type { FbsWorkspace } from './fbsApi'
import type { FbsAssemblyFrameControl } from './FbsAssemblySupplyFrame'

const { fetchWorkspace, wbScan, ozonScan } = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(), wbScan: vi.fn(), ozonScan: vi.fn(),
}))
vi.mock('./fbsApi', async (importOriginal) => ({
  ...await importOriginal<typeof import('./fbsApi')>(), fetchFbsWorkspace: fetchWorkspace,
}))
vi.mock('./FfFbsAssemblyPick', () => ({ FfFbsAssemblyPick: () => null }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FfFbsSupplyWorkspace', () => ({
  FfFbsSupplyWorkspace: ({ supplyId, open, assemblyFrame }: {
    supplyId: string; open: boolean; assemblyFrame: FbsAssemblyFrameControl
  }) => {
    const ozon = supplyId === 'ozon'
    const register = assemblyFrame.registerScanner
    useEffect(() => {
      if (ozon) return
      register?.(supplyId, { scan: wbScan, hasPending: () => false, hasSavedAttempt: () => false, view: () => null })
      return () => register?.(supplyId, null)
    }, [ozon, register, supplyId])
    // The production Ozon workspace retains this active-frame condition.
    // Use the real scanner hook so a physical burst exposes double listeners.
    const intake = useScanIntake({
      enabled: open && ozon && assemblyFrame.active && assemblyFrame.visible,
      emitRaw: true, onScan: ozonScan,
    })
    return <div ref={intake.bindRoot}>
      <button data-testid={`activate-${supplyId}`} onClick={assemblyFrame.onActivate}>Начать</button>
      <button data-testid={`finish-${supplyId}`} onClick={assemblyFrame.onDeactivate}>Завершить</button>
    </div>
  },
}))

const authHeaders = () => ({})
function workspace(id: string): FbsWorkspace {
  return {
    supply: { id, marketplace: id === 'ozon' ? 'ozon' : 'wb', name: id, wb_supply_id: id,
      seller: { id, name: id }, wb_warehouse: { id: 1, name: 'Склад' } },
    progress: { picked: 1, total: 1, packed: 0, metadata_ready: 0, stickers_ready: 0 }, orders: [],
  } as unknown as FbsWorkspace
}
let root: Root
let host: HTMLDivElement
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
beforeEach(() => {
  window.sessionStorage.clear()
  wbScan.mockReset().mockResolvedValue(undefined)
  ozonScan.mockReset().mockResolvedValue(undefined)
  fetchWorkspace.mockReset().mockImplementation(async (_token, _headers, id: string) => workspace(id))
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
async function render(ids: string[]) {
  await act(async () => root.render(<FfFbsSupplyAssembly token="test" authHeaders={authHeaders} supplyIds={ids} open onClose={() => undefined} />))
}
async function click(id: string) {
  await act(async () => document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`)!.click())
}
async function scan(raw: string) {
  await act(async () => {
    (document.activeElement as HTMLElement | null)?.blur()
    for (const key of raw) document.body.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

describe('WMS-604 mixed marketplace scan ownership', () => {
  it('routes each physical scan once across WB → active Ozon → WB', async () => {
    await render(['wb', 'ozon'])
    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(1)
    expect(ozonScan).not.toHaveBeenCalled()

    await click('activate-ozon')
    expect(document.querySelector<HTMLInputElement>('[data-testid="fbs-unified-scan"] input')!.disabled).toBe(true)
    await scan('OZON-LABEL-1')
    expect(ozonScan).toHaveBeenCalledExactlyOnceWith('OZON-LABEL-1')
    expect(wbScan).toHaveBeenCalledTimes(1)

    await click('finish-ozon')
    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(2)
    expect(ozonScan).toHaveBeenCalledTimes(1)

    await click('activate-ozon')
    await click('activate-wb')
    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(3)
    expect(ozonScan).toHaveBeenCalledTimes(1)
  })
  it('leaves Ozon-only assemblies to their original scanner without an empty WB consumer', async () => {
    await render(['ozon'])
    await scan('OZON-BEFORE-ACTIVATE')
    expect(wbScan).not.toHaveBeenCalled()
    expect(ozonScan).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alert"]')).toBeNull()
    await click('activate-ozon')
    await scan('OZON-LABEL-2')
    expect(ozonScan).toHaveBeenCalledExactlyOnceWith('OZON-LABEL-2')
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })
})
