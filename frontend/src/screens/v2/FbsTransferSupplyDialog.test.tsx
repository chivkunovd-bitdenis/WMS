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
  const loadTargets = vi.fn(async () => [{ id: 'target', name: 'Черновик', wb_supply_id: 'WB-2', created_at: '2026-09-28T10:00:00Z' }])
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
    // WMS-581 R3: выбор поставки — из выпадающего списка одного поля.
    await click('[data-testid="fbs-transfer-target-open"]')
    await click('[data-testid="fbs-transfer-target-target"]')
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

it('WMS-581: one dropdown field, typed name for a new supply and the created-supply window', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  sessionStorage.clear()
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const loadTargets = vi.fn(async () => [
    { id: 'in-work', name: 'Коледино утро', wb_supply_id: 'WB-GI-7', created_at: '2026-09-29T08:00:00Z' },
  ])
  const submit = vi.fn(async (): Promise<FbsTransferOrdersResult> => ({
    state: 'confirmed', target_supply_id: 'created-id', target_supply_name: 'Коледино 29.09',
    target_wb_supply_id: 'WB-GI-9', target_created: true,
    transferred_order_ids: ['A'], pending_order_ids: [], failed_order_ids: [], message: null,
  }))
  const onClose = vi.fn()
  const onTransferred = vi.fn()
  const click = async (selector: string) => act(async () => {
    const node = document.querySelector<HTMLElement>(selector)
    expect(node).not.toBeNull()
    node!.click()
  })
  const input = () => document.querySelector<HTMLInputElement>('[data-testid="fbs-transfer-target-input"]')!
  try {
    await act(async () => root.render(<FbsTransferSupplyDialog
      open orderIds={['A']} currentSupplyId="source" onClose={onClose} onTransferred={onTransferred}
      deps={{ loadTargets, submit, createIdempotencyKey: () => 'key' }}
    />))
    expect(loadTargets).toHaveBeenCalledWith(['A'])
    // По умолчанию — «Новая поставка»: поле само является строкой ввода.
    expect(input().readOnly).toBe(false)
    expect(input().placeholder).toBe('Новая поставка')
    await click('[data-testid="fbs-transfer-target-open"]')
    const items = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].map((node) => node.textContent)
    expect(items).toEqual(['Новая поставка', 'WB-GI-7 · от 29.09.2026'])
    await click('[data-testid="fbs-transfer-target-in-work"]')
    expect(input().value).toBe('WB-GI-7 · от 29.09.2026')
    expect(input().readOnly).toBe(true)
    await click('[data-testid="fbs-transfer-target-open"]')
    await click('[data-testid="fbs-transfer-target-new"]')
    expect(input().readOnly).toBe(false)
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      setter.call(input(), 'Коледино 29.09')
      input().dispatchEvent(new Event('input', { bubbles: true }))
    })
    await click('[data-testid="fbs-transfer-submit"]')
    expect(submit).toHaveBeenCalledWith({
      order_ids: ['A'], target_supply_id: null, idempotency_key: 'key', name: 'Коледино 29.09',
    })
    expect(onTransferred).toHaveBeenCalledWith(expect.objectContaining({ target_created: true }))
    const created = document.querySelector('[data-testid="fbs-transfer-created"]')
    expect(created?.textContent).toBe('Создана поставка Коледино 29.09 · WB WB-GI-9')
    const link = document.querySelector<HTMLAnchorElement>('[data-testid="fbs-transfer-created-link"]')!
    expect(link.getAttribute('href')).toBe(`${window.location.pathname}?supply_id=created-id`)
    expect(link.target).toBe('_blank')
    const buttons = [...document.querySelectorAll<HTMLElement>('[data-testid="fbs-transfer-supply-dialog"] button')]
    expect(buttons.map((node) => node.textContent)).toEqual(['ОК'])
    await click('[data-testid="fbs-transfer-created-ok"]')
    expect(onClose).toHaveBeenCalledTimes(1)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
