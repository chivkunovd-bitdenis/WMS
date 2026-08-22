import { describe, expect, it } from 'vitest'

// Воспроизводим фильтрацию по складу из rows useMemo (SellerDocumentsScreen).
// TC-S26-*: фильтрация документов по warehouse_id контекста.

type InboundRow = { id: string; warehouse_id: string }
type MpUnloadRow = { id: string; warehouse_id?: string }

function filterInbound(rows: InboundRow[], warehouseId: string | null): InboundRow[] {
  return warehouseId ? rows.filter((r) => r.warehouse_id === warehouseId) : rows
}

function filterMpUnload(rows: MpUnloadRow[], warehouseId: string | null): MpUnloadRow[] {
  return warehouseId
    ? rows.filter((r) => !r.warehouse_id || r.warehouse_id === warehouseId)
    : rows
}

describe('SellerDocumentsScreen warehouse filter (S-26, R-37)', () => {
  it('TC-S26-001 без warehouseId показывает все документы', () => {
    const inbound: InboundRow[] = [
      { id: 'i1', warehouse_id: 'wh-1' },
      { id: 'i2', warehouse_id: 'wh-2' },
    ]
    const mpUnload: MpUnloadRow[] = [
      { id: 'm1', warehouse_id: 'wh-1' },
      { id: 'm2' },
    ]
    expect(filterInbound(inbound, null)).toHaveLength(2)
    expect(filterMpUnload(mpUnload, null)).toHaveLength(2)
  })

  it('TC-S26-002 с warehouseId фильтрует inbound по складу', () => {
    const inbound: InboundRow[] = [
      { id: 'i1', warehouse_id: 'wh-1' },
      { id: 'i2', warehouse_id: 'wh-2' },
    ]
    const result = filterInbound(inbound, 'wh-1')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('i1')
  })

  it('TC-S26-003 с warehouseId фильтрует mp_unload по складу, сохраняет без warehouse_id', () => {
    const mpUnload: MpUnloadRow[] = [
      { id: 'm1', warehouse_id: 'wh-1' },
      { id: 'm2', warehouse_id: 'wh-2' },
      { id: 'm3' }, // без warehouse_id — сохраняем (данных нет, не скрываем)
    ]
    const result = filterMpUnload(mpUnload, 'wh-1')
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.id)).toContain('m1')
    expect(result.map((r) => r.id)).toContain('m3')
    expect(result.map((r) => r.id)).not.toContain('m2')
  })

  it('TC-S26-004 возвращает пустой список если в выбранном складе нет документов', () => {
    const inbound: InboundRow[] = [{ id: 'i1', warehouse_id: 'wh-2' }]
    expect(filterInbound(inbound, 'wh-1')).toHaveLength(0)
  })
})
