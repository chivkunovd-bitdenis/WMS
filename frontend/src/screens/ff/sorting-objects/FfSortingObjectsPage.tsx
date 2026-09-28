import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, Stack, ToggleButton, ToggleButtonGroup } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { canRememberSortingPlacement, pendingPlacement, placementFailureMessage, placementStorageKey, rememberPlacement, sendPlacement, type PlacementBody } from './pendingPlacement'
import { randomId } from '../../../utils/randomId'
import { renderBarcodeDataUrl } from '../../../utils/renderBarcodeDataUrl'
import { printBarcodeLabel } from '../../../utils/printBarcodeLabel'
import type { LabelSize } from '../../../utils/labelSize'
import { EmptyState, ErrorNotice } from '../../../ui-kit'
import { SortingObjectsScreen } from './SortingObjectsScreen'
import type { Cell, GoodsLine, ObjKind, Product, WarehouseObject } from './objectsStub'
import { pendingScan, rememberScan, sendScan, type ScanBody } from './pendingScan'
import { RejectedScan, type ScanContext } from './sortingScan'
import { applyScanResult, type ScanResult } from './scanResult'
import { objectQty } from './objectsStub'

// Раскладка по объектам, подключённая к серверу.
//
// Экран приняли по макету, и он не знает про сеть. Здесь только загрузка склада
// и отправка того, что оператор поставил на полку.

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

