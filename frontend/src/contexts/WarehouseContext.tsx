import { useCallback, useState } from 'react'
import { chooseWarehouseId, operationalWarehouses, type FbsWarehouse } from '../utils/fbsWarehouse'

const STORAGE_PREFIX = 'wms_operational_warehouse:'

export function useWarehouseContext(portal: 'fulfillment' | 'seller') {
  const [warehouses, setWarehousesState] = useState<FbsWarehouse[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)

  const setWarehouses = useCallback((rows: FbsWarehouse[]) => {
    const operational = operationalWarehouses(rows)
    setWarehousesState(operational)
    setSelectedWarehouseId((previous) => {
      const stored = sessionStorage.getItem(`${STORAGE_PREFIX}${portal}`)
      const next = chooseWarehouseId(operational, previous, stored)
      if (next) sessionStorage.setItem(`${STORAGE_PREFIX}${portal}`, next)
      return next
    })
  }, [portal])

  const selectWarehouse = useCallback((warehouseId: string | null) => {
    setSelectedWarehouseId(warehouseId)
    if (warehouseId) sessionStorage.setItem(`${STORAGE_PREFIX}${portal}`, warehouseId)
  }, [portal])

  const clearWarehouseContext = useCallback(() => {
    sessionStorage.removeItem(`${STORAGE_PREFIX}${portal}`)
    setWarehousesState([])
    setSelectedWarehouseId(null)
  }, [portal])

  return {
    warehouses,
    selectedWarehouseId,
    setWarehouses,
    selectWarehouse,
    setSelectedWarehouseId,
    clearWarehouseContext,
  }
}
