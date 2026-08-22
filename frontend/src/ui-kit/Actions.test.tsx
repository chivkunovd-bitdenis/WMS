import { describe, expect, it } from 'vitest'
import { PrintAction } from './Actions'

describe('PrintAction', () => {
  it('uses the storage invoice label in row and panel placements', () => {
    const row = PrintAction({ what: 'накладную', placement: 'row' })
    const panel = PrintAction({ what: 'накладную', placement: 'panel' })

    expect(row.props.title).toBe('Печать накладной')
    expect(panel.props.children).toBe('Печать накладной')
  })

  it('keeps existing labels in panel placement', () => {
    const labels = [
      ['ШК товара', 'Печать ШК товара'],
      ['ЧЗ и ШК', 'Печать ЧЗ и ШК'],
      ['ШК короба', 'Печать ШК короба'],
      ['ШК ячейки', 'Печать ШК ячейки'],
    ] as const

    for (const [what, label] of labels) {
      const action = PrintAction({ what, placement: 'panel' })
      expect(action.props.children).toBe(label)
    }
  })

  it('preserves disabled explanations in row and panel placements', () => {
    const reason = 'Расчёт ещё не зафиксирован'
    const barcode = PrintAction({ what: 'ШК товара', placement: 'panel' })
    const disabled = PrintAction({
      what: 'накладную',
      placement: 'panel',
      disabledReason: reason,
    })
    const disabledRow = PrintAction({
      what: 'накладную',
      placement: 'row',
      disabledReason: reason,
    })

    expect(barcode.props.children).toBe('Печать ШК товара')
    expect(disabled.props.title).toBe(reason)
    expect(disabled.props.children.props.disabled).toBe(true)
    expect(disabledRow.props.title).toBe(reason)
    expect(disabledRow.props.children.props.children.props.disabled).toBe(true)
  })
})
