import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfPackagingPage.tsx', import.meta.url), 'utf8')

describe('FfPackagingPage warehouse queue contract', () => {
  it('S-14-TC-001 requests the queue for the selected warehouse and reloads on context changes', () => {
    expect(source).toContain("useWarehouseContext('fulfillment')")
    expect(source).toContain(
      'new URLSearchParams({ status: statusFilter, warehouse_id: selectedWarehouseId })',
    )
    expect(source).toContain('}, [search, selectedWarehouseId, statusFilter, token])')
    expect(source).toContain('}, [load, selectedWarehouseId])')
  })

  it('does not request the queue and shows the shared state without a warehouse context', () => {
    const loadStart = source.indexOf('const load = useCallback(async () => {')
    const noContextGuard = source.indexOf('if (!selectedWarehouseId)', loadStart)
    const queueRequest = source.indexOf(
      'fetch(apiUrl(`/operations/packaging-tasks?${params}`)',
      loadStart,
    )

    expect(loadStart).toBeGreaterThanOrEqual(0)
    expect(noContextGuard).toBeGreaterThan(loadStart)
    expect(queueRequest).toBeGreaterThan(noContextGuard)
    expect(source).toContain('!selectedWarehouseId ? <WarehouseNoContextState />')
  })
})
