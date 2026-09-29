import { describe, expect, it } from 'vitest'
import { sellerWbStatusLabel } from './sellerWbStatus'

describe('sellerWbStatusLabel', () => {
  it('reports "Ключа нет" when there is no WB key, regardless of a stale scope flag', () => {
    expect(sellerWbStatusLabel({ wb_has_key: false, wb_marketplace_scope_ok: true })).toBe('Ключа нет')
  })

  it('reports the passed check result when a key exists', () => {
    expect(sellerWbStatusLabel({ wb_has_key: true, wb_marketplace_scope_ok: true })).toBe('Проверка пройдена')
    expect(sellerWbStatusLabel({ wb_has_key: true, wb_marketplace_scope_ok: false })).toBe(
      'Нет доступа к Marketplace',
    )
  })

  it('reports "Не проверяли" when the scope was never checked', () => {
    expect(sellerWbStatusLabel({ wb_has_key: true, wb_marketplace_scope_ok: null })).toBe('Не проверяли')
    expect(sellerWbStatusLabel({})).toBe('Не проверяли')
  })
})
