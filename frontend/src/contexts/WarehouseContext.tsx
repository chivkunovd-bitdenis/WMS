import { useCallback, useEffect, useState } from 'react'
import { chooseWarehouseId, operationalWarehouses, type FbsWarehouse } from '../utils/fbsWarehouse'

const STORAGE_PREFIX = 'wms_operational_warehouse:'
const CONTEXT_EVENT = 'wms:operational-warehouse-changed'

type WarehouseContextEvent = CustomEvent<{
  portal: 'fulfillment' | 'seller'
  warehouseId: string | null
}>

function readStoredWarehouse(storageKey: string): string | null {
  try {
    return window.sessionStorage.getItem(storageKey)
  } catch {
    return null
  }
}

function writeStoredWarehouse(storageKey: string, warehouseId: string | null): void {
  try {
    if (warehouseId) {
      window.sessionStorage.setItem(storageKey, warehouseId)
    } else {
      window.sessionStorage.removeItem(storageKey)
    }
  } catch {
    // The current in-memory context remains usable when storage is unavailable.
  }
}

export function useWarehouseContext(portal: 'fulfillment' | 'seller') {
  const [warehouses, setWarehousesState] = useState<FbsWarehouse[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)
  const storageKey = `${STORAGE_PREFIX}${portal}`

  useEffect(() => {
    const onContextChange = (event: Event) => {
      const detail = (event as WarehouseContextEvent).detail
      if (detail?.portal === portal) {
        setSelectedWarehouseId(detail.warehouseId)
      }
    }
    window.addEventListener(CONTEXT_EVENT, onContextChange)
    return () => window.removeEventListener(CONTEXT_EVENT, onContextChange)
  }, [portal])

  const setWarehouses = useCallback((rows: FbsWarehouse[]) => {
    const operational = operationalWarehouses(rows)
    setWarehousesState(operational)
    setSelectedWarehouseId((previous) => {
      const stored = readStoredWarehouse(storageKey)
      const next = chooseWarehouseId(operational, previous, stored)
      if (next) writeStoredWarehouse(storageKey, next)
      return next
    })
  }, [storageKey])

  const selectWarehouse = useCallback((warehouseId: string | null) => {
    setSelectedWarehouseId(warehouseId)
    writeStoredWarehouse(storageKey, warehouseId)
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, warehouseId },
      }),
    )
  }, [portal, storageKey])

  const clearWarehouseContext = useCallback(() => {
    writeStoredWarehouse(storageKey, null)
    setWarehousesState([])
    setSelectedWarehouseId(null)
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, warehouseId: null },
      }),
    )
  }, [portal, storageKey])

  return {
    warehouses,
    selectedWarehouseId,
    setWarehouses,
    selectWarehouse,
    setSelectedWarehouseId,
    clearWarehouseContext,
  }
}
