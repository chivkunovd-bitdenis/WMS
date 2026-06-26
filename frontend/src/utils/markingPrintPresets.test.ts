import { describe, expect, it } from 'vitest'

import { expandLayoutTape } from './markingPrintPresets'

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
})
