// @vitest-environment jsdom
import { act, useCallback, useState } from 'react'
import { FbsPackingActionsToolbar, type FbsPackingActions } from './FbsPackingActionsToolbar'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, authHeaders, button, click, json, order, selected, settle, workspace } from './fbsSupplyCard.contract-fixture'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
const { openPrint } = vi.hoisted(() => ({ openPrint: vi.fn() }))
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint, dialog: null }) }))
let f: CardFixture
beforeEach(() => { f = new CardFixture(); openPrint.mockReset() })
afterEach(() => { f.dispose(); vi.restoreAllMocks() })
const metadata = (required: string[] = [], states: any[] = [], optional: string[] = []) => ({ required, states, optional, delivery_allowed: true, last_checked_at: null })
const marked = (id: string, states: any[] = []) => order(id, { metadata: metadata(['sgtin'], states) })
const checkbox = (id: string, scope: ParentNode = document) => scope.querySelector(`[data-order-id="${id}"] [data-testid="fbs-packing-select-order"] input`)
async function choose(scope: ParentNode = document) { await click(button('Выбрать без ЧЗ', scope)) }

it('C1 replaces WB selection using metadata product and task requirements, including IMEI UIN', async () => {
  const product = { ...order('o3').product, requires_honest_sign: true }
  f.current = workspace('wb', [order('o1'), marked('o2'), order('o3', { product, metadata: metadata([], [], ['sgtin']) }),
    order('o4'), marked('o5', [{ kind: 'sgtin', status: 'accepted', value_tail: '555' }]),
    marked('o6', [{ kind: 'sgtin', status: 'rejected', value_tail: '666' }]),
    order('o7', { metadata: metadata(['imei', 'uin']) }), order('o8', { metadata: metadata([], [], ['sgtin']) })])
  f.lines = [{ id: 'line', product_id: 'product-o4', requires_honest_sign: true, qty_need_pack: 1, qty_total: 1 }]
  await f.render('packing')
  await click(checkbox('o2')); await click(checkbox('o6'))
  const before = structuredClone(f.current); const writes = f.writes().length
  await choose()
  expect(selected()).toEqual(['o1', 'o7', 'o8'])
  expect(f.current).toEqual(before)
  expect(f.writes()).toHaveLength(writes)
  expect(document.querySelectorAll('[data-order-id]')).toHaveLength(8)
})

it.each([false, true])('C2 cleared and skipped codes never turn required products into plain products, skipped=%s', async skipped => {
  f.current = workspace('wb', [order('o1'), order('o2', { product: { ...order('o2').product, requires_honest_sign: true } }),
    marked('o3', [{ kind: 'sgtin', status: 'accepted', value_tail: '123' }]), marked('o4')])
  ;(f.current.supply as any).honest_sign_skipped = skipped
  await f.render('packing'); const before = structuredClone(f.current)
  await choose()
  expect(selected()).toEqual(['o1'])
  expect(f.current).toEqual(before)
  expect(f.writes()).toEqual([])
})

it.each(['empty', 'marked', 'plain', 'printed', 'rejected-filter'])('C4 repeats only selection for %s and still permits manual checkboxes', async state => {
  const rows = state === 'empty' ? [] : state === 'marked' ? [marked('o1'), marked('o2')]
    : [order('o1'), order('o2', { pack: { status: 'packed', packed_at: '2026-10-09T08:00:00Z' }, sticker: { ...order('o2').sticker, status: 'applied', applied_at: '2026-10-09T08:00:00Z' } })]
  f.current = workspace('wb', rows)
  if (state === 'rejected-filter') f.current.orders.push(marked('o3', [{ kind: 'sgtin', status: 'rejected', value_tail: '3' }]))
  await f.render('packing')
  const filter = document.querySelector('[data-testid="fbs-wb-rejected-kiz-toggle"]')
  if (state === 'rejected-filter') { expect(filter).toBeTruthy(); await click(filter) }
  const before = structuredClone(f.current)
  await choose(); await choose()
  expect(selected()).toEqual(state === 'empty' || state === 'marked' ? [] : ['o1', 'o2'])
  expect(f.current).toEqual(before); expect(f.writes()).toEqual([])
  if (rows.length) {
    await click(checkbox('o1'))
    expect(selected().includes('o1')).toBe(state === 'marked')
  }
})

it('C5 new selection and manual selection feed identical ordered print requests without CHZ issuance', async () => {
  f.current = workspace('wb', [order('o1'), marked('o2'), order('o3')])
  await f.render('packing'); await choose()
  await click(document.querySelector('[data-testid="fbs-packing-print"]'))
  const first = openPrint.mock.calls.at(-1)![0]
  expect(first.fbsTape.orders.map((o: any) => o.orderId)).toEqual(['o1', 'o3'])
  expect(first.requiresHonestSign).toBe(false)
  await act(async () => first.fbsTape.print({ layout: { chz: { copies: 0 }, product: { copies: 1 } }, allowPartial: false, reprint: false }))
  expect(f.calls.find(c => c.path.endsWith('/order-print-tape'))!.body).toMatchObject({ order_ids: ['o1', 'o3'], allow_partial: false })
  await act(async () => openPrint.mock.calls.at(-1)![1].onClose(false))
  await click(checkbox('o3')); await click(checkbox('o1')); await click(checkbox('o3')); await click(checkbox('o1'))
  await click(document.querySelector('[data-testid="fbs-packing-print"]'))
  expect(openPrint.mock.calls.at(-1)![0].fbsTape.orders.map((o: any) => o.orderId)).toEqual(['o1', 'o3'])
  await act(async () => openPrint.mock.calls.at(-1)![1].onClose(false))
  await click(document.querySelector('[data-testid="fbs-packing-select-all"]'))
  await click(document.querySelector('[data-testid="fbs-packing-print"]'))
  expect(openPrint.mock.calls.at(-1)![0].fbsTape.orders.map((o: any) => o.orderId)).toEqual(['o1', 'o2', 'o3'])
})

