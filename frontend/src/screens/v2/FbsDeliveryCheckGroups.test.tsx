// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { DeliveryCheckGroupList } from './FbsDeliveryCheckGroups'
import { summarizeDeliveryChecks } from './fbsUx'

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
