import { describe, expect, it } from 'vitest'
import { helpButtonBottom } from './useHelpButtonBottom'

describe('global help button avoids working controls', () => {
  it('stays in the lower right when controls do not cross its area', () => {
    expect(helpButtonBottom(1280, 720, [{ left: 300, right: 800, top: 648, bottom: 695, width: 500, height: 47 }])).toBe(16)
  })
  it('moves above a fixed FBS action and a second control without overlap', () => {
    const controls = [
      { left: 1100, right: 1260, top: 651, bottom: 690, width: 160, height: 39 },
      { left: 1170, right: 1260, top: 590, bottom: 630, width: 90, height: 40 },
    ]
    const bottom = helpButtonBottom(1280, 720, controls)
    expect(720 - bottom).toBeLessThan(590)
    expect(720 - bottom - 40).toBeGreaterThan(16)
    expect(helpButtonBottom(1280, 720, [])).toBe(16)
  })
})
