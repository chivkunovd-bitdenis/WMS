import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, Stack, ToggleButton, ToggleButtonGroup } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { pendingPlacement, placementStorageKey, rememberPlacement, sendPlacement, type PlacementBody } from './pendingPlacement'
import { randomId } from '../../../utils/randomId'
import { renderBarcodeDataUrl } from '../../../utils/renderBarcodeDataUrl'
import { printBarcodeLabel } from '../../../utils/printBarcodeLabel'
import type { LabelSize } from '../../../utils/labelSize'
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
  /**
   * Внутри документа сортировки склад уже известен, а заголовок документа стоит
   * выше — переключатель складов и собственная шапка здесь только мешают.
   */
  embedded?: boolean
  inboundRequestId?: string
  onPlaced?: () => Promise<unknown>
}

export function FfSortingObjectsPage({ token, warehouses, embedded, inboundRequestId, onPlaced }: Props) {
  const navigate = useNavigate()
  // Склад выбирается руками, как на карте: раскладка идёт на конкретном складе,
  // и молча показывать первый попавшийся значит врать оператору.
  const [warehouseId, setWarehouseId] = useState<string | null>(warehouses[0]?.id ?? null)

  // Список складов грузится в App отдельно и приезжает после первого рендера.
  // Состояние, заведённое пустым списком, так бы и осталось пустым, и экран
  // навсегда показывал бы «Нет складов» при живых складах.
  useEffect(() => {
    setWarehouseId((current) => {
      if (current && warehouses.some((one) => one.id === current)) return current
      return warehouses[0]?.id ?? null
    })
  }, [warehouses])
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
  const activeContext = useRef('')
  const context = `${token}:${warehouseId}:${inboundRequestId ?? ''}`
  activeContext.current = context
  const onPlacedRef = useRef(onPlaced)
  onPlacedRef.current = onPlaced

  const send = useCallback(async (body: PlacementBody, key: string | null) => {
    if (activeContext.current !== context) throw new Error('Открыт другой документ или сотрудник')
    return sendPlacement(localStorage, key, body, (confirmed) => fetch(
      apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify(confirmed),
      },
    ))
  }, [context, token, warehouseId])


  const load = useCallback(async (recover = true) => {
    if (!warehouseId) return
    try {
      if (recover && embedded && inboundRequestId) {
        const key = placementStorageKey(token, apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), inboundRequestId)
        const pending = pendingPlacement(localStorage, key)
        if (pending) {
          const response = await send(pending, key)
          if (!response.ok) throw new Error(await readApiErrorMessage(response))
          await onPlacedRef.current?.()
        }
      }
      const inboundQuery = embedded && inboundRequestId
        ? `?inbound_request_id=${encodeURIComponent(inboundRequestId)}`
        : ''
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects${inboundQuery}`), {
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const loaded = (await res.json()) as ApiSorting
      if (activeContext.current !== context) return
      setData(loaded)
      setVersion((current) => current + 1)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить раскладку'
      setError((current) => current ? `${current} ${message}` : message)
    }
  }, [context, embedded, inboundRequestId, token, warehouseId, send])

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
      const body = {
        kind: payload.kind, id: payload.id, cell_id: payload.cellId, to_id: payload.toId, qty: payload.qty,
        ...(embedded && inboundRequestId ? { inbound_request_id: inboundRequestId } : {}),
      }
      // Only document loose putaway has the durable operation receipt contract.
      const key = embedded && inboundRequestId && payload.kind === 'product' && payload.cellId
        ? placementStorageKey(token, apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), inboundRequestId)
        : null
      const confirmed = key ? rememberPlacement(localStorage, key, body) : { ...body, operation_id: randomId() }
      const res = await send(confirmed, key)
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      await onPlacedRef.current?.()
      await load(false)
    } catch (err) {
      // Экран уже переставил строку у себя. Показываем отказ и перечитываем
      // склад: иначе на экране будет одно, а в системе другое, и оператор
      // узнает об этом на инвентаризации.
      setError(`${err instanceof Error ? err.message : 'Нет ответа сервера'}. Обновите документ, чтобы проверить результат размещения.`)
      await load(false)
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

  const warehouseName = warehouses.find((one) => one.id === warehouseId)?.name ?? ''

  async function createCell(code: string) {
    if (!warehouseId) return
    setError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({ code }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать ячейку')
    }
  }

  async function createObject(kind: 'pallet' | 'box' | 'cargo_place') {
    if (!warehouseId) return
    setError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        // Тара, созданная внутри документа приёмки, обязана нести ссылку на
        // него (§A-03) — иначе документный фильтр её потом не находит: объект
        // создаётся, но в приёмке, откуда его создали, не появляется.
        body: JSON.stringify({
          kind,
          ...(embedded && inboundRequestId ? { inbound_request_id: inboundRequestId } : {}),
        }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать тару')
    }
  }

  function printLabel(title: string, barcode: string, size: LabelSize) {
    printBarcodeLabel({
      title,
      barcode,
      barcodeDataUrl: renderBarcodeDataUrl(barcode, { variant: 'storageCell' }),
      labelSize: size,
      layout: 'storageCell',
    })
  }

  return (
    <Box>
      {error ? <ErrorNotice testId="sorting-objects-error">{error}</ErrorNotice> : null}
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ mb: 2, flexWrap: 'wrap', display: embedded ? 'none' : 'flex' }}
      >
        <ToggleButtonGroup
          exclusive
          size="small"
          value={warehouseId}
          onChange={(_event, value: string | null) => {
            if (value) setWarehouseId(value)
          }}
          aria-label="Склад"
          data-testid="sorting-objects-warehouses"
          sx={{ flexWrap: 'wrap' }}
        >
          {warehouses.map((warehouse) => (
            <ToggleButton
              key={warehouse.id}
              value={warehouse.id}
              data-testid={`sorting-objects-warehouse-${warehouse.id}`}
              sx={{ textTransform: 'none', fontWeight: 600, px: 1.75 }}
            >
              {warehouse.name}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>
      {data ? (
        <SortingObjectsScreen
          key={`${warehouseId}-${version}`}
          onNote={() => undefined}
          initialObjects={data.objects}
          initialLines={data.lines}
          products={data.products}
          initialCells={data.cells}
          onPlace={(payload) => void place(payload)}
          purpose={
            embedded
              ? 'Собираем объект и ставим готовый объект на полку.'
              : `Склад ${warehouseName}. Собираем объект и ставим готовый объект на полку.`
          }
          warehouseName={warehouseName}
          onCreateCell={(code) => void createCell(code)}
          onPrint={(title, barcode, size) => printLabel(title, barcode, size)}
          onClose={() => navigate('/app/ff/sorting')}
          onCreateObject={(kind) => void createObject(kind)}
          savedImmediately
        />
      ) : (
        <EmptyState title="Загружаем склад" hint="Считаем, что где лежит." />
      )}
    </Box>
  )
}
