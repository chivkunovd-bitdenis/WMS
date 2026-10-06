import { useCallback, useEffect, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { ErrorNotice } from '../../../ui-kit'
import { FfWarehouseMapScreen } from './FfWarehouseMapScreen'
import { WarehousePrinterDialog } from './WarehousePrinterDialog'
import { InventoryCountDialog } from '../inventory/InventoryCountDialog'
import type { MapRow } from './WarehouseMapRows'
import type { WarehouseMapData } from './WarehouseMapTypes'
import type { CreateCellBody } from './WarehouseMapToolbar'
import {
  mapErrorMessage,
  humanError,
  placeOf,
  useWarehouseMapActions,
  type LoadOptions,
} from './useWarehouseMapActions'

// Карта склада, подключённая к серверу.
//
// Принятый экран ничего не знает про сеть: здесь выбирается склад, загружается
// его состав и подтверждаются сделанные оператором перемещения. Сама работа с
// сервером (перемещение, расформирование, печать ШК ячейки, пересчёт и тексты
// ошибок) — в хуке `useWarehouseMapActions` (WMS-490 D5): им же пользуется
// вкладка «Расположение» карточки товара, без второй копии той же логики.

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

const EMPTY_MAP: WarehouseMapData = {
  warehouses: [],
  sellers: [],
  categories: [],
  cells: [],
  unassigned: [],
  journal: [],
}

type Props = {
  token: string
  warehouses: Array<{ id: string; name: string }>
  isAdmin: boolean
}

export function FfWarehouseMapPage({ token, warehouses, isAdmin }: Props) {
  const [warehouseId, setWarehouseId] = useState<string | null>(warehouses[0]?.id ?? null)
  const [data, setData] = useState<WarehouseMapData | null>(
    warehouses.length === 0 ? EMPTY_MAP : null,
  )
  const [loading, setLoading] = useState(warehouses.length > 0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const selectedWarehouseRef = useRef(warehouseId)
  const loadVersionRef = useRef(0)
  const [printerOpen, setPrinterOpen] = useState(false)

  // Список складов в App загружается отдельно и может приехать после первого
  // рендера страницы. Если выбранный склад исчез, переходим на первый доступный.
  useEffect(() => {
    const current = selectedWarehouseRef.current
    const next = current && warehouses.some((warehouse) => warehouse.id === current)
      ? current
      : (warehouses[0]?.id ?? null)
    if (next === current) return
    loadVersionRef.current += 1
    selectedWarehouseRef.current = next
    setWarehouseId(next)
    setData(next ? null : EMPTY_MAP)
    setLoading(next !== null)
    setLoadError(null)
    setOperationError(null)
    setPrinterOpen(false)
  }, [warehouses])

  const load = useCallback(async (options: LoadOptions = {}) => {
    const requestWarehouseId = warehouseId
    const requestVersion = loadVersionRef.current + 1
    loadVersionRef.current = requestVersion

    if (!requestWarehouseId) {
      setData(EMPTY_MAP)
      setLoading(false)
      setLoadError(null)
      if (!options.preserveOperationError) setOperationError(null)
      return true
    }

    setLoading(true)
    setLoadError(null)
    if (!options.preserveOperationError) setOperationError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${requestWarehouseId}/map`), {
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      const next = (await res.json()) as WarehouseMapData
      if (requestVersion !== loadVersionRef.current) return false
      setData(next)
      return true
    } catch (err) {
      if (requestVersion !== loadVersionRef.current) return false
      setData(null)
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить карту склада')
      return false
    } finally {
      if (requestVersion === loadVersionRef.current) setLoading(false)
    }
  }, [token, warehouseId])

  useEffect(() => {
    void load()
  }, [load])

  function selectWarehouse(nextWarehouseId: string) {
    if (nextWarehouseId === selectedWarehouseRef.current) return
    loadVersionRef.current += 1
    selectedWarehouseRef.current = nextWarehouseId
    setWarehouseId(nextWarehouseId)
    setData(null)
    setLoading(true)
    setLoadError(null)
    setOperationError(null)
  }

  const actions = useWarehouseMapActions({
    token,
    warehouseId,
    data,
    setData,
    load,
    onError: setOperationError,
  })

  async function createCell(body: CreateCellBody): Promise<boolean> {
    const requestWarehouseId = selectedWarehouseRef.current
    if (!requestWarehouseId) {
      setOperationError('Сначала выберите склад: ячейка создаётся внутри склада.')
      return false
    }
    setOperationError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${requestWarehouseId}/locations`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      await load({ preserveOperationError: true })
      return true
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось создать ячейку'))
      return false
    }
  }

  async function createWarehouse(name: string, code: string) {
    setOperationError(null)
    try {
      const res = await fetch(apiUrl('/warehouses'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({ name, code }),
      })
      if (!res.ok) throw new Error(await mapErrorMessage(res))
      const created = (await res.json()) as { id: string }
      // Список складов на карте приезжает вместе с её составом, поэтому просто
      // переключаемся на новый: перечитывание запустит useEffect загрузки.
      selectWarehouse(created.id)
    } catch (err) {
      setOperationError(humanError(err, 'Не удалось создать склад'))
    }
  }

  return (
    <Box>
      {operationError ? (
        <ErrorNotice testId="warehouse-map-operation-error">{operationError}</ErrorNotice>
      ) : null}
      <FfWarehouseMapScreen
        addressing
        data={data}
        loading={loading}
        error={loadError}
        warehouseId={warehouseId}
        onWarehouseChange={selectWarehouse}
        onMove={actions.move}
        onCreateCell={createCell}
        onCreateWarehouse={(name: string, code: string) => void createWarehouse(name, code)}
        onPrinter={() => setPrinterOpen(true)}
        onPrintCell={actions.printCell}
        onInventory={(row: MapRow) => void actions.openInventory(row)}
        historyFor={(row: MapRow) =>
          // История строки — это не только то, что двигали саму строку, но и
          // то, что клали в неё и забирали из неё. Иначе у короба, в который
          // только что положили товар, история пустая: переезжал товар, а не
          // короб, и по одному названию строки запись не находится.
          data?.journal.filter(
            (entry) =>
              entry.subject === row.title ||
              entry.from_label === row.title ||
              entry.to_label === row.title,
          ) ?? []
        }
      />
      <WarehousePrinterDialog open={printerOpen} warehouseId={warehouseId} warehouseName={data?.warehouses.find((warehouse) => warehouse.id === warehouseId)?.name ?? ''} token={token} isAdmin={isAdmin} onClose={() => setPrinterOpen(false)} />
      <InventoryCountDialog
        open={actions.count !== null}
        title={actions.countTarget?.title ?? ''}
        place={data && actions.countTarget ? placeOf(data, actions.countTarget) : null}
        initialCount={actions.count}
        busy={actions.countBusy}
        onMarkEmpty={(edited, target) => void actions.markEmpty(edited, target)}
        onClose={actions.closeCount}
        onSave={(edited) => void actions.saveCount(edited)}
        onPost={(edited) => void actions.postAndClose(edited)}
      />
    </Box>
  )
}
