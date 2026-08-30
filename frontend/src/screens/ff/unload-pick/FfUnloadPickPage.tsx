import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { useNavigate, useParams } from 'react-router-dom'
import { apiUrl } from '../../../api'
import { useMarketplaceProductCatalog } from '../../../hooks/useWbProductCatalog'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { EmptyState, ErrorNotice } from '../../../ui-kit'
import { UnloadPickScreen, type UnloadPickScanResult } from './UnloadPickScreen'
import {
  cellRef,
  objRef,
  type Cell,
  type GoodsLine,
  type ObjKind,
  type PickProduct,
  type PlanLine,
  type WarehouseObject,
} from './pickStub'
import { pickKey, type PickedMap } from './pickRows'

// Принятый экран подбора, подключённый к серверу.
//
// Экран по-прежнему ничего не знает про HTTP: здесь загружаются документ и
// варианты мест, а каждое снятие сразу сохраняется. Если сервер отказал после
// оптимистичного изменения, перечитываем документ — иначе оператор продолжит
// работу по цифрам, которых в системе на самом деле нет.

const UNLOAD_BASE = '/operations/marketplace-unload-requests'
const FBS_BASE = '/operations/fbs-supplies'

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
  name?: string | null
  wb_supply_id?: string | null
  document_number: string | null
  display_number: string | null
  warehouse_name?: string | null
  status: string
  seller_id: string | null
  seller_name: string | null
  planned_shipment_date: string | null
  // У поставки ФБС состава в документе нет: там товары приходят вместе с
  // местами подбора. Поэтому поле необязательное, а состав ниже собирается
  // из того источника, который его реально отдаёт.
  lines?: ApiLine[]
}

/** Ступень тары снаружи внутрь: палета, потом короб на ней. */
type ApiContainerStep = {
  kind: ObjKind
  id: string
  code: string
  label: string
}

/**
 * Один физический источник внутри ячейки: короб, грузоместо, палета или россыпь.
 *
 * Сервер не делит по таре агрегаты `quantity`/`reserved`/`available`/`picked` —
 * они остаются на всё место целиком. Поэтому долю каждого источника считаем
 * здесь, а сохраняем по-прежнему сумму на ячейку: ручка `pick/set` принимает
 * только `storage_location_id`.
 */
type ApiPickSource = {
  quantity: number
  is_loose: boolean
  source_label: string
  container_path: ApiContainerStep[]
  /** Сколько уже снято именно отсюда — считает сервер, экран не угадывает. */
  picked?: number
}

type ApiPickLocation = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
  picked: number
  sources?: ApiPickSource[]
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
  kind: 'location' | 'container' | 'product'
  storage_location_id: string | null
  location_code: string | null
  product_id: string | null
  sku_code: string | null
  product_name: string | null
  picked_qty: number | null
  allocation_quantity: number | null
  container_kind: ObjKind | null
  container_id: string | null
  container_code: string | null
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

type Props = {
  token: string
  /**
   * Документ, который подбираем.
   *
   * Экран живёт двумя способами: отдельным адресом со своим параметром пути и
   * встроенным во вкладку «Подбор» документа отгрузки. Во втором случае номер
   * приходит пропсом — адрес страницы при этом не меняется.
   */
  requestId?: string
  /**
   * Откуда подбираем: отгрузка на маркетплейс или поставка FBS.
   *
   * Экран один и тот же — владелец так и требовал. Обе стороны отдают места
   * одной формой и принимают запись одними и теми же двумя ручками, поэтому
   * различается только корень адреса.
   */
  source?: 'unload' | 'fbs'
  /** Скрывает только дублирующий заголовок внутри карточки документа. */
  hideHeader?: boolean
  /** Экран встроен в окно документа: там завершение подбора не уводит
   * со страницы, а переключает на упаковку. Без этого встроенный экран
   * уходил на список отгрузок и окно оставалось пустым. */
  onFinished?: () => void
  /** Действие «Отложить» во встроенном документе не должно уводить в чужой список. */
  onPaused?: () => void
}

