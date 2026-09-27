import { describe, expect, it } from 'vitest'

import { resolveInitialSellerFilter } from './urlSellerFilter'

describe('resolveInitialSellerFilter', () => {
  const sellers = [{ id: 'seller-a' }, { id: 'seller-b' }]

  it('returns the id when it is present in the loaded sellers list', () => {
    expect(resolveInitialSellerFilter('seller-a', sellers)).toBe('seller-a')
  })

  it('ignores an id of a seller not in the loaded list (foreign or another tenant)', () => {
    expect(resolveInitialSellerFilter('seller-of-another-tenant', sellers)).toBe('')
  })

  it('ignores a garbage value', () => {
    expect(resolveInitialSellerFilter('not-a-uuid', sellers)).toBe('')
  })

  it('returns "all sellers" (empty string) when the parameter is absent', () => {
    expect(resolveInitialSellerFilter(null, sellers)).toBe('')
  })
})
