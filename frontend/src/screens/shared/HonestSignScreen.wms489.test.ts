import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./HonestSignScreen.tsx', import.meta.url), 'utf8')

describe('WMS-489 · FF Honest Sign KIZ reprint entrypoint', () => {
  it('shows the shared dialog opener only in the FF route and requires a selected seller', () => {
    expect(source).toContain("routeBase === '/app/ff'")
    expect(source).toContain('disabled={!effectiveSellerId}')
    expect(source).toContain('setKizReprintOpen(true)')
    expect(source).toContain('KizReprintDialog')
  })

  it('keeps the seller portal out of the new reprint flow', () => {
    const entrypoint = source.slice(
      source.indexOf("routeBase === '/app/ff'"),
      source.indexOf('      <Paper variant="outlined"', source.indexOf("routeBase === '/app/ff'")),
    )
    expect(entrypoint).toContain('Перепечатать ЧЗ')
    expect(entrypoint).not.toContain("routeBase === '/seller'")
  })
})
