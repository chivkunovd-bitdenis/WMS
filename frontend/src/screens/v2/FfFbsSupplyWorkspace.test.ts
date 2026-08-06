import { describe, expect, it } from 'vitest'
import {
  buildFbsPickingListPrintHtml,
  bindFbsIdempotencyKey,
  createLatestRequestGuard,
  normalizeMetadataKind,
  supportsFbsCommonSupplyQr,
} from './fbsUx'

describe('FBS required identifiers', () => {
  it('TC-FBS-UX-002 sends the API-supported kind when WB calls it KIZ', () => {
    expect(normalizeMetadataKind('KIZ')).toBe('sgtin')
    expect(normalizeMetadataKind('SGTIN')).toBe('sgtin')
    expect(normalizeMetadataKind('UIN')).toBe('uin')
    expect(normalizeMetadataKind(undefined)).toBe('sgtin')
  })
})

describe('FBS picking list print document', () => {
  it('renders the current server-owned picking data and escapes product fields', () => {
    const html = buildFbsPickingListPrintHtml({
      supplyName: 'FBS <05.08>',
      wbSupplyId: 'WB-GI-1',
      sellerName: 'Seller & Co',
      wmsWarehouseName: 'Основной склад',
      routeLabel: 'ПВЗ',
      deadlineLabel: '10.08.2026, 12:00',
      printedAtLabel: '05.08.2026, 19:00',
      rows: [{
        name: '<script>alert(1)</script>',
        imageUrl: 'javascript:alert(1)',
        identifiers: ['ART-1', '2000000000011'],
        locations: ['A-01: 2'],
        required: 2,
        picked: 1,
        wbOrders: [500001, 500002],
        marking: 'КИЗ',
      }],
    })

    expect(html).toContain('Лист подбора FBS')
    expect(html).toContain('FBS &lt;05.08&gt;')
    expect(html).toContain('Seller &amp; Co')
    expect(html).toContain('№500001')
    expect(html).toContain('A-01: 2')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).not.toContain('javascript:alert(1)')
  })
})

describe('FBS async workspace guards', () => {
  it('reuses one idempotency key when a retryable mutation runs again', async () => {
    const receivedKeys: string[] = []
    const operation = bindFbsIdempotencyKey('stable-key', async (key) => {
      receivedKeys.push(key)
      return { ok: true }
    })

    await operation()
    await operation()

    expect(receivedKeys).toEqual(['stable-key', 'stable-key'])
  })

  it('allows only the latest polling generation to commit', () => {
    const guard = createLatestRequestGuard()
    const slow = guard.begin()
    const latest = guard.begin()

    expect(guard.isCurrent(slow)).toBe(false)
    expect(guard.isCurrent(latest)).toBe(true)

    guard.invalidate()
    expect(guard.isCurrent(latest)).toBe(false)
  })

  it('exposes the common supply QR only for warehouse or sorting-centre delivery', () => {
    expect(supportsFbsCommonSupplyQr({ delivery_type: 'warehouse_sc' })).toBe(true)
    expect(supportsFbsCommonSupplyQr({ delivery_type: 'pvz' })).toBe(false)
    expect(supportsFbsCommonSupplyQr(null)).toBe(false)
  })
})
