import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('WMS-524: foreground confirmation before reserving a print popup', () => {
  it('keeps the blocking batch confirmation before popup, busy state and API work', () => {
    const source = readFileSync(new URL('./MarkingPrintDialog.tsx', import.meta.url), 'utf8')
    const handler = source.slice(source.indexOf('const handlePrint = async'), source.indexOf('const sepCzLayout:'))
    const confirmation = handler.indexOf('window.confirm(')
    const popup = handler.indexOf('beginPrintUserGesture()')
    const busy = handler.indexOf('onBusyChange(true)')
    const api = handler.indexOf('await printFbsTape(')
    expect(confirmation).toBeGreaterThan(0)
    expect(popup).toBeGreaterThan(confirmation)
    expect(busy).toBeGreaterThan(popup)
    expect(api).toBeGreaterThan(busy)
    expect(handler.slice(confirmation, popup)).toContain('return')
  })
})
