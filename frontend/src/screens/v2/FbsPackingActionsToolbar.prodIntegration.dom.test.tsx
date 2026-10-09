// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FbsPackingActionsToolbar, type FbsPackingActions } from './FbsPackingActionsToolbar'

let root: Root
let host: HTMLDivElement
function supply(id: string, marketplace: 'wb' | 'ozon' = 'wb'): FbsPackingActions {
  return {
    id, title: id, seller: `seller-${id}`, marketplace,
    orderIds: [`${id}-1`, `${id}-2`], selectedIds: [],
    printed: 1, packed: 0, packedTotal: 2, busy: false, editable: true,
    codes: 1, clearable: 1, honestSignSkipped: false, skipBusy: false,
    packAllDisabled: false, select: vi.fn(), print: vi.fn(() => true),
    verify: vi.fn(), packAll: vi.fn(), skip: vi.fn(), transfer: vi.fn(), clear: vi.fn(),
  }
}
async function render(entries: FbsPackingActions[], contextKey = 'group', active = true) {
  await act(async () => root.render(<FbsPackingActionsToolbar entries={entries} active={active} contextKey={contextKey} />))
}
async function click(testId: string) {
  const el = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`)
  expect(el, testId).not.toBeNull()
  await act(async () => el!.click())
}
beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove() })

describe('WMS-666 production integration: real shared packing actions', () => {
  it('prints selected orders in their own supply and advances only after full success', async () => {
    const a = supply('A'); const b = supply('B'); const c = supply('C', 'ozon')
    a.selectedIds = ['A-2']; b.selectedIds = ['B-1']
    let completeA: (success: boolean) => void = () => {}
    let completeB: (success: boolean) => void = () => {}
    a.print = vi.fn((ids, completed) => { expect(ids).toEqual(['A-2']); completeA = completed; return true })
    b.print = vi.fn((ids, completed) => { expect(ids).toEqual(['B-1']); completeB = completed; return true })
    await render([a, b, c]); await click('fbs-packing-print')
    expect(a.print).toHaveBeenCalledTimes(1); expect(b.print).not.toHaveBeenCalled(); expect(c.print).not.toHaveBeenCalled()
    await act(async () => completeA(true))
    expect(b.print).toHaveBeenCalledTimes(1)
    await act(async () => completeA(true))
    expect(b.print).toHaveBeenCalledTimes(1)
    await act(async () => completeB(true))
    expect(c.print).not.toHaveBeenCalled()
    expect(document.querySelector<HTMLButtonElement>('[data-testid="fbs-packing-print"]')!.disabled).toBe(false)
  })

  it('stops the remaining queue when an operator cancels the current print', async () => {
    const a = supply('A'); const b = supply('B')
    let close: (success: boolean) => void = () => {}
    a.print = vi.fn((_ids, completed) => { close = completed; return true })
    await render([a, b]); await click('fbs-packing-print')
    await act(async () => close(false))
    expect(b.print).not.toHaveBeenCalled()
    expect(document.querySelector<HTMLButtonElement>('[data-testid="fbs-packing-print"]')!.disabled).toBe(false)
  })

  it('ignores completion from a group which the operator has already left', async () => {
    const a = supply('A'); const b = supply('B')
    let complete: (success: boolean) => void = () => {}
    a.print = vi.fn((_ids, completed) => { complete = completed; return true })
    await render([a, b]); await click('fbs-packing-print')
    await render([a, b], 'next-group')
    await act(async () => complete(true))
    expect(b.print).not.toHaveBeenCalled()
  })

  it('checks every eligible WB supply independently of selection and excludes Ozon', async () => {
    const a = supply('A'); const b = supply('B'); const ozon = supply('Ozon', 'ozon'); const busy = supply('busy')
    b.selectedIds = ['B-1']; busy.busy = true
    await render([a, b, ozon])
    await click('fbs-packing-check-wb')
    expect(a.verify).toHaveBeenCalledOnce(); expect(b.verify).toHaveBeenCalledOnce(); expect(ozon.verify).not.toHaveBeenCalled()
    await render([a, busy, ozon])
    expect(document.querySelector<HTMLButtonElement>('[data-testid="fbs-packing-check-wb"]')!.disabled).toBe(true)
  })

  it('clears and transfers only selected rows of the explicitly chosen supply', async () => {
    const a = supply('A'); const b = supply('B')
    a.selectedIds = ['A-1']; b.selectedIds = ['B-2']
    await render([a, b]); await click('fbs-packing-more-actions')
    const chooseB = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')]
      .find(el => el.textContent === 'B · WB · seller-B')!
    expect(chooseB).toBeDefined(); await act(async () => chooseB.click())
    await click('fbs-packing-clear-selected')
    expect(b.clear).toHaveBeenCalledOnce(); expect(a.clear).not.toHaveBeenCalled()
    await click('fbs-packing-more-actions'); await click('fbs-packing-transfer-supply')
    expect(b.transfer).toHaveBeenCalledOnce(); expect(a.transfer).not.toHaveBeenCalled()
  })

  it('selects every visible supply and keeps print and packing counters separate', async () => {
    const a = supply('A'); const b = supply('B', 'ozon'); b.packed = 2
    await render([a, b]); await click('fbs-packing-select-all')
    expect(a.select).toHaveBeenCalledWith(['A-1', 'A-2']); expect(b.select).toHaveBeenCalledWith(['B-1', 'B-2'])
    expect(document.body.textContent).toContain('Напечатано 2 из 4 · упаковано 2 из 4 · выбрано 0')
    a.selectedIds = [...a.orderIds]; b.selectedIds = [...b.orderIds]
    await render([a, b]); await click('fbs-packing-select-all')
    expect(a.select).toHaveBeenLastCalledWith([]); expect(b.select).toHaveBeenLastCalledWith([])
  })
})
