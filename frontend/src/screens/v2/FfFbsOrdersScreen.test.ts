import { describe, expect, it, vi } from 'vitest'
import {
  formatFreshness,
  supplyStatusLabel,
  supplyStatusColor,
  normalizeSearch,
  formatNullableDateTime,
  elapsedSince,
  metadataProblem,
} from './fbsUx'
import type { FbsOrderMetadata, FbsWorklistOrder } from './fbsApi'

// Минимальный «конструктор» тестового заказа: TypeScript проверяет полноту через as.
function makeOrder(metadata: FbsOrderMetadata): FbsWorklistOrder {
  return {
    id: 'ord-1',
    wb_order_id: 1,
    status: 'new',
    wb_status: null,
    supplier_status: null,
    seller: { id: 's1', name: 'Seller' },
    wb_warehouse: { id: 1, name: 'WB МСК' },
    wms_warehouse: { id: 'w1', name: 'Основной' },
    product: {
      id: 'p1',
      name: 'Товар',
      image_url: null,
      seller_article: null,
      wb_article: null,
      barcode: null,
      sku: null,
      chrt_id: null,
      category: null,
      color: null,
      size: null,
    },
    inventory: { available_unpacked: 0, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'fbs',
    can_pvz: false,
    metadata,
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date().toISOString(),
    supply_id: null,
    selection_blockers: [],
  }
}

// TC-S03-PERF-001: метка свежести данных в шапке (R-38)
describe('formatFreshness', () => {
  it('returns null when no timestamp', () => {
    expect(formatFreshness(null)).toBeNull()
  })

  it('returns «только что» for less than 1 minute ago', () => {
    const now = new Date().toISOString()
    expect(formatFreshness(now)).toBe('Обновлено только что')
  })

  it('returns minutes label for older timestamp', () => {
    const twoMinutesAgo = new Date(Date.now() - 2 * 60 * 1000).toISOString()
    const result = formatFreshness(twoMinutesAgo)
    expect(result).toMatch(/2 минуты назад/)
  })
})

// TC-S03-PERF-002: формулировки пустых состояний поставок на языке склада (R-21, R-30)
describe('supplyStatusLabel', () => {
  it('translates known supply statuses', () => {
    expect(supplyStatusLabel('draft')).toBe('Черновик')
    expect(supplyStatusLabel('assembling')).toBe('В работе')
    expect(supplyStatusLabel('packed')).toBe('Готова к сдаче')
    expect(supplyStatusLabel('in_delivery')).toBe('В доставке')
    expect(supplyStatusLabel('done')).toBe('Завершена')
  })

  it('falls back for unknown status', () => {
    expect(supplyStatusLabel('something_new')).toBe('Статус уточняется')
  })
})

// TC-S03-PERF-003: цвет чипа статуса
describe('supplyStatusColor', () => {
  it('maps supply statuses to MUI semantic colors', () => {
    expect(supplyStatusColor('done')).toBe('success')
    expect(supplyStatusColor('in_delivery')).toBe('primary')
    expect(supplyStatusColor('draft')).toBe('warning')
    expect(supplyStatusColor('assembling')).toBe('warning')
    expect(supplyStatusColor('packed')).toBe('warning')
    expect(supplyStatusColor('unknown')).toBe('default')
  })
})

// TC-S03-PERF-004: нормализация поискового запроса
describe('normalizeSearch', () => {
  it('trims and lowercases input', () => {
    expect(normalizeSearch('  Привет  ')).toBe('привет')
    expect(normalizeSearch('ABC')).toBe('abc')
    expect(normalizeSearch('')).toBe('')
  })
})

// TC-S03-PERF-005: форматирование nullable datetime
describe('formatNullableDateTime', () => {
  it('returns em-dash for null', () => {
    expect(formatNullableDateTime(null)).toBe('—')
  })

  it('formats a valid ISO date string', () => {
    const result = formatNullableDateTime('2026-08-20T10:30:00.000Z')
    expect(result).toMatch(/\d{2}\.\d{2}\.\d{2}/)
  })
})

// TC-S03-PERF-006: время в сборке (elapsed since)
describe('elapsedSince', () => {
  it('shows minutes for short durations', () => {
    const start = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    expect(elapsedSince(start, null)).toBe('5 мин')
  })

  it('shows hours and minutes for longer durations', () => {
    const start = new Date(Date.now() - 90 * 60 * 1000).toISOString()
    expect(elapsedSince(start, null)).toBe('1 ч 30 мин')
  })

  it('shows days and hours for multi-day durations', () => {
    const start = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString()
    expect(elapsedSince(start, null)).toBe('1 д 1 ч')
  })

  it('uses serverNow if provided instead of Date.now()', () => {
    const start = '2026-08-20T10:00:00.000Z'
    const serverNow = '2026-08-20T10:05:00.000Z'
    expect(elapsedSince(start, serverNow)).toBe('5 мин')
  })
})

// TC-S03-PERF-007: флаг проблемы маркировки (метаданные Честного знака)
describe('metadataProblem', () => {
  const emptyMeta: FbsOrderMetadata = {
    required: [],
    optional: [],
    states: [],
    delivery_allowed: true,
    last_checked_at: null,
  }

  it('returns null when marking not required', () => {
    expect(metadataProblem(makeOrder(emptyMeta))).toBeNull()
  })

  it('detects rejected marking', () => {
    const meta: FbsOrderMetadata = {
      required: ['sgtin'],
      optional: [],
      states: [{ kind: 'sgtin', status: 'rejected', reason: null }],
      delivery_allowed: false,
      last_checked_at: null,
    }
    const result = metadataProblem(makeOrder(meta))
    expect(result).not.toBeNull()
    expect(result?.label).toBe('Отклонено WB')
    expect(result?.color).toBe('error')
  })

  it('counts missing marking codes', () => {
    const meta: FbsOrderMetadata = {
      required: ['sgtin'],
      optional: [],
      states: [
        { kind: 'sgtin', status: 'missing', reason: null },
        { kind: 'sgtin', status: 'missing', reason: null },
      ],
      delivery_allowed: false,
      last_checked_at: null,
    }
    const result = metadataProblem(makeOrder(meta))
    expect(result?.label).toContain('2')
  })

  it('returns null for accepted marking (no problem)', () => {
    const meta: FbsOrderMetadata = {
      required: ['sgtin'],
      optional: [],
      states: [{ kind: 'sgtin', status: 'accepted', reason: null }],
      delivery_allowed: true,
      last_checked_at: '2026-08-20T10:00:00.000Z',
    }
    expect(metadataProblem(makeOrder(meta))).toBeNull()
  })
})

// Suppress unused import linting since vi is used in the test runner context
void vi
