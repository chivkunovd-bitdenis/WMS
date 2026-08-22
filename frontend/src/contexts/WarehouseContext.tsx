import { useCallback, useEffect, useState } from 'react'
import { chooseWarehouseId, operationalWarehouses, type FbsWarehouse } from '../utils/fbsWarehouse'

const STORAGE_PREFIX = 'wms_operational_warehouse:'
const CONTEXT_EVENT = 'wms:operational-warehouse-changed'

type WarehouseContextEvent = CustomEvent<{
  portal: 'fulfillment' | 'seller'
  sessionId: string | null
  warehouseId: string | null
}>

export function useWarehouseContext(
  portal: 'fulfillment' | 'seller',
  sessionId: string | null = null,
) {
  const [warehouses, setWarehousesState] = useState<FbsWarehouse[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)
  const storageKey = sessionId
    ? `${STORAGE_PREFIX}${portal}:${sessionId}`
    : `${STORAGE_PREFIX}${portal}`

  useEffect(() => {
    const onContextChange = (event: Event) => {
      const detail = (event as WarehouseContextEvent).detail
      if (detail?.portal === portal && detail.sessionId === sessionId) {
        setSelectedWarehouseId(detail.warehouseId)
      }
    }
    window.addEventListener(CONTEXT_EVENT, onContextChange)
    return () => window.removeEventListener(CONTEXT_EVENT, onContextChange)
  }, [portal, sessionId])

  useEffect(() => {
    setWarehousesState([])
    setSelectedWarehouseId(null)
  }, [sessionId])

  const setWarehouses = useCallback((rows: FbsWarehouse[]) => {
    const operational = operationalWarehouses(rows)
    setWarehousesState(operational)
    setSelectedWarehouseId((previous) => {
      const stored = storageKey ? sessionStorage.getItem(storageKey) : null
      const next = chooseWarehouseId(operational, previous, stored)
      if (next && storageKey) sessionStorage.setItem(storageKey, next)
      return next
    })
  }, [storageKey])

  const selectWarehouse = useCallback((warehouseId: string | null) => {
    setSelectedWarehouseId(warehouseId)
    if (storageKey) {
      if (warehouseId) {
        sessionStorage.setItem(storageKey, warehouseId)
      } else {
        sessionStorage.removeItem(storageKey)
      }
    }
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, sessionId, warehouseId },
      }),
    )
  }, [portal, sessionId, storageKey])

  const clearWarehouseContext = useCallback(() => {
    if (storageKey) sessionStorage.removeItem(storageKey)
    setWarehousesState([])
    setSelectedWarehouseId(null)
    window.dispatchEvent(
      new CustomEvent<WarehouseContextEvent['detail']>(CONTEXT_EVENT, {
        detail: { portal, sessionId, warehouseId: null },
      }),
    )
  }, [portal, sessionId, storageKey])

  return {
    warehouses,
    selectedWarehouseId,
    setWarehouses,
    selectWarehouse,
    setSelectedWarehouseId,
    clearWarehouseContext,
  }
}
