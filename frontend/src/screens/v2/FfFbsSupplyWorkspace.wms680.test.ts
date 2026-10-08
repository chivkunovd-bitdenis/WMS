import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml } from './fbsUx'

const workspaceSource = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')

describe('WMS-680 · одиночная печать FBS Ozon', () => {
  it('C680-05: передаёт marketplace Ozon реальному вызову листа подбора', () => {
    const callStart = workspaceSource.indexOf('printWindow.document.write(buildFbsPickingListPrintHtml({')
    const callEnd = workspaceSource.indexOf('\n    }))', callStart)
    expect(callStart).toBeGreaterThan(-1)
    expect(callEnd).toBeGreaterThan(callStart)
    const printCall = workspaceSource.slice(callStart, callEnd)

    // This is the single-supply caller, not the already-correct assembly caller.
    const callerPassesMarketplace = printCall.includes('marketplace: printWorkspace.supply.marketplace')
    const html = buildFbsPickingListPrintHtml({
      supplyName: 'Ozon supply',
      wbSupplyId: 'OZ-680',
      ...(callerPassesMarketplace ? { marketplace: 'ozon' as const } : {}),
      sellerName: 'Seller', wmsWarehouseName: 'WMS', routeLabel: 'Route',
      deadlineLabel: '2026-10-07', printedAtLabel: '2026-10-07',
      rows: [{ name: 'Ozon position', size: 'M', color: 'Blue', imageUrl: null, identifiers: [], locations: [], required: 1, picked: 0, wbOrders: [680], stickerCodes: [null], marking: '—' }],
    })

    expect(callerPassesMarketplace).toBe(true)
    expect(html).toContain('<th>Заказы Ozon</th>')
    expect(html).toContain('№ Ozon OZ-680')
  })
})
