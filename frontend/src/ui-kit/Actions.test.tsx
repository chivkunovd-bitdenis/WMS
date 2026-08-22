import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { PrintAction } from './Actions'

describe('PrintAction', () => {
  it('uses the storage invoice label in row and panel placements', () => {
    const row = renderToStaticMarkup(<PrintAction what="накладную" placement="row" />)
    const panel = renderToStaticMarkup(<PrintAction what="накладную" placement="panel" />)

    expect(row).toContain('aria-label="Печать накладной"')
    expect(panel).toContain('Печать накладной')
  })

  it('keeps existing labels in row and panel placements', () => {
    const labels = [
      ['ШК товара', 'Печать ШК товара'],
      ['ЧЗ и ШК', 'Печать ЧЗ и ШК'],
      ['ШК короба', 'Печать ШК короба'],
      ['ШК ячейки', 'Печать ШК ячейки'],
    ] as const

    for (const [what, label] of labels) {
      const row = renderToStaticMarkup(<PrintAction what={what} placement="row" />)
      const panel = renderToStaticMarkup(<PrintAction what={what} placement="panel" />)

      expect(row).toContain(`aria-label="${label}"`)
      expect(panel).toContain(label)
    }
  })

  it('preserves disabled explanations in row and panel placements', () => {
    const reason = 'Расчёт ещё не зафиксирован'
    const disabledPanel = renderToStaticMarkup(
      <PrintAction what="накладную" placement="panel" disabledReason={reason} />,
    )
    const disabledRow = renderToStaticMarkup(
      <PrintAction what="накладную" placement="row" disabledReason={reason} />,
    )

    expect(disabledPanel).toContain(`aria-label="${reason}"`)
    expect(disabledPanel).toContain('disabled=""')
    expect(disabledRow).toContain(`aria-label="${reason}"`)
    expect(disabledRow).toContain('disabled=""')
  })
})