it('C6 after rejected print the next selection uses current ids and current layout', async () => {
  f.current = workspace('wb', [order('o1'), order('o2')])
  await f.render('packing'); await choose()
  await click(document.querySelector('[data-testid="fbs-packing-print"]'))
  const context = openPrint.mock.calls.at(-1)![0]
  f.hook = async c => c.path.endsWith('/order-print-tape') ? json({ detail: { message: 'Печать отказала' } }, 503) : undefined
  await expect(context.fbsTape.print({ layout: { chz: { copies: 1 } }, allowPartial: false, reprint: false })).rejects.toThrow()
  await act(async () => openPrint.mock.calls.at(-1)![1].onClose(false))
  await click(checkbox('o1'))
  await click(document.querySelector('[data-testid="fbs-packing-print"]'))
  f.hook = async c => c.path.endsWith('/order-print-tape') ? json({ assets: [], orders: [], errors: [] }) : undefined
  await act(async () => openPrint.mock.calls.at(-1)![0].fbsTape.print({ layout: { chz: { copies: 0 } }, allowPartial: false, reprint: false }))
  expect(f.calls.filter(c => c.path.endsWith('/order-print-tape')).at(-1)!.body).toMatchObject({ order_ids: ['o2'], layout_json: { chz: { copies: 0 } } })
})

it('C7 reread and another card use only current ids without automatically adding checkboxes', async () => {
  let tick!: () => void
  const interval = window.setInterval.bind(window)
  vi.spyOn(window, 'setInterval').mockImplementation(((callback: () => void, ms: number) => { if (ms === 15_000) tick = callback; return interval(callback, ms) }) as any)
  f.current = workspace('wb', [order('o1'), marked('o2')])
  await f.render('packing'); await choose()
  f.current.orders = [order('o3'), marked('o4')]
  await act(async () => tick()); await settle()
  expect(selected()).toEqual([])
  await choose(); expect(selected()).toEqual(['o3'])
  f.current.supply.id = 'supply-b'; f.current.supply.name = 'Поставка B'
  await f.render('packing')
  expect(selected()).toEqual([])
  await choose(); expect(selected()).toEqual(['o3'])
  expect([...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].every(t => !t.disabled)).toBe(true)
})

it('C3 Ozon selects only known plain whole postings, including all positions, and preserves manual unknown choice', async () => {
  const posting = (id: string, known: boolean, required: string[] = [], secondMarked = false) => order(id, {
    metadata: { ...metadata(required), requirements_known: known },
    positions: [1, 2].map(n => ({ id: `${id}-p${n}`, product_id: `${id}-product-${n}`, name: `${id} позиция ${n}`,
      quantity: 2, picked_quantity: 0, requires_honest_sign: n === 2 && secondMarked })),
  })
  f.current = workspace('ozon', [posting('o1', true), posting('o2', true, [], true), posting('o3', true, ['sgtin']),
    posting('o4', true, ['imei', 'uin']), posting('o5', false), posting('o6', true)])
  await f.render('packing'); await click(checkbox('o3')); const before = structuredClone(f.current)
  await choose()
  expect(selected()).toEqual(['o1', 'o4', 'o6'])
  expect(f.current).toEqual(before); expect(f.writes()).toEqual([])
  await click(checkbox('o5')); expect(selected()).toEqual(['o1', 'o4', 'o5', 'o6'])
})

it('C7 assembly registration keeps independent selectors for two seller blocks', async () => {
  const a = workspace('wb', [order('o1'), marked('o2')]); a.stage = 'packing'
  const b = workspace('wb', [order('o3'), marked('o4')]); b.supply.id = 'supply-b'; b.supply.seller = { id: 'other-seller', name: 'Другой селлер' }; b.stage = 'packing'
  const packingHosts = [document.createElement('div'), document.createElement('div')]
  packingHosts.forEach(h => document.body.append(h))
  f.hook = async c => c.path.endsWith('/workspace') ? json(c.path.includes('supply-b') ? b : a) : undefined
  function Frame({ snapshot, host }: { snapshot: typeof a; host: HTMLDivElement }) {
    const [actions, setActions] = useState<FbsPackingActions | null>(null)
    const register = useCallback((_id: string, value: FbsPackingActions | null) => setActions(value), [])
    return <>
      <FfFbsSupplyWorkspace token="contract-test" authHeaders={authHeaders} supplyId={snapshot.supply.id}
        initialWorkspace={snapshot} open onClose={() => undefined} assemblyFrame={{ stage: 'packing', packingHost: host,
          registerPackingActions: register, active: true, expanded: true, visible: true,
          onToggleExpanded: () => undefined, onActivate: () => undefined, onDeactivate: () => undefined,
          onWorkspaceChange: () => undefined } as any} />
      {actions && <div data-scope={snapshot.supply.id}><FbsPackingActionsToolbar entries={[actions]} active contextKey={snapshot.supply.id} /></div>}
    </>
  }
  await act(async () => f.root.render(<><Frame snapshot={a} host={packingHosts[0]} /><Frame snapshot={b} host={packingHosts[1]} /></>))
  await settle()
  await click(checkbox('o4', packingHosts[1]))
  await choose(document.querySelector('[data-scope="supply-a"]')!)
  expect(selected(packingHosts[0])).toEqual(['o1'])
  expect(selected(packingHosts[1])).toEqual(['o4'])
  expect(f.writes()).toEqual([])
  packingHosts.forEach(h => h.remove())
})
