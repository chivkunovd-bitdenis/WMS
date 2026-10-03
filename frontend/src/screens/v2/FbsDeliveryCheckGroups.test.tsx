// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { DeliveryCheckGroupList } from './FbsDeliveryCheckGroups'
import { fbsDeliveryCheckOrderLabel, summarizeDeliveryChecks } from './fbsUx'

it('reveals each order reason and shortage without putting them in the group title', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const checks = [
    ['marking_not_allowed', 'WB ещё не подтвердил маркировку.', 'a'],
    ['marking_not_allowed', 'WB не принял маркировку: код уже использован', 'b'],
    ['negative_stock', 'Не хватает 1 шт.; после подтверждения остаток будет списан в минус.', 'a'],
    ['negative_stock', 'Не хватает 5 шт.; после подтверждения остаток будет списан в минус.', 'b'],
  ].map(([code, message, order_id]) => ({ code, message, order_id, ok: false, severity: 'warning' as const }))
  const { warnings } = summarizeDeliveryChecks(checks, new Map([['a', 530009], ['b', 530011]]))
  try {
    await act(async () => root.render(<DeliveryCheckGroupList groups={warnings} />))
    expect(host.textContent).not.toContain('530009')
    expect(host.textContent).not.toContain('код уже использован')
    expect(host.textContent).not.toContain('Не хватает 5')
    for (const code of ['marking_not_allowed', 'negative_stock']) {
      const toggle = host.querySelector<HTMLElement>(`[data-testid="fbs-delivery-check-${code}"]`)!
      await act(async () => toggle.click())
      const rows = host.querySelector(`[data-testid="fbs-delivery-check-orders-${code}"]`)!
      expect(rows.children).toHaveLength(2)
      expect(rows.children[0].textContent).toContain('530009')
      expect(rows.children[1].textContent).toContain('530011')
      if (code === 'marking_not_allowed') {
        expect(rows.children[0].textContent).toContain('WB ещё не подтвердил маркировку.')
        expect(rows.children[1].textContent).toContain('WB не принял маркировку: код уже использован')
      } else {
        expect(rows.children[0].textContent).toContain('Не хватает 1 шт.')
        expect(rows.children[1].textContent).toContain('Не хватает 5 шт.')
      }
    }
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})

it('signs expanded rows as WB orders by default and uses the passed label for Ozon postings', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const checks = ['o1', 'o2', 'o3'].map((order_id) => ({
    code: 'marking_required',
    message: 'Не нанесён Честный знак',
    order_id,
    ok: false,
    severity: 'warning' as const,
  }))
  const { warnings } = summarizeDeliveryChecks(checks, new Map([['o1', -4839201], ['o2', -77], ['o3', -12]]))
  const expandedRows = async () => {
    await act(async () => host.querySelector<HTMLElement>('[data-testid="fbs-delivery-check-marking_required"]')!.click())
    return [...host.querySelector('[data-testid="fbs-delivery-check-orders-marking_required"]')!.children]
      .map((row) => row.textContent)
  }
  try {
    await act(async () => root.render(<DeliveryCheckGroupList groups={warnings} />))
    expect(await expandedRows()).toEqual(['Заказ WB №-4839201', 'Заказ WB №-77', 'Заказ WB №-12'])

    await act(async () => root.render(<DeliveryCheckGroupList key="custom" groups={warnings} orderLabel={(id) => `Метка ${id}`} />))
    expect(await expandedRows()).toEqual(['Метка -4839201', 'Метка -77', 'Метка -12'])

    const wbLabel = fbsDeliveryCheckOrderLabel('wb', [])
    await act(async () => root.render(<DeliveryCheckGroupList key="wb" groups={warnings} orderLabel={wbLabel} />))
    expect(await expandedRows()).toEqual(['Заказ WB №-4839201', 'Заказ WB №-77', 'Заказ WB №-12'])

    // o1 пришёл со служебным номером строкой, у o2 нет номера отправления, o3 нет среди заказов поставки.
    const ozonLabel = fbsDeliveryCheckOrderLabel('ozon', [
      { wb_order_id: '-4839201', external_order_id: '87654321-0001-1' },
      { wb_order_id: -77, external_order_id: null },
    ])
    await act(async () => root.render(<DeliveryCheckGroupList key="ozon" groups={warnings} orderLabel={ozonLabel} />))
    const ozonRows = await expandedRows()
    expect(ozonRows).toEqual(['Отправление Ozon №87654321-0001-1', 'Отправление Ozon', 'Отправление Ozon'])
    expect(ozonRows.join(' ')).not.toContain('Заказ WB')
    expect(ozonRows.join(' ')).not.toMatch(/-4839201|-77|-12/)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
