import { describe, expect, it } from 'vitest'
import {
  buildFbsPickingListPrintHtml,
  buildFbsSyncTargets,
  fbsBoxOperationsDisabled,
  fbsOrdersSyncErrorMessage,
  mixedMarketplaceSelectionMessage,
  normalizeMetadataKind,
} from './fbsUx'

describe('Ozon FBS UI boundaries', () => {
  it('syncs every seller and marketplace pair from one action', () => {
    expect(buildFbsSyncTargets(['seller-a', 'seller-b'], '__all__')).toEqual([
      { sellerId: 'seller-a', marketplace: 'wb' },
      { sellerId: 'seller-a', marketplace: 'ozon' },
      { sellerId: 'seller-b', marketplace: 'wb' },
      { sellerId: 'seller-b', marketplace: 'ozon' },
    ])
  })

  it('shows missing WB token as an operator action instead of a raw code', () => {
    expect(fbsOrdersSyncErrorMessage(new Error('missing_marketplace_token'))).toBe(
      'У селлера не подключён ключ Wildberries. Добавьте ключ WB в карточке селлера.',
    )
  })

  it('blocks creating and adding a mixed WB/Ozon selection', () => {
    expect(mixedMarketplaceSelectionMessage(['wb', 'ozon'])).toBe(
      'Нельзя объединить заказы Wildberries и Ozon в одну поставку.',
    )
    expect(mixedMarketplaceSelectionMessage(['ozon', 'ozon'])).toBeNull()
  })

  it('disables every box operation for Ozon, including removing an order', () => {
    expect(fbsBoxOperationsDisabled('ozon')).toBe(true)
    expect(fbsBoxOperationsDisabled('wb')).toBe(false)
  })
})

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
        size: '38',
        imageUrl: 'javascript:alert(1)',
        identifiers: ['ART-1', '2000000000011'],
        locations: ['A-01: 2'],
        required: 2,
        picked: 1,
        wbOrders: [500001, 500002],
        stickerCodes: ['56672606304'],
        marking: 'КИЗ',
      }],
    })

    expect(html).toContain('Лист подбора FBS')
    expect(html).toContain('FBS &lt;05.08&gt;')
    expect(html).toContain('Seller &amp; Co')
    expect(html).toContain('№500001')
    expect(html).toContain('<td class="number">1–2</td>')
    expect(html).toContain('5667260 <strong>6304</strong>')
    expect(html).toContain('A-01: 2')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).not.toContain('javascript:alert(1)')
  })

  it('печатает размер отдельной колонкой, а без размера ставит прочерк', () => {
    const base = {
      supplyName: 'FBS 19.08',
      wbSupplyId: 'WB-GI-2',
      sellerName: 'Loviana',
      wmsWarehouseName: 'основной',
      routeLabel: 'Склад / СЦ',
      deadlineLabel: '24.08.2026, 12:00',
      printedAtLabel: '19.08.2026, 16:20',
    }
    const row = {
      name: 'Лоферы замшевые',
      imageUrl: null,
      identifiers: ['J308-6'],
      locations: [],
      required: 1,
      picked: 0,
      wbOrders: [5524537174],
      stickerCodes: [null],
      marking: 'Не требуется',
    }

    const withSize = buildFbsPickingListPrintHtml({ ...base, rows: [{ ...row, size: '38' }] })
    expect(withSize).toContain('<th class="size">Размер</th>')
    expect(withSize).toContain('<td class="size">38</td>')

    const noSize = buildFbsPickingListPrintHtml({ ...base, rows: [{ ...row, size: null }] })
    expect(noSize).toContain('<td class="size">—</td>')
  })
})
