import { describe, expect, it } from 'vitest'

import { KizReprintDialog } from './KizReprintDialog'

const dialogSource = import.meta.glob<string>('./KizReprintDialog.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
})['./KizReprintDialog.tsx'] ?? ''

describe('KizReprintDialog FF contract', () => {
  it('is a shared minimal dialog with scan, exact history, individual and bulk printing', () => {
    expect(KizReprintDialog).toBeTypeOf('function')
    expect(dialogSource).toContain('Сканируйте КИЗ')
    expect(dialogSource).toContain('Печать всё')
    expect(dialogSource).toContain('Честный знак {row.kiz} успешно перепечатан')
    expect(dialogSource).toContain('aria-label="Печать КИЗ"')
    expect(dialogSource).toContain('Готово')
  })

  it('uses scanner payloads, persists them first, then only auto-prints non-replayed scans', () => {
    expect(dialogSource).toContain('useBarcodeScanner')
    expect(dialogSource).toContain('saveKizReprint')
    expect(dialogSource).toContain('printScannedKiz(row')
    expect(dialogSource).toContain('loadKizReprints')
  })
})