type ApiSorting = {
  remainingQty?: number
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
  const dataRef = useRef<ApiSorting | null>(null)
  const parentRefresh = useRef<ReturnType<typeof setTimeout> | null>(null)
  const updateData = (next: ApiSorting) => { dataRef.current = next; setData(next) }
  const [error, setError] = useState<string | null>(null)
  const [loadedContext, setLoadedContext] = useState('')
  const activeContext = useRef('')
  const context = `${token}:${warehouseId}:${inboundRequestId ?? ''}`
  activeContext.current = context
  const onPlacedRef = useRef(onPlaced)
  onPlacedRef.current = onPlaced
  const scanIdle = () => {
    if (parentRefresh.current) clearTimeout(parentRefresh.current)
    parentRefresh.current = setTimeout(() => {
      if (activeContext.current === context) void onPlacedRef.current?.().catch(() => undefined)
    }, 1500)
  }
  useEffect(() => () => { if (parentRefresh.current) clearTimeout(parentRefresh.current) }, [])
  const scanKey = embedded && inboundRequestId && warehouseId
    ? placementStorageKey(token, apiUrl(`/warehouses/${warehouseId}/sorting-objects/scan`), inboundRequestId)
    : null

  const sendProductScan = useCallback(async (body: ScanBody, key: string) => {
    if (activeContext.current !== context) throw new Error('Открыт другой документ или сотрудник')
    return sendScan(localStorage, key, body, (confirmed) => fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects/scan`), {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...headers(token) }, body: JSON.stringify(confirmed),
    }))
  }, [context, token, warehouseId])

  const send = useCallback(async (body: PlacementBody, key: string | null) => {
    if (activeContext.current !== context) throw new Error('Открыт другой документ или сотрудник')
    return sendPlacement(localStorage, key, body, (confirmed) => fetch(
      apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify(confirmed),
      },
    ))
  }, [context, token, warehouseId])


  const load = useCallback(async (recover = true): Promise<boolean> => {
    if (!warehouseId) return false
    try {
      if (recover && scanKey) {
        const pending = pendingScan(localStorage, scanKey)
        if (pending) {
          const response = await sendProductScan(pending, scanKey)
          if (!response.ok) throw new Error(await readApiErrorMessage(response))
          await onPlacedRef.current?.()
        }
      }
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
      if (activeContext.current !== context) return false
      updateData(loaded)
      setLoadedContext(context)
      return true
    } catch (err) {
      const message = placementFailureMessage(err)
      // A placement can have committed just before its reply or re-read failed.
      // Keep that warning intact instead of appending a second transport error.
      setError((current) => current ?? message)
      return false
    }
  }, [context, embedded, inboundRequestId, token, warehouseId, send, scanKey, sendProductScan])

  useEffect(() => {
    void load()
  }, [load])

  async function place(payload: {
    kind: ObjKind | 'product'
    id: string
    cellId: string | null
    toId: string | null
    qty: number
    sourceHolder: string | null
    operationId?: string
  }) {
    if (!warehouseId) throw new Error('Склад не выбран')
    setError(null)
    try {
      const body = {
        kind: payload.kind, id: payload.id, cell_id: payload.cellId, to_id: payload.toId, qty: payload.qty,
        ...(embedded && inboundRequestId ? { inbound_request_id: inboundRequestId } : {}),
      }
      // The document receipt exists only for top-level loose stock. A product
      // inside a box or cargo place uses the ordinary warehouse move, which a
      // page reload must never replay physically.
      const key = embedded && inboundRequestId && canRememberSortingPlacement(payload)
        ? placementStorageKey(token, apiUrl(`/warehouses/${warehouseId}/sorting-objects/place`), inboundRequestId)
        : null
      const confirmed = key ? rememberPlacement(localStorage, key, body) : { ...body, operation_id: payload.operationId ?? randomId() }
      const res = await send(confirmed, key)
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        throw [400, 404, 409, 422].includes(res.status) ? new RejectedScan(message) : new Error(message)
      }
      const current = dataRef.current
      if (payload.operationId && payload.kind !== 'product' && payload.cellId && current && objectQty(payload.id, current.objects, current.lines) === 0) {
        updateData({ ...current, objects: current.objects.map((one) => one.id === payload.id ? { ...one, holder: `cell:${payload.cellId}` } : one) })
        return
      }
      await onPlacedRef.current?.()
      if (!await load(false)) throw new Error('Размещение сохранено, но состав не обновлён. Обновите документ для проверки результата.')
    } catch (err) {
      // Экран уже переставил строку у себя. Показываем отказ и перечитываем
      // склад: иначе на экране будет одно, а в системе другое, и оператор
      // узнает об этом на инвентаризации.
      setError(`${placementFailureMessage(err)} Обновите документ, чтобы проверить результат размещения.`)
      if (!await load(false)) setData(null)
      throw err
    }
  }

  async function scanProduct(barcode: string, selected: ScanContext, operationId: string) {
    if (!scanKey || !inboundRequestId || !selected.cellId) throw new Error('Откройте документ приёмки и отсканируйте ячейку')
    setError(null)
    if (parentRefresh.current) clearTimeout(parentRefresh.current)
    try {
      const body = rememberScan(localStorage, scanKey, {
        inbound_request_id: inboundRequestId, barcode, cell_id: selected.cellId, to_id: selected.objectId,
      }, operationId)
      const response = await sendProductScan(body, scanKey)
      if (!response.ok) {
        const detail = response.status === 409 ? (await response.clone().json() as { detail?: string }).detail : null
        if (detail === 'already_in_target') {
          if (!await load(false)) throw new Error('Не удалось обновить состав. Обновите документ для проверки результата.')
          return 'Товар уже находится в выбранном месте'
        }
        const message = await readApiErrorMessage(response)
        throw [400, 404, 409, 422].includes(response.status) ? new RejectedScan(message) : new Error(message)
      }
      const result = await response.json() as ScanResult
      const current = dataRef.current
      const lines = current ? applyScanResult(current.lines, result) : null
      if (current && lines) updateData({ ...current, lines, remainingQty: result.remaining_qty ?? undefined })
      else if (!await load(false)) throw new Error('Скан сохранён, но состав не обновлён. Повторите проверку ответа.')
    } catch (err) {
      const message = placementFailureMessage(err)
      setError(message)
      throw err instanceof RejectedScan ? err : new Error(message)
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
      {data && loadedContext === context ? (
        <SortingObjectsScreen
          key={context}
          onNote={() => undefined}
          initialObjects={data.objects}
          initialLines={data.lines}
          products={data.products}
          initialCells={data.cells}
          onPlace={place}
          onProductScan={scanProduct}
          onScanIdle={scanIdle}
          remainingQty={data.remainingQty}
          scanStorageKey={scanKey ? `${scanKey}:context` : undefined}
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