export function FfUnloadPickPage({ token, requestId: requestIdProp, source, hideHeader = false, onFinished, onPaused }: Props) {
  const BASE = source === 'fbs' ? FBS_BASE : UNLOAD_BASE
  const params = useParams<{ requestId: string }>()
  const requestId = requestIdProp ?? params.requestId
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ApiDetail | null>(null)
  const [pickOptions, setPickOptions] = useState<ApiPickProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  // Тара, отсканированная как место снятия (§Ж-03), но пока не встретившаяся
  // среди источников pick-options — например, короб только что подъехал и в
  // pick-options ещё не попал. `screenData.placeSource` знает только про тару,
  // которая уже держит товар этой отгрузки; этот кэш — про саму тару, ключ
  // тот же `obj:<id>`, что и в `placeSource`, поэтому оба источника читаются
  // одним и тем же кодом при следующем скане товара.
  const scannedContainers = useRef<
    Map<string, { locationId: string; containerKind: ObjKind; containerId: string }>
  >(new Map())
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

    // Состав берём из того источника, который его отдаёт. У отгрузки это строки
    // документа. У поставки ФБС строк в документе нет вовсе — там товары
    // приезжают вместе с местами подбора, и обращение к `detail.lines` роняло
    // экран целиком: «Cannot read properties of undefined (reading 'map')».
    const composition: Array<{
      id: string
      productId: string
      name: string
      sku: string
      plan: number
    }> = detail.lines
      ? detail.lines.map((line) => ({
          id: line.id,
          productId: line.product_id,
          name: line.product_name,
          sku: line.sku_code,
          plan: line.quantity,
        }))
      : pickOptions.map((option) => ({
          id: option.product_id,
          productId: option.product_id,
          name: option.product_name,
          sku: option.sku_code,
          plan: option.planned_qty,
        }))

    const products: PickProduct[] = composition.map((item) => {
      const catalog = catalogById.get(item.productId)
      return {
        id: item.productId,
        name: item.name,
        sku: item.sku,
        barcode: catalog?.wb_primary_barcode ?? catalog?.wb_barcodes[0] ?? '',
        photo: catalog?.wb_primary_image_url ?? '',
        size: catalog?.wb_size ?? null,
      }
    })
    const plan: PlanLine[] = composition.map((item) => ({
      id: item.id,
      productId: item.productId,
      plan: item.plan,
    }))

    const cellsById = new Map<string, Cell>()
    const objectsById = new Map<string, WarehouseObject>()
    const stock: GoodsLine[] = []
    const picked: PickedMap = {}
    // Что стоит за каждой строкой места: ячейка и тара, из которой снимаем.
    // Сервер принимает эту пару и списывает остаток именно этой тары.
    const placeSource = new Map<
      string,
      { locationId: string; containerKind: ObjKind | null; containerId: string | null }
    >()

    for (const product of pickOptions) {
      for (const location of product.locations) {
        cellsById.set(location.storage_location_id, {
          id: location.storage_location_id,
          code: location.location_code,
          // pick-options не раскрывает отдельный ШК ячейки. Код нужен для
          // ручного ввода, а настоящий штрихкод распознаёт scan-роут сервера.
          barcode: location.location_code,
        })
        const cellHolder = cellRef(location.storage_location_id)

        // Остаток уже уменьшен предыдущими снятиями. Возвращаем picked к
        // доступному, чтобы поле могло показать и уменьшить сохранённый факт.
        const pool = location.available + location.picked

        // Старый ответ сервера без тары — место остаётся одной строкой на ячейку.
        const sources: ApiPickSource[] = location.sources?.length
          ? location.sources
          : [
              {
                quantity: pool,
                is_loose: true,
                source_label: 'Россыпью',
                container_path: [],
                picked: location.picked,
              },
            ]

        for (const source of sources) {
          // Строим цепочку тары снаружи внутрь: палета стоит в ячейке, короб —
          // на палете. У россыпи цепочка пустая, и держателем остаётся ячейка.
          let holder = cellHolder
          for (const step of source.container_path) {
            if (!objectsById.has(step.id)) {
              objectsById.set(step.id, {
                id: step.id,
                kind: step.kind,
                code: step.code,
                // Отдельного ШК тары ручка не отдаёт; распознаёт его scan-роут.
                barcode: step.code,
                holder,
              })
            }
            holder = objRef(step.id)
          }

          // Снятое приходит по каждому источнику отдельно, а «сколько можно
          // снять» — это то, что лежит здесь, плюс уже снятое отсюда же.
          const takenHere = source.picked ?? 0
          const capacity = source.quantity + takenHere
          if (capacity <= 0) continue

          stock.push({
            id: `${product.product_id}-${holder}`,
            productId: product.product_id,
            qty: capacity,
            holder,
          })
          picked[pickKey(product.product_id, holder)] = takenHere
          const innermost = source.container_path.at(-1) ?? null
          placeSource.set(holder, {
            locationId: location.storage_location_id,
            containerKind: innermost ? innermost.kind : null,
            containerId: innermost ? innermost.id : null,
          })
        }
      }
    }

    const number = detail.display_number ?? detail.document_number ?? detail.name ?? detail.wb_supply_id ?? detail.id
    const date = formatDate(detail.planned_shipment_date)
    const warehouse = detail.warehouse_name ? ` · ${detail.warehouse_name}` : ''
    return {
      document: `${source === 'fbs' ? 'Поставка' : 'Отгрузка'} ${number}${date ? ` от ${date}` : ''}${warehouse}`,
      seller: detail.seller_name ?? '—',
      products,
      plan,
      stock,
      objects: [...objectsById.values()],
      cells: [...cellsById.values()],
      picked,
      placeSource,
    }
  }, [catalogById, detail, pickOptions, source])

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
      const source = screenData?.placeSource.get(payload.place.key)
      const locationId = source?.locationId ?? sourceLocationId(payload.place.key)
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
            // Тара, из которой снимаем. Пусто — снимаем россыпью с ячейки.
            container_kind: source?.containerKind ?? null,
            container_id: source?.containerId ?? null,
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
    [load, requestId, screenData, token, updateOption],
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
      // Тара — источник, из которого спишется товар (§Ж-03): сначала ищем её
      // среди уже известных pick-options источников, затем среди того, что
      // оператор только что отсканировал сам (см. scannedContainers выше).
      // Если выбрана просто ячейка, а не тара, containerSource останется
      // пустым — сработает старая адресация по locationId.
      const containerSource = sourceKey
        ? (screenData?.placeSource.get(sourceKey) ?? scannedContainers.current.get(sourceKey))
        : null
      let locationId = containerSource?.locationId ?? sourceLocationId(sourceKey)
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
            // Тара, из которой снимаем. Пусто — сервер сам решает по ячейке.
            container_kind: containerSource?.containerKind ?? null,
            container_id: containerSource?.containerId ?? null,
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
        if (result.kind === 'container') {
          if (!result.storage_location_id || !result.container_kind || !result.container_id) {
            throw new Error('Сервер распознал тару, но не вернул её адрес')
          }
          // Запоминаем тару здесь же: следующий скан товара найдёт её по
          // тому же ключу `obj:<id>`, даже если в pick-options источников
          // с этой тарой ещё нет.
          scannedContainers.current.set(objRef(result.container_id), {
            locationId: result.storage_location_id,
            containerKind: result.container_kind,
            containerId: result.container_id,
          })
          return {
            kind: 'container',
            storageLocationId: result.storage_location_id,
            locationCode: result.location_code,
            containerKind: result.container_kind,
            containerId: result.container_id,
            containerCode: result.container_code,
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
    [
      catalogById,
      pickOptions,
      requestId,
      screenData?.placeSource,
      screenData?.products,
      token,
      updateOption,
    ],
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
        hideHeader={hideHeader}
        document={screenData.document}
        seller={screenData.seller}
        products={screenData.products}
        plan={screenData.plan}
        stock={screenData.stock}
        objects={screenData.objects}
        cells={screenData.cells}
        initialPicked={screenData.picked}
        busy={busy}
        onSetPicked={setPicked}
        onScan={scan}
        onPause={() => {
          if (onPaused) {
            onPaused()
            return
          }
          navigate('/app/ff/mp-shipments')
        }}
        onComplete={() => {
          if (onFinished) {
            onFinished()
            return
          }
          navigate(`/app/ff/mp-shipments?open_mp=${encodeURIComponent(requestId ?? '')}`)
        }}
      />
    </Box>
  )
}
