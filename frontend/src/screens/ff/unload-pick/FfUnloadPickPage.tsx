import { useCallback, useEffect, useMemo, useState } from 'react'
import { Box } from '@mui/material'
import { useNavigate, useParams } from 'react-router-dom'
import { apiUrl } from '../../../api'
import { useMarketplaceProductCatalog } from '../../../hooks/useWbProductCatalog'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { EmptyState, ErrorNotice } from '../../../ui-kit'
import { UnloadPickScreen, type UnloadPickScanResult } from './UnloadPickScreen'
import { cellRef, type Cell, type GoodsLine, type PickProduct, type PlanLine } from './pickStub'
import { pickKey, type PickedMap } from './pickRows'

// Принятый экран подбора, подключённый к серверу.
//
// Экран по-прежнему ничего не знает про HTTP: здесь загружаются документ и
// варианты мест, а каждое снятие сразу сохраняется. Если сервер отказал после
// оптимистичного изменения, перечитываем документ — иначе оператор продолжит
// работу по цифрам, которых в системе на самом деле нет.

const BASE = '/operations/marketplace-unload-requests'

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

type ApiLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  picked_qty: number
}

type ApiDetail = {
  id: string
  document_number: string | null
  display_number: string | null
  warehouse_name: string
  status: string
  seller_id: string | null
  seller_name: string | null
  planned_shipment_date: string | null
  lines: ApiLine[]
}

type ApiPickLocation = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
  picked: number
}

type ApiPickProduct = {
  product_id: string
  sku_code: string
  product_name: string
  planned_qty: number
  picked_qty: number
  locations: ApiPickLocation[]
}

type ApiScanResult = {
  kind: 'location' | 'product'
  storage_location_id: string | null
  location_code: string | null
  product_id: string | null
  sku_code: string | null
  product_name: string | null
  picked_qty: number | null
  allocation_quantity: number | null
}

type ApiPickAllocation = {
  product_id: string
  storage_location_id: string | null
  quantity: number
}

function formatDate(value: string | null): string | null {
  if (!value) return null
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  return new Intl.DateTimeFormat('ru-RU').format(new Date(year, month - 1, day))
}

function sourceLocationId(sourceKey: string | null): string | null {
  return sourceKey?.startsWith('cell:') ? sourceKey.slice(5) : null
}

type Props = { token: string }

