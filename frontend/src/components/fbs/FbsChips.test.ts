import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DeadlinePill, resolveDeadlineNow } from './FbsChips'

describe('resolveDeadlineNow', () => {
  it('uses server time as the initial deadline reference and only client elapsed time afterwards', () => {
    const serverNow = '2026-08-04T10:00:00.000Z'
    const clientAnchor = 1_000_000

    expect(resolveDeadlineNow(serverNow, clientAnchor, clientAnchor)).toBe(Date.parse(serverNow))
    expect(resolveDeadlineNow(serverNow, clientAnchor + 90_000, clientAnchor)).toBe(
      Date.parse(serverNow) + 90_000,
    )
  })

  it('falls back to the client clock when server time is absent or malformed', () => {
    expect(resolveDeadlineNow(null, 120_000, 100_000)).toBe(120_000)
    expect(resolveDeadlineNow('not-a-date', 120_000, 100_000)).toBe(120_000)
  })

  it('hides only an expired or current Ozon deadline pill', () => {
    const serverNow = '2026-09-14T10:00:00.000Z'

    for (const deadlineAt of ['2026-09-14T09:59:59.000Z', serverNow]) {
      expect(renderToStaticMarkup(
        createElement(DeadlinePill, { deadlineAt, serverNow, marketplace: 'ozon' }),
      )).toBe('')
    }
  })

  it('keeps future Ozon and expired WB deadline pills unchanged', () => {
    const serverNow = '2026-09-14T10:00:00.000Z'
    const futureOzon = renderToStaticMarkup(
      createElement(DeadlinePill, {
        deadlineAt: '2026-09-14T11:00:00.000Z', serverNow, marketplace: 'ozon',
      }),
    )
    const expiredWb = renderToStaticMarkup(
      createElement(DeadlinePill, {
        deadlineAt: '2026-09-14T09:59:59.000Z', serverNow, marketplace: 'wb',
      }),
    )

    expect(futureOzon).toContain('data-testid="fbs-deadline-pill"')
    expect(futureOzon).toContain('data-overdue="false"')
    expect(expiredWb).toContain('Просрочен')
    expect(expiredWb).toContain('data-overdue="true"')
  })
})
