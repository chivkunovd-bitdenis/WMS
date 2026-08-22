import { describe, expect, it } from 'vitest'
import { PrintAction } from './Actions'

describe('PrintAction', () => {
  it('uses the storage invoice label in row and panel placements', () => {
    const row = PrintAction({ what: 'накладную', placement: 'row' })
    const panel = PrintAction({ what: 'накладную', placement: 'panel' })

    expect(row.props.title).toBe('Печать накладную')
    expect(panel.props.children).toBe('Печать накладную')
  })

  it('keeps existing labels and disabled explanations', () => {
    const barcode = PrintAction({ what: 'ШК товара', placement: 'panel' })
    const disabled = PrintAction({
      what: 'накладную',
      placement: 'panel',
      disabledReason: 'Расчёт ещё не зафиксирован',
    })

    expect(barcode.props.children).toBe('Печать ШК товара')
    expect(disabled.props.disabledReason).toBe('Расчёт ещё не зафиксирован')
  })
})
