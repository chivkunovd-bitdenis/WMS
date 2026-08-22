import { createContext, useContext, ReactNode, useState, useEffect } from 'react'

export interface Warehouse {
  id: string
  name: string
  code: string
  is_auto_fbs?: boolean
}

interface WarehouseContextType {
  selectedWarehouseId: string | null
  warehouses: Warehouse[]
  isLoading: boolean
  error: string | null
  selectWarehouse: (warehouseId: string) => void
  setWarehouses: (warehouses: Warehouse[]) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

const WarehouseContext = createContext<WarehouseContextType | null>(null)

export function WarehouseProvider({ children }: { children: ReactNode }) {
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [isLoading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Загрузка начального значения из localStorage при первой загрузке
  useEffect(() => {
    const savedWarehouseId = localStorage.getItem('selectedWarehouseId')
    if (savedWarehouseId) {
      setSelectedWarehouseId(savedWarehouseId)
    }
  }, [])

  // Сохранение выбранного склада в localStorage
  useEffect(() => {
    if (selectedWarehouseId) {
      localStorage.setItem('selectedWarehouseId', selectedWarehouseId)
    }
  }, [selectedWarehouseId])

  const selectWarehouse = (warehouseId: string) => {
    setSelectedWarehouseId(warehouseId)
  }

  return (
    <WarehouseContext.Provider
      value={{
        selectedWarehouseId,
        warehouses,
        isLoading,
        error,
        selectWarehouse,
        setWarehouses,
        setLoading,
        setError,
      }}
    >
      {children}
    </WarehouseContext.Provider>
  )
}

export function useWarehouse() {
  const context = useContext(WarehouseContext)
  if (!context) {
    throw new Error('useWarehouse must be used within WarehouseProvider')
  }
  return context
}
