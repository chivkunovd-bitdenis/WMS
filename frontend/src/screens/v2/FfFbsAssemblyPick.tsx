import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../api'
import { fetchMarketplaceProductCatalogRows } from '../../hooks/useWbProductCatalog'
import type { MarketplaceProductCatalogRow } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { EmptyState, ErrorNotice } from '../../ui-kit'
import { resolveProductScanSource, scanSourceKey } from '../ff/unload-pick/pickScanSource'
import { UnloadPickScreen, type UnloadPickScanResult } from '../ff/unload-pick/UnloadPickScreen'
import {
  cellRef,
  objRef,
  type Cell,
  type GoodsLine,
  type ObjKind,
  type PickProduct,
  type PlanLine,
  type WarehouseObject,
} from '../ff/unload-pick/pickStub'
import { pickKey, placesOf, type PickedMap } from '../ff/unload-pick/pickRows'
import {
  pickScanTargets,
  planGroupPickSet,
  type GroupPickLogEntry,
  type GroupPickSupplyState,
} from './fbsSupplyAssembly'

// WMS-574 R8–R10: «Подбор» окна сборки — тот же экран подбора
// (UnloadPickScreen), что во вкладке «Подбор» карточки поставки, только план
// в нём — сумма планов всех поставок группы. Экран про сервер не знает; этот
// контейнер делает то же, что FfUnloadPickPage для одной поставки, и решает,
// какой поставке уходит каждое снятие (Д5). Запросы — прежние pick/scan и
// pick/set конкретной поставки. FfUnloadPickPage и карточка не меняются.

const FBS_BASE = '/operations/fbs-supplies'

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

type ApiContainerStep = { kind: ObjKind; id: string; code: string; label: string }

