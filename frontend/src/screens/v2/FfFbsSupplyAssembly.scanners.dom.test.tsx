// @vitest-environment jsdom
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
import type { FbsAssemblyFrameControl } from './FbsAssemblySupplyFrame'
import { saveFbsAssemblyStage } from './fbsSupplyAssembly'

const { fetchWorkspace, wbScan, wbQrPrint, ozonScan } = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(), wbScan: vi.fn(), wbQrPrint: vi.fn(), ozonScan: vi.fn(),
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
      const scan = ozon
        ? async (raw: string) => { await ozonScan(raw) }
        : async (raw: string) => { await wbScan(raw); await wbQrPrint(raw) }
      register?.(supplyId, {
        matches: (raw) => ozon ? raw.startsWith('OZON-') : !raw.startsWith('OZON-'),
        scan, hasPending: () => false, hasSavedAttempt: () => false, view: () => null,
      })
      return () => register?.(supplyId, null)
    }, [ozon, register, supplyId])
    return open ? <div data-stage={assemblyFrame.stage} data-testid={`registered-${supplyId}`} /> : null
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
  wbQrPrint.mockReset().mockResolvedValue(undefined)
  ozonScan.mockReset().mockResolvedValue(undefined)
  fetchWorkspace.mockReset().mockImplementation(async (_token, _headers, id: string) => workspace(id))
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
async function render(ids: string[]) {
  saveFbsAssemblyStage(ids, 'packing', window.sessionStorage)
  await act(async () => root.render(<FfFbsSupplyAssembly token="test" authHeaders={authHeaders} supplyIds={ids} open onClose={() => undefined} />))
}
async function scan(raw: string) {
  await act(async () => {
    (document.activeElement as HTMLElement | null)?.blur()
    for (const key of raw) document.body.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

describe('WMS-604/WMS-666 unified marketplace scan ownership', () => {
  it('opens boxes after packing and suspends scan intake until returning to packing', async () => {
    await render(['wb', 'ozon'])
    const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Состав', 'Подбор', 'Упаковка и маркировка', 'Короба'])
    await act(async () => tabs.find((tab) => tab.textContent === 'Короба')!.click())
    expect(document.querySelectorAll('[data-stage="boxes"]')).toHaveLength(2)
    await scan('4600000000017')
    expect(wbScan).not.toHaveBeenCalled()
    expect(ozonScan).not.toHaveBeenCalled()
    await act(async () => tabs.find((tab) => tab.textContent === 'Упаковка и маркировка')!.click())
    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(1)
    expect(wbQrPrint).toHaveBeenCalledTimes(1)
    expect(ozonScan).not.toHaveBeenCalled()
  })

  it('routes each physical scan once across WB → Ozon → WB without an active frame', async () => {
    await render(['wb', 'ozon'])
    expect(document.querySelectorAll('[data-testid="fbs-unified-scan"]')).toHaveLength(1)
    expect(document.querySelector('[data-testid^="activate-"]')).toBeNull()
    expect(document.querySelector('[data-testid^="finish-"]')).toBeNull()
    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(1)
    expect(wbQrPrint).toHaveBeenCalledTimes(1)
    expect(ozonScan).not.toHaveBeenCalled()

    await scan('OZON-LABEL-1')
    expect(ozonScan).toHaveBeenCalledExactlyOnceWith('OZON-LABEL-1')
    expect(wbScan).toHaveBeenCalledTimes(1)
    expect(wbQrPrint).toHaveBeenCalledTimes(1)

    await scan('4600000000017')
    expect(wbScan).toHaveBeenCalledTimes(2)
    expect(wbQrPrint).toHaveBeenCalledTimes(2)
    expect(ozonScan).toHaveBeenCalledTimes(1)
  })

  it('routes Ozon-only scans through the one common router with WB QR disabled', async () => {
    await render(['ozon'])
    expect(document.querySelectorAll('[data-testid="fbs-unified-scan"]')).toHaveLength(1)
    expect(document.querySelector<HTMLInputElement>('[data-testid="fbs-unified-scan"] input')!.disabled).toBe(false)
    const qr = document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-qr-toggle"] input')!
    expect(qr.disabled).toBe(true)
    expect(qr.checked).toBe(false)
    await scan('OZON-BEFORE-ACTIVATE')
    expect(wbScan).not.toHaveBeenCalled()
    expect(wbQrPrint).not.toHaveBeenCalled()
    expect(ozonScan).toHaveBeenCalledExactlyOnceWith('OZON-BEFORE-ACTIVATE')
    expect(document.querySelector('[role="alert"]')).toBeNull()
    await scan('OZON-LABEL-2')
    expect(ozonScan).toHaveBeenCalledTimes(2)
    expect(ozonScan).toHaveBeenLastCalledWith('OZON-LABEL-2')
    expect(wbQrPrint).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })
})
