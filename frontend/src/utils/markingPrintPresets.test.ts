import { describe, expect, it } from 'vitest'

import {
  expandLayoutTape,
  applyLabelsPerProductToLayout,
  countTapeBlocks,
  tapeToLayout,
} from './markingPrintPresets'

describe('expandLayoutTape', () => {
  it('expands cz×2 + label×1 for two units', () => {
    const layout = {
      units: [
        { block: 'cz' as const, copies: 2 },
        { block: 'label' as const, copies: 1 },
      ],
    }
    const tape = expandLayoutTape(['cis-a', 'cis-b'], layout)
    expect(tape.map((item) => `${item.block}:${item.cis}`)).toEqual([
      'cz:cis-a',
      'cz:cis-a',
      'label:cis-a',
      'cz:cis-b',
      'cz:cis-b',
      'label:cis-b',
    ])
  })

  it('defaults to single cz when layout units empty', () => {
    const tape = expandLayoutTape(['x'], { units: [] })
    expect(tape).toEqual([{ block: 'cz', cis: 'x', unitIndex: 0 }])
  })

  // TC-NEW-MP-016 — layout [cz×3, label×2], qty 5, lpp 2 → 35 blocks (A-002: label only × lpp).
  it('counts tape blocks with labels per product on label blocks only', () => {
    const layout = {
      units: [
        { block: 'cz' as const, copies: 3 },
        { block: 'label' as const, copies: 2 },
      ],
    }
    expect(countTapeBlocks(5, layout, 2)).toBe(35)
  })

  it('applyLabelsPerProductToLayout multiplies label copies only', () => {
    const layout = {
      units: [
        { block: 'cz' as const, copies: 2 },
        { block: 'label' as const, copies: 1 },
      ],
    }
    const adjusted = applyLabelsPerProductToLayout(layout, 3)
    expect(adjusted.units).toEqual([
      { block: 'cz', copies: 2 },
      { block: 'label', copies: 3 },
    ])
  })
})

describe('лента и состав этикетки', () => {
  it('правка ленты не стирает состав, закреплённый за продавцом', () => {
    // Состав — свойство товара продавца, лента — привычка оператора. Пока
    // состав терялся здесь, любое изменение количества блоков возвращало на
    // этикетку выключенные поля. А системная лента — два блока Честного знака,
    // поэтому оператору, которому нужен ШК ВБ, приходилось менять количество —
    // и настройка слетала почти всегда.
    const options = {
      include_size: true,
      include_color: true,
      include_brand: false,
      include_composition: false,
    }
    const layout = tapeToLayout(['cz', 'label', 'label'], options)
    expect(layout.units).toEqual([
      { block: 'cz', copies: 1 },
      { block: 'label', copies: 2 },
    ])
    expect(layout.label_options).toEqual(options)
  })

  it('без состава макет остаётся прежним — печатаем всё', () => {
    expect(tapeToLayout(['cz', 'cz'])).toEqual({ units: [{ block: 'cz', copies: 2 }] })
  })
})
