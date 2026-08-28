import { useCallback, useEffect, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { EmptyState, ErrorNotice } from '../../../ui-kit'
import { SortingObjectsScreen } from './SortingObjectsScreen'
import type { Cell, GoodsLine, ObjKind, Product, WarehouseObject } from './objectsStub'

// Раскладка по объектам, подключённая к серверу.
//
// Экран приняли по макету, и он не знает про сеть. Здесь только загрузка склада
// и отправка того, что оператор поставил на полку.

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

type ApiSorting = {
  objects: WarehouseObject[]
  lines: GoodsLine[]
  products: Product[]
  cells: Cell[]
}

type Props = {
  token: string
  warehouses: Array<{ id: string; name: string }>
}

export function FfSortingObjectsPage({ token, warehouses }: Props) {
  const warehouseId = warehouses[0]?.id ?? null
  const [data, setData] = useState<ApiSorting | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Счётчик загрузок нужен как ключ экрана.
  //
  // Экран принимает состав склада НАЧАЛЬНЫМ состоянием: он им дальше двигает
  // сам, и перезаписывать его на каждый ответ сервера значило бы отменять
  // работу оператора под руками. Но приехавшие позже данные он бы и не увидел.
  // Смена ключа пересобирает экран заново — ровно тогда, когда пришёл новый
  // состав, и ни разу между.
  const [version, setVersion] = useState(0)

  const load = useCallback(async () => {
    if (!warehouseId) return
    setError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects`), {
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setData((await res.json()) as ApiSorting)
      setVersion((current) => current + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить раскладку')
    }
  }, [token, warehouseId])

  useEffect(() => {
    void load()
  }, [load])

  async function place(payload: {
    kind: ObjKind | 'product'
    id: string
    cellId: string | null
    toId: string | null
    qty: number
  }) {
    if (!warehouseId) return
    setError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({
          kind: payload.kind,
          id: payload.id,
          cell_id: payload.cellId,
          to_id: payload.toId,
          qty: payload.qty,
        }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
    } catch (err) {
      // Экран уже переставил строку у себя. Показываем отказ и перечитываем
      // склад: иначе на экране будет одно, а в системе другое, и оператор
      // узнает об этом на инвентаризации.
      setError(err instanceof Error ? err.message : 'Не удалось поставить объект')
      await load()
    }
  }

  if (!warehouseId) {
    return (
      <EmptyState
        title="Нет складов"
        hint="Раскладывать некуда: заведите склад в настройках."
      />
    )
  }

  return (
    <Box>
      {error ? <ErrorNotice testId="sorting-objects-error">{error}</ErrorNotice> : null}
      {data ? (
        <SortingObjectsScreen
          key={`${warehouseId}-${version}`}
          onNote={() => undefined}
          initialObjects={data.objects}
          initialLines={data.lines}
          products={data.products}
          initialCells={data.cells}
          onPlace={(payload) => void place(payload)}
        />
      ) : (
        <EmptyState title="Загружаем склад" hint="Считаем, что где лежит." />
      )}
    </Box>
  )
}
