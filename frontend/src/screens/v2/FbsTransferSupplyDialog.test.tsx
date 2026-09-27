// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { FbsTransferSupplyDialog } from './FbsTransferSupplyDialog'
import type { FbsTransferOrdersResult } from './fbsApi'

it('preserves the original request through network loss, rerender, reopen and partial confirmation', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  sessionStorage.clear()
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const loadTargets = vi.fn(async () => [{ id: 'target', name: 'Черновик', wb_supply_id: 'WB-2' }])
  const createIdempotencyKey = vi.fn(() => 'one-operation')
  const result = (state: FbsTransferOrdersResult['state'], moved: string[], pending: string[]): FbsTransferOrdersResult => ({
    state, target_supply_id: 'target', transferred_order_ids: moved, pending_order_ids: pending, failed_order_ids: [], message: null,
  })
  const submit = vi.fn()
    .mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(result('partial', ['A'], ['B']))
    .mockResolvedValueOnce(result('confirmed', ['A', 'B'], []))
  const onTransferred = vi.fn()
  const render = (open = true, orderIds = ['A', 'B']) => root.render(<FbsTransferSupplyDialog
    open={open} orderIds={orderIds} currentSupplyId="source" onClose={() => {}} onTransferred={onTransferred}
    deps={{ loadTargets, submit, createIdempotencyKey }}
  />)
  const click = async (selector: string) => act(async () => {
    const node = document.querySelector<HTMLElement>(selector)
    expect(node).not.toBeNull()
    node!.click()
  })
  try {
    await act(async () => render())
    await click('[data-testid="fbs-transfer-target-target"] input')
    await click('[data-testid="fbs-transfer-submit"]')
    expect(document.querySelector('[data-testid="fbs-transfer-pending"]')).not.toBeNull()
    await act(async () => render())
    expect(loadTargets).toHaveBeenCalledTimes(1)
    await act(async () => render(false))
    await act(async () => render())
    await click('[data-testid="fbs-transfer-submit"]')
    expect(onTransferred).toHaveBeenCalledWith(expect.objectContaining({ state: 'partial' }))
    await act(async () => render(true, ['B']))
    await click('[data-testid="fbs-transfer-submit"]')
    expect(submit).toHaveBeenCalledTimes(3)
    const request = { order_ids: ['A', 'B'], target_supply_id: 'target', idempotency_key: 'one-operation' }
    for (const [body] of submit.mock.calls) expect(body).toEqual(request)
    expect(createIdempotencyKey).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('wms:fbs:source:transfer')).toBeNull()
    expect(onTransferred).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'confirmed' }))
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