type ApiPickSource = {
  quantity: number
  available?: number
  is_loose: boolean
  source_label: string
  container_path: ApiContainerStep[]
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
  sku_code: string | null
  product_name: string
  seller_article: string | null
  barcode: string | null
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

type PlaceSource = { locationId: string; containerKind: ObjKind | null; containerId: string | null }

/** Что знает контейнер об одной поставке группы: план и подборы по местам. */
type SupplyPickState = {
  planned: Map<string, number>
  pickedTotal: Map<string, number>
  /** Ключ — pickKey(товар, место). */
  pickedHere: Map<string, number>
}

function sourceLocationId(sourceKey: string | null): string | null {
  return sourceKey?.startsWith('cell:') ? sourceKey.slice(5) : null
}

/** Место источника — тот же ключ, что строит FfUnloadPickPage: ячейка, затем тара снаружи внутрь. */
function sourceHolder(locationId: string, source: ApiPickSource): string {
  let holder = cellRef(locationId)
  for (const step of source.container_path) holder = objRef(step.id)
  return holder
}

function locationSources(location: ApiPickLocation): ApiPickSource[] {
  return location.sources?.length
    ? location.sources
    : [{
        quantity: location.quantity,
        available: location.available,
        is_loose: true,
        source_label: 'Россыпью',
        container_path: [],
        picked: location.picked,
      }]
}

function supplyPickState(options: ApiPickProduct[]): SupplyPickState {
  const state: SupplyPickState = { planned: new Map(), pickedTotal: new Map(), pickedHere: new Map() }
  for (const product of options) {
    state.planned.set(product.product_id, product.planned_qty)
    state.pickedTotal.set(product.product_id, product.picked_qty)
    for (const location of product.locations) {
      for (const source of locationSources(location)) {
        const key = pickKey(product.product_id, sourceHolder(location.storage_location_id, source))
        state.pickedHere.set(key, (state.pickedHere.get(key) ?? 0) + (source.picked ?? 0))
      }
    }
  }
  return state
}

type Props = {
  token: string
  /** Поставки группы в порядке раздачи (Д5) и их селлеры — для каталога товаров. */
  supplies: Array<{ id: string; sellerId: string }>
}

export function FfFbsAssemblyPick({ token, supplies }: Props) {
  const supplyIds = useMemo(() => supplies.map((one) => one.id), [supplies])
  const idsKey = supplyIds.join(',')
  const sellerKey = [...new Set(supplies.map((one) => one.sellerId))].join(',')
  const [options, setOptions] = useState<Array<ApiPickProduct[] | null>>(() => supplyIds.map(() => null))
  const [catalogById, setCatalogById] = useState<Map<string, MarketplaceProductCatalogRow>>(() => new Map())
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const statesRef = useRef<SupplyPickState[]>([])
  // Номер изменения по поставке: фоновое перечитывание мест не затирает
  // снятие, сделанное после его старта.
  const mutationRef = useRef<number[]>([])
  const logsRef = useRef(new Map<string, GroupPickLogEntry[]>())
  const scannedContainers = useRef(new Map<string, PlaceSource>())
  // Снятия группы идут строго по одному: раздача считается по числам,
  // которые предыдущее снятие уже поменяло.
  const chainRef = useRef<Promise<unknown>>(Promise.resolve())
  // Последнее начатое перечитывание мест по поставке (WMS-575, Д5): его ждёт
  // только следующий скан товара без выбранного места.
  const refreshingRef = useRef(new Map<number, Promise<ApiPickProduct[] | null>>())

  const enqueue = useCallback(<T,>(task: () => Promise<T>): Promise<T> => {
    const run = chainRef.current.then(task, task)
    chainRef.current = run.catch(() => undefined)
    return run
  }, [])

  const fetchOptions = useCallback(async (supplyId: string): Promise<ApiPickProduct[]> => {
    const res = await fetch(apiUrl(`${FBS_BASE}/${supplyId}/pick-options`), { headers: headers(token) })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    return (await res.json()) as ApiPickProduct[]
  }, [token])

  const load = useCallback(async () => {
    const ids = idsKey ? idsKey.split(',') : []
    setLoading(true)
    setError(null)
    try {
      const next = await Promise.all(ids.map((id) => fetchOptions(id)))
      statesRef.current = next.map(supplyPickState)
      mutationRef.current = ids.map((_, index) => (mutationRef.current[index] ?? 0) + 1)
      logsRef.current = new Map()
      setOptions(next)
      setVersion((current) => current + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть подбор')
    } finally {
      setLoading(false)
    }
  }, [fetchOptions, idsKey])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const sellerIds = sellerKey ? sellerKey.split(',') : []
    if (!token || sellerIds.length === 0) return
    let active = true
    setCatalogError(null)
    void Promise.all(sellerIds.map((sellerId) => fetchMarketplaceProductCatalogRows(headers(token), sellerId)))
      .then((lists) => {
        if (!active) return
        setCatalogById(new Map(lists.flat().map((row) => [row.id, row])))
      })
      .catch((cause: unknown) => {
        if (!active) return
        setCatalogError(cause instanceof Error ? cause.message : 'Не удалось загрузить каталог товаров.')
      })
    return () => {
      active = false
    }
  }, [token, sellerKey])

  const refreshSupply = useCallback((index: number): Promise<ApiPickProduct[] | null> => {
    const supplyId = supplyIds[index]
    if (!supplyId) return Promise.resolve(null)
    const startedAt = mutationRef.current[index] ?? 0
    const refresh = (async () => {
      try {
        const next = await fetchOptions(supplyId)
        if ((mutationRef.current[index] ?? 0) === startedAt) {
          statesRef.current[index] = supplyPickState(next)
          setOptions((current) => current.map((one, position) => (position === index ? next : one)))
        }
        return next
      } catch {
        setError('Снятие сохранено, список не обновлён. Обновите страницу.')
        return null
      }
    })()
    refreshingRef.current.set(index, refresh)
    void refresh.then(() => {
      if (refreshingRef.current.get(index) === refresh) refreshingRef.current.delete(index)
    })
    return refresh
  }, [fetchOptions, supplyIds])

  const screenData = useMemo(() => {
    const loaded = options.filter((one): one is ApiPickProduct[] => Boolean(one))
    if (loaded.length !== supplyIds.length || loaded.length === 0) return null

    const productOrder: string[] = []
    const productInfo = new Map<string, ApiPickProduct>()
    const planByProduct = new Map<string, number>()
    const cellsById = new Map<string, Cell>()
    const objectsById = new Map<string, WarehouseObject>()
    const stockByKey = new Map<string, GoodsLine & { pickCapacity: number }>()
    const picked: PickedMap = {}
    const placeSource = new Map<string, PlaceSource>()

    for (const supplyOptions of loaded) {
      for (const product of supplyOptions) {
        if (!productInfo.has(product.product_id)) {
          productInfo.set(product.product_id, product)
          productOrder.push(product.product_id)
        }
        planByProduct.set(product.product_id, (planByProduct.get(product.product_id) ?? 0) + product.planned_qty)
        for (const location of product.locations) {
          cellsById.set(location.storage_location_id, {
            id: location.storage_location_id,
            code: location.location_code,
            barcode: location.location_code,
          })
          for (const source of locationSources(location)) {
            let holder = cellRef(location.storage_location_id)
            for (const step of source.container_path) {
              if (!objectsById.has(step.id)) {
                objectsById.set(step.id, { id: step.id, kind: step.kind, code: step.code, barcode: step.code, holder })
              }
              holder = objRef(step.id)
            }
            const takenHere = source.picked ?? 0
            const key = pickKey(product.product_id, holder)
            const existing = stockByKey.get(key)
            if (existing) {
              // Физический остаток и «доступно» у места одни на всю организацию:
              // берём их один раз, а снятое каждой поставкой складываем (R8).
              existing.pickCapacity += takenHere
              picked[key] = (picked[key] ?? 0) + takenHere
              continue
            }
            if (source.quantity <= 0 && takenHere <= 0) continue
            stockByKey.set(key, {
              id: `${product.product_id}-${holder}`,
              productId: product.product_id,
              qty: source.quantity,
              pickCapacity: (source.available ?? source.quantity) + takenHere,
              holder,
            })
            picked[key] = takenHere
            const innermost = source.container_path.at(-1) ?? null
            placeSource.set(holder, {
              locationId: location.storage_location_id,
              containerKind: innermost ? innermost.kind : null,
              containerId: innermost ? innermost.id : null,
            })
          }
        }
      }
    }

    const products: PickProduct[] = productOrder.map((productId) => {
      const item = productInfo.get(productId)!
      const catalog = catalogById.get(productId)
      return {
        id: productId,
        name: item.product_name,
        sku: item.sku_code ?? '',
        sellerArticle: catalog?.wb_vendor_code ?? '',
        barcode: catalog?.wb_primary_barcode ?? catalog?.wb_barcodes[0] ?? '',
        photo: catalog?.wb_primary_image_url ?? '',
        size: catalog?.wb_size ?? null,
      }
    })
    const plan: PlanLine[] = productOrder.map((productId) => ({
      id: productId,
      productId,
      plan: planByProduct.get(productId) ?? 0,
    }))
    return {
      products,
      plan,
      stock: [...stockByKey.values()],
      objects: [...objectsById.values()],
      cells: [...cellsById.values()],
      picked,
      placeSource,
    }
  }, [catalogById, options, supplyIds.length])

  const statesFor = useCallback((productId: string, placeKey: string | null): GroupPickSupplyState[] => {
    const result: GroupPickSupplyState[] = []
    statesRef.current.forEach((state, index) => {
      if (!state.planned.has(productId)) return
      result.push({
        index,
        planned: state.planned.get(productId) ?? 0,
        pickedTotal: state.pickedTotal.get(productId) ?? 0,
        pickedHere: placeKey ? state.pickedHere.get(pickKey(productId, placeKey)) ?? 0 : 0,
      })
    })
    return result
  }, [])

  /** Новое число поставки в месте — из ответа сервера; итог по товару сдвигается на разницу. */
  const applyPicked = useCallback((index: number, productId: string, placeKey: string, quantity: number) => {
    const state = statesRef.current[index]
    if (!state) return 0
    const key = pickKey(productId, placeKey)
    const previous = state.pickedHere.get(key) ?? 0
    state.pickedHere.set(key, quantity)
    state.pickedTotal.set(productId, Math.max(0, (state.pickedTotal.get(productId) ?? 0) + quantity - previous))
    mutationRef.current[index] = (mutationRef.current[index] ?? 0) + 1
    return quantity - previous
  }, [])

  const groupPickedAt = useCallback((productId: string, placeKey: string) => (
    statesRef.current.reduce((sum, state) => sum + (state.pickedHere.get(pickKey(productId, placeKey)) ?? 0), 0)
  ), [])

  const setPicked = useCallback(
    (payload: { productId: string; place: { key: string }; quantity: number }) => enqueue(async () => {
      const source = screenData?.placeSource.get(payload.place.key)
      const locationId = source?.locationId ?? sourceLocationId(payload.place.key)
      if (!locationId) {
        setError('Сервер не вернул ячейку, из которой снимается товар')
        await load()
        return
      }
      const logKey = pickKey(payload.productId, payload.place.key)
      const plan = planGroupPickSet(
        statesFor(payload.productId, payload.place.key),
        payload.quantity,
        logsRef.current.get(logKey) ?? [],
      )
      setBusy(true)
      setError(null)
      try {
        for (const change of plan.changes) {
          const res = await fetch(apiUrl(`${FBS_BASE}/${supplyIds[change.index]}/pick/set`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...headers(token) },
            body: JSON.stringify({
              product_id: payload.productId,
              storage_location_id: locationId,
              quantity: change.quantity,
              container_kind: source?.containerKind ?? null,
              container_id: source?.containerId ?? null,
            }),
          })
          if (!res.ok) throw new Error(await readApiErrorMessage(res))
          const out = (await res.json()) as { quantity: number }
          applyPicked(change.index, payload.productId, payload.place.key, out.quantity)
        }
        logsRef.current.set(logKey, plan.log)
        await Promise.all(plan.changes.map((change) => refreshSupply(change.index)))
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Не удалось сохранить снятое количество'
        setError(message)
        await load()
        setError(message)
      } finally {
        setBusy(false)
      }
    }),
    [applyPicked, enqueue, load, refreshSupply, screenData, statesFor, supplyIds, token],
  )

  const scan = useCallback(
    ({ barcode, sourceKey }: { barcode: string; sourceKey: string | null }) => enqueue(async (): Promise<UnloadPickScanResult> => {
      if (!screenData) throw new Error('Подбор ещё загружается')
      const normalized = barcode.trim().toLowerCase()
      const matchedProduct = screenData.products.find((product) => {
        const catalog = catalogById.get(product.id)
        return (
          product.sku.toLowerCase() === normalized ||
          product.barcode === barcode ||
          catalog?.wb_barcodes.some((one) => one === barcode)
        )
      })
      let containerSource: PlaceSource | null | undefined = sourceKey
        ? (screenData.placeSource.get(sourceKey) ?? scannedContainers.current.get(sourceKey))
        : null
      let locationId = containerSource?.locationId ?? sourceLocationId(sourceKey)
      // Д5: товар уходит первой по порядку поставке, которой он ещё нужен.
      // Незнакомый экрану код (ячейка, тара, другой ШК) сервер распознаёт сам —
      // спрашиваем поставки по порядку, пока одна из них его не примет.
      let targets = supplyIds.map((_, index) => index)
      if (matchedProduct) {
        const productTargets = pickScanTargets(statesFor(matchedProduct.id, null))
        if (productTargets.length > 0) targets = productTargets
        // Место не выбрано — источник ищется по доступному остатку; сразу после
        // прошлого снятия берём свежий ответ мест, как экран одной поставки.
        let supplyOptions = options[targets[0]] ?? []
        const refreshing = refreshingRef.current.get(targets[0])
        if (!containerSource && !locationId && refreshing) supplyOptions = (await refreshing) ?? supplyOptions
        const option = supplyOptions.find((one) => one.product_id === matchedProduct.id)
        containerSource = resolveProductScanSource(
          matchedProduct,
          option?.locations ?? [],
          containerSource ?? (locationId ? { locationId, containerKind: null, containerId: null } : null),
        )
        locationId = containerSource.locationId
      }

      setBusy(true)
      setError(null)
      try {
        let firstRejection: Error | null = null
        for (const index of targets) {
          const res = await fetch(apiUrl(`${FBS_BASE}/${supplyIds[index]}/pick/scan`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...headers(token) },
            body: JSON.stringify({
              barcode,
              ...(matchedProduct ? { product_id: matchedProduct.id } : {}),
              storage_location_id: locationId,
              container_kind: containerSource?.containerKind ?? null,
              container_id: containerSource?.containerId ?? null,
            }),
          })
          if (!res.ok) {
            const rejection = new Error(await readApiErrorMessage(res))
            // Отказ сервера (4xx) ничего не записал — можно спросить следующую
            // поставку. Исход ответа 5xx неизвестен: второй раз не снимаем.
            if (res.status >= 500) throw rejection
            firstRejection ??= rejection
            continue
          }
          const result = (await res.json()) as ApiScanResult
          if (result.kind === 'location') {
            if (!result.storage_location_id || !result.location_code) {
              throw new Error('Сервер распознал ячейку, но не вернул её адрес')
            }
            return {
              kind: 'location',
              storageLocationId: result.storage_location_id,
              locationCode: result.location_code,
            }
          }
          if (result.kind === 'container') {
            if (!result.storage_location_id || !result.container_kind || !result.container_id) {
              throw new Error('Сервер распознал тару, но не вернул её адрес')
            }
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
            }
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
          const productId = result.product_id
          const placeKey = containerSource
            ? scanSourceKey(containerSource)
            : result.storage_location_id
              ? cellRef(result.storage_location_id)
              : placesOf(productId, screenData.stock, screenData.objects, screenData.cells, screenData.picked)[0]?.key ?? null
          if (placeKey) {
            const added = applyPicked(index, productId, placeKey, result.allocation_quantity)
            if (added > 0) {
              const logKey = pickKey(productId, placeKey)
              logsRef.current.set(logKey, [...(logsRef.current.get(logKey) ?? []), { index, qty: added }])
            }
          }
          // Счётчик меняется по ответу pick/scan; места перечитываются следом.
          void refreshSupply(index)
          return {
            kind: 'product',
            sourceKey: placeKey,
            storageLocationId: result.storage_location_id,
            productId,
            sku: result.sku_code,
            productName: result.product_name,
            pickedQty: statesRef.current.reduce((sum, state) => sum + (state.pickedTotal.get(productId) ?? 0), 0),
            allocationQuantity: placeKey ? groupPickedAt(productId, placeKey) : result.allocation_quantity,
          }
        }
        throw firstRejection ?? new Error('Не удалось выполнить скан')
      } finally {
        setBusy(false)
      }
    }),
    [applyPicked, catalogById, enqueue, groupPickedAt, options, refreshSupply, screenData, statesFor, supplyIds, token],
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
        key={`${idsKey}-${version}`}
        onNote={() => undefined}
        hideHeader
        hideFooterActions
        products={screenData.products}
        plan={screenData.plan}
        stock={screenData.stock}
        objects={screenData.objects}
        cells={screenData.cells}
        initialPicked={screenData.picked}
        busy={busy}
        onSetPicked={setPicked}
        onScan={scan}
      />
    </Box>
  )
}