export function FfUnloadPickPage({ token }: Props) {
  const { requestId } = useParams<{ requestId: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ApiDetail | null>(null)
  const [pickOptions, setPickOptions] = useState<ApiPickProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const {
    catalogById,
    error: catalogError,
  } = useMarketplaceProductCatalog(token, Boolean(detail?.seller_id), detail?.seller_id)

  const load = useCallback(async () => {
    if (!requestId) {
      setError('Не указан номер отгрузки')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [detailRes, optionsRes] = await Promise.all([
        fetch(apiUrl(`${BASE}/${requestId}`), { headers: headers(token) }),
        fetch(apiUrl(`${BASE}/${requestId}/pick-options`), { headers: headers(token) }),
      ])
      if (!detailRes.ok) throw new Error(await readApiErrorMessage(detailRes))
      if (!optionsRes.ok) throw new Error(await readApiErrorMessage(optionsRes))
      setDetail((await detailRes.json()) as ApiDetail)
      setPickOptions((await optionsRes.json()) as ApiPickProduct[])
      setVersion((current) => current + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть подбор')
    } finally {
      setLoading(false)
    }
  }, [requestId, token])

  useEffect(() => {
    void load()
  }, [load])

  const screenData = useMemo(() => {
    if (!detail) return null

    // Состав строится только из lines документа. Даже если складской ответ
    // содержит больше товаров, чужой состав тары на этом экране не появится.
    const products: PickProduct[] = detail.lines.map((line) => {
      const catalog = catalogById.get(line.product_id)
      return {
        id: line.product_id,
        name: line.product_name,
        sku: line.sku_code,
        barcode: catalog?.wb_primary_barcode ?? catalog?.wb_barcodes[0] ?? '',
        photo: catalog?.wb_primary_image_url ?? '',
        size: catalog?.wb_size ?? null,
      }
    })
    const plan: PlanLine[] = detail.lines.map((line) => ({
      id: line.id,
      productId: line.product_id,
      plan: line.quantity,
    }))

    const cellsById = new Map<string, Cell>()
    const stock: GoodsLine[] = []
    const picked: PickedMap = {}
    for (const product of pickOptions) {
      for (const location of product.locations) {
        cellsById.set(location.storage_location_id, {
          id: location.storage_location_id,
          code: location.location_code,
          // pick-options не раскрывает отдельный ШК ячейки. Код нужен для
          // ручного ввода, а настоящий штрихкод распознаёт scan-роут сервера.
          barcode: location.location_code,
        })
        const holder = cellRef(location.storage_location_id)
        stock.push({
          id: `${product.product_id}-${location.storage_location_id}`,
          productId: product.product_id,
          // Остаток уже уменьшен предыдущими снятиями. Возвращаем picked к
          // доступному, чтобы поле могло показать и уменьшить сохранённый факт.
          qty: location.available + location.picked,
          holder,
        })
        picked[pickKey(product.product_id, holder)] = location.picked
      }
    }

    const number = detail.display_number ?? detail.document_number ?? detail.id
    const date = formatDate(detail.planned_shipment_date)
    return {
      document: `Отгрузка ${number}${date ? ` от ${date}` : ''} · ${detail.warehouse_name}`,
      seller: detail.seller_name ?? '—',
      products,
      plan,
      stock,
      cells: [...cellsById.values()],
      picked,
    }
  }, [catalogById, detail, pickOptions])

  const updateOption = useCallback(
    (productId: string, locationId: string, quantity: number) => {
      setPickOptions((current) =>
        current.map((product) => {
          if (product.product_id !== productId) return product
          const location = product.locations.find(
            (one) => one.storage_location_id === locationId,
          )
          if (!location) return product
          const delta = quantity - location.picked
          return {
            ...product,
            picked_qty: Math.max(0, product.picked_qty + delta),
            locations: product.locations.map((one) =>
              one.storage_location_id === locationId
                ? {
                    ...one,
                    picked: quantity,
                    available: Math.max(0, one.available - delta),
                  }
                : one,
            ),
          }
        }),
      )
    },
    [],
  )

  const setPicked = useCallback(
    async (payload: { productId: string; place: { key: string }; quantity: number }) => {
      if (!requestId) return
      const locationId = sourceLocationId(payload.place.key)
      if (!locationId) {
        setError('Сервер не вернул ячейку, из которой снимается товар')
        await load()
        return
      }
      setBusy(true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`${BASE}/${requestId}/pick/set`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify({
            product_id: payload.productId,
            storage_location_id: locationId,
            quantity: payload.quantity,
          }),
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
        const saved = (await res.json()) as ApiPickAllocation
        updateOption(payload.productId, locationId, saved.quantity)
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'Не удалось сохранить снятое количество'
        setError(message)
        await load()
        setError(message)
      } finally {
        setBusy(false)
      }
    },
    [load, requestId, token, updateOption],
  )

  const scan = useCallback(
    async ({ barcode, sourceKey }: { barcode: string; sourceKey: string | null }) => {
      if (!requestId) throw new Error('Не указан номер отгрузки')

      const normalized = barcode.trim().toLowerCase()
      const matchedProduct = screenData?.products.find((product) => {
        const catalog = catalogById.get(product.id)
        return (
          product.sku.toLowerCase() === normalized ||
          product.barcode === barcode ||
          catalog?.wb_barcodes.some((one) => one === barcode)
        )
      })
      let locationId = sourceLocationId(sourceKey)
      if (matchedProduct && !locationId) {
        const option = pickOptions.find((one) => one.product_id === matchedProduct.id)
        const candidates = option?.locations.filter((one) => one.available > 0) ?? []
        if (candidates.length === 0) {
          throw new Error(`${matchedProduct.sku} — этого товара нет на складе`)
        }
        if (candidates.length > 1) {
          throw new Error(
            `${matchedProduct.sku} лежит в ${candidates.length} местах — уточните место или укажите число руками`,
          )
        }
        locationId = candidates[0].storage_location_id
      }

      setBusy(true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`${BASE}/${requestId}/pick/scan`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify({
            barcode,
            ...(matchedProduct ? { product_id: matchedProduct.id } : {}),
            storage_location_id: locationId,
          }),
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
        const result = (await res.json()) as ApiScanResult
        if (result.kind === 'location') {
          if (!result.storage_location_id || !result.location_code) {
            throw new Error('Сервер распознал ячейку, но не вернул её адрес')
          }
          return {
            kind: 'location',
            storageLocationId: result.storage_location_id,
            locationCode: result.location_code,
          } satisfies UnloadPickScanResult
        }
        if (
          !result.product_id ||
          !result.sku_code ||
          !result.product_name ||
          result.picked_qty == null ||
          result.allocation_quantity == null
        ) {
          throw new Error('Сервер не вернул результат снятия товара')
        }
        if (result.storage_location_id) {
          updateOption(result.product_id, result.storage_location_id, result.allocation_quantity)
        }
        return {
          kind: 'product',
          storageLocationId: result.storage_location_id,
          productId: result.product_id,
          sku: result.sku_code,
          productName: result.product_name,
          pickedQty: result.picked_qty,
          allocationQuantity: result.allocation_quantity,
        } satisfies UnloadPickScanResult
      } finally {
        setBusy(false)
      }
    },
    [catalogById, pickOptions, requestId, screenData?.products, token, updateOption],
  )

  if (loading && !screenData) {
    return <EmptyState title="Загружаем подбор" hint="Получаем состав отгрузки и места хранения." />
  }
  if (!screenData) {
    return (
      <Box>
        <ErrorNotice testId="unload-pick-load-error">
          {error ?? 'Не удалось открыть подбор'}
        </ErrorNotice>
      </Box>
    )
  }

  return (
    <Box>
      {error || catalogError ? (
        <ErrorNotice testId="unload-pick-error">{error ?? catalogError}</ErrorNotice>
      ) : null}
      <UnloadPickScreen
        key={`${requestId}-${version}`}
        onNote={() => undefined}
        document={screenData.document}
        seller={screenData.seller}
        products={screenData.products}
        plan={screenData.plan}
        stock={screenData.stock}
        objects={[]}
        cells={screenData.cells}
        initialPicked={screenData.picked}
        busy={busy}
        onSetPicked={setPicked}
        onScan={scan}
        onPause={() => navigate('/app/ff/mp-shipments')}
        onComplete={() =>
          navigate(`/app/ff/mp-shipments?open_mp=${encodeURIComponent(requestId ?? '')}`)
        }
      />
    </Box>
  )
}
