import { describe, expect, it } from 'vitest'
import { PrintAction } from './Actions'

describe('PrintAction', () => {
  it('uses the storage invoice label in row and panel placements', () => {
    const row = PrintAction({ what: 'накладную', placement: 'row' })
    const panel = PrintAction({ what: 'накладную', placement: 'panel' })

    expect(row.props.title).toBe('Печать накладной')
    expect(panel.props.children).toBe('Печать накладной')
  })

  it('keeps existing labels in row and panel placements', () => {
    const labels = [
      ['ШК товара', 'Печать ШК товара'],
      ['ЧЗ и ШК', 'Печать ЧЗ и ШК'],
      ['ШК короба', 'Печать ШК короба'],
      ['ШК ячейки', 'Печать ШК ячейки'],
    ] as const

    for (const [what, label] of labels) {
      const row = PrintAction({ what, placement: 'row' })
      const panel = PrintAction({ what, placement: 'panel' })

      expect(row.props.title).toBe(label)
      expect(panel.props.children).toBe(label)
    }
  })

  it('preserves disabled explanations in row and panel placements', () => {
    const reason = 'Расчёт ещё не зафиксирован'
    const disabledPanel = PrintAction({
      what: 'накладную',
      placement: 'panel',
      disabledReason: reason,
    })
    const disabledRow = PrintAction({
      what: 'накладную',
      placement: 'row',
      disabledReason: reason,
    })

    expect(disabledPanel.props.title).toBe(reason)
    expect(disabledPanel.props.children.props.disabled).toBe(true)
    expect(disabledRow.props.title).toBe(reason)
    expect(disabledRow.props.children.props.children.props.disabled).toBe(true)
  })
})
