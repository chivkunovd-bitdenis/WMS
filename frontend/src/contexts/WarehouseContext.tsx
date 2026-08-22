import { useCallback, useEffect, useState } from 'react'
import { chooseWarehouseId, operationalWarehouses, type FbsWarehouse } from '../utils/fbsWarehouse'

const STORAGE_PREFIX = 'wms_operational_warehouse:'
const CONTEXT_EVENT = 'wms:operational-warehouse-changed'

type WarehouseContextEvent = CustomEvent<{
  portal: 'fulfillment' | 'seller'
  warehouseId: string | null
}>

export function useWarehouseContext(portal: 'fulfillment' | 'seller') {
  const [warehouses, setWarehousesState] = useState<FbsWarehouse[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)

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
      const stored = sessionStorage.getItem(`${STORAGE_PREFIX}${portal}`)
      const next = chooseWarehouseId(operational, previous, stored)
      if (next) sessionStorage.setItem(`${STORAGE_PREFIX}${portal}`, next)
      return next
    })
  }, [portal])

  const selectWarehouse = useCallback((warehouseId: string | null) => {
    setSelectedWarehouseId(warehouseId)
    const key = `${STORAGE_PREFIX}${portal}`
    if (warehouseId) {
      sessionStorage.setItem(key, warehouseId)
    } else {
      sessionStorage.removeItem(key)
    }
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, warehouseId },
      }),
    )
  }, [portal])

  const clearWarehouseContext = useCallback(() => {
    sessionStorage.removeItem(`${STORAGE_PREFIX}${portal}`)
    setWarehousesState([])
    setSelectedWarehouseId(null)
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, warehouseId: null },
      }),
    )
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
