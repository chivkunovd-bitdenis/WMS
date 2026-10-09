import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { useNavigate, useParams } from 'react-router-dom'
import { apiUrl } from '../../../api'
import { useMarketplaceProductCatalog } from '../../../hooks/useWbProductCatalog'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { randomId } from '../../../utils/randomId'
import { EmptyState, ErrorNotice } from '../../../ui-kit'
import { isInboundMarkingScan } from '../inboundMarkingCodes'
import { resolveProductScanSource, scanSourceKey } from './pickScanSource'
import { UnloadPickScreen, type PickSaveResult, type UnloadPickScanResult } from './UnloadPickScreen'
import {
  isUnknownBarcodeResponse,
  printFboKizLabel,
  readFboBoxRefusal,
  readFboKizError,
  type FboKizCode,
  type FboKizScanResponse,
} from './fboKizData'
import { loadFboContainers, saveFboContainers } from './fboPickState'
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
import { trackPickSave, waitForPickSaves } from './pickSaveLifecycle'

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
  /** WMS-686: у товара включён Честный знак — число КИЗ видно и при нуле. */
  requires_honest_sign?: boolean
}

type ApiDetail = {
  id: string
  marketplace?: 'wb' | 'ozon'
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

/** Физический остаток и доступное количество по конкретной ячейке или таре. */
type ApiPickSource = {
  quantity: number
  available?: number
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
  /**
   * Отгрузка FBO (WMS-686): подбор или КИЗ изменились на сервере — документу вокруг
   * экрана пора обновить свои данные (сводку, вкладку «Упаковка»). Для FBS не вызывается.
   */
  onChanged?: () => void
}

export function FfUnloadPickPage({ token, requestId: requestIdProp, source, hideHeader = false, onFinished, onPaused, onChanged }: Props) {
  const BASE = source === 'fbs' ? FBS_BASE : UNLOAD_BASE
  // Подбор отгрузки FBO — всё, что не поставка FBS (WMS-686): вид «По ячейкам / По товарам»,
  // КИЗ, двойной скан короба. Поставка FBS остаётся такой, как была.
  const isFbo = source !== 'fbs'
  const params = useParams<{ requestId: string }>()
  const requestId = requestIdProp ?? params.requestId
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ApiDetail | null>(null)
  const [pickOptions, setPickOptions] = useState<ApiPickProduct[]>([])
  const [pickOptionsReady, setPickOptionsReady] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const [kizCodes, setKizCodes] = useState<FboKizCode[]>([])
  // Открыт ли экран сейчас: отказ сохранения на закрытом экране переносится на следующее открытие.
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const onChangedRef = useRef(onChanged)
  useEffect(() => {
    onChangedRef.current = onChanged
  })
  const notifyChanged = useCallback(() => {
    if (isFbo) onChangedRef.current?.()
  }, [isFbo])
  // ШК товара, отсканированный последним: следующий КИЗ относится к этой штуке (WMS-686, D1.4).
  const lastProductScan = useRef<string | null>(null)
  // Ключи печати: пока перепечатка кода не завершилась, повтор идёт с тем же ключом — WMS Print
  // не напечатает вторую копию, если первая уже принята, а ответ потерялся.
  const reprintKeys = useRef<Map<string, string>>(new Map())
  // Async reads belong to the document and authorization context that started them.
  const requestContext = useMemo(() => ({ BASE, requestId, token }), [BASE, requestId, token])
  const activeContext = useRef(requestContext)
  activeContext.current = requestContext
  const loadSeq = useRef(0)
  const isOzonFbs = source === 'fbs' && detail?.marketplace === 'ozon'
  // Тара, отсканированная как место снятия (§Ж-03), но пока не встретившаяся
  // среди источников pick-options — например, короб только что подъехал и в
  // pick-options ещё не попал. `screenData.placeSource` знает только про тару,
  // которая уже держит товар этой отгрузки; этот кэш — про саму тару, ключ
  // тот же `obj:<id>`, что и в `placeSource`, поэтому оба источника читаются
  // одним и тем же кодом при следующем скане товара.
  const scannedContainers = useRef<
    Map<string, { locationId: string; containerKind: ObjKind; containerId: string }>
  >(new Map())
  // FBO: тара, выбранная сканом, переживает перемонтирование экрана (смену вкладок документа).
  useEffect(() => {
    if (!isFbo || !requestId) return
    for (const [key, value] of loadFboContainers(requestId)) {
      if (!scannedContainers.current.has(key)) scannedContainers.current.set(key, value)
    }
  }, [isFbo, requestId])
  const {
    catalogById,
    error: catalogError,
  } = useMarketplaceProductCatalog(
    token,
    !isOzonFbs && Boolean(detail?.seller_id),
    detail?.seller_id,
  )

  const load = useCallback(async (waitForSave = true) => {
    if (activeContext.current !== requestContext || !mounted.current) return
    const seq = ++loadSeq.current
    const isCurrent = () => activeContext.current === requestContext && loadSeq.current === seq && mounted.current
    if (!requestId) {
      setError('Не указан номер отгрузки')
      setLoading(false)
      return
    }
    setLoading(true)
    setPickOptionsReady(false)
    setError(null)
    try {
      if (waitForSave) await waitForPickSaves([`${BASE}/${requestId}`])
      if (!isCurrent()) return
      const [detailRes, optionsRes] = await Promise.all([
        fetch(apiUrl(`${BASE}/${requestId}`), { headers: headers(token) }),
        fetch(apiUrl(`${BASE}/${requestId}/pick-options`), { headers: headers(token) }),
      ])
      if (!detailRes.ok) throw new Error(await readApiErrorMessage(detailRes))
      if (!optionsRes.ok) throw new Error(await readApiErrorMessage(optionsRes))
      const [nextDetail, nextOptions] = await Promise.all([
        detailRes.json() as Promise<ApiDetail>, optionsRes.json() as Promise<ApiPickProduct[]>,
      ])
      if (!isCurrent()) return
      setDetail(nextDetail)
      setPickOptions(nextOptions)
      setPickOptionsReady(true)
      setVersion((current) => current + 1)
    } catch (err) {
      if (isCurrent()) setError(err instanceof Error ? err.message : 'Не удалось открыть подбор')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [BASE, requestContext, requestId, token])

  useEffect(() => {
    void load()
    return () => { loadSeq.current += 1 }
  }, [load])

  // WMS-686: КИЗ отгрузки. Последний начатый запрос побеждает — иначе опоздавший
  // ответ вернул бы на экран код, который уже отвязали.
  const kizSeq = useRef(0)
  const refreshKiz = useCallback(async () => {
    if (!isFbo || !requestId || activeContext.current !== requestContext) return
    kizSeq.current += 1
    const seq = kizSeq.current
    try {
      const res = await fetch(apiUrl(`${BASE}/${requestId}/marking-codes`), { headers: headers(token) })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const body = (await res.json()) as { items?: FboKizCode[] }
      if (seq === kizSeq.current && activeContext.current === requestContext && mounted.current) setKizCodes(body.items ?? [])
    } catch (err) {
      if (seq === kizSeq.current && activeContext.current === requestContext && mounted.current) {
        setError(err instanceof Error ? err.message : 'Не удалось получить КИЗ отгрузки')
      }
    }
  }, [BASE, isFbo, requestContext, requestId, token])

  useEffect(() => {
    void refreshKiz()
  }, [refreshKiz])

  const screenData = useMemo(() => {
    if (!detail || detail.id !== requestId) return null

    // Состав берём из того источника, который его отдаёт. У отгрузки это строки
    // документа. У поставки ФБС строк в документе нет вовсе — там товары
    // приезжают вместе с местами подбора, и обращение к `detail.lines` роняло
    // экран целиком: «Cannot read properties of undefined (reading 'map')».
    const composition: Array<{
      id: string
      productId: string
      name: string
      sku: string | null
      sellerArticle: string | null
      barcode: string | null
      plan: number
    }> = detail.lines
      ? detail.lines.map((line) => ({
          id: line.id,
          productId: line.product_id,
          name: line.product_name,
          sku: line.sku_code,
          sellerArticle: null,
          barcode: null,
          plan: line.quantity,
        }))
      : pickOptions.map((option) => ({
          id: option.product_id,
          productId: option.product_id,
          name: option.product_name,
          sku: option.sku_code,
          sellerArticle: option.seller_article,
          barcode: option.barcode,
          plan: option.planned_qty,
        }))

    const products: PickProduct[] = composition.map((item) => {
      const catalog = isOzonFbs ? undefined : catalogById.get(item.productId)
      return {
        id: item.productId,
        name: item.name,
        sku: item.sku ?? '',
        sellerArticle: isOzonFbs ? item.sellerArticle ?? '' : catalog?.wb_vendor_code ?? '',
        barcode: isOzonFbs ? item.barcode ?? '' : catalog?.wb_primary_barcode ?? catalog?.wb_barcodes[0] ?? '',
        photo: isOzonFbs ? '' : catalog?.wb_primary_image_url ?? '',
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
    const stock: (GoodsLine & { pickCapacity?: number })[] = []
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

        // Старый ответ сервера без тары — место остаётся одной строкой на ячейку.
        const sources: ApiPickSource[] = location.sources?.length
          ? location.sources
          : [
              {
                quantity: location.quantity,
                available: location.available,
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

          // «Лежит» показывает физический остаток. Потолок ввода включает
          // доступное и уже снятое, чтобы сохранённое количество можно было уменьшить.
          const takenHere = source.picked ?? 0
          const capacity = (source.available ?? source.quantity) + takenHere
          if (source.quantity <= 0 && takenHere <= 0) continue

          stock.push({
            id: `${product.product_id}-${holder}`,
            productId: product.product_id,
            qty: source.quantity,
            pickCapacity: capacity,
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
  }, [catalogById, detail, isOzonFbs, pickOptions, source, requestId])

  // Товары, у которых включён Честный знак: число КИЗ видно и при нуле (WMS-686, R3).
  const markingProducts = useMemo(
    () => new Set((detail?.lines ?? []).filter((line) => line.requires_honest_sign).map((line) => line.product_id)),
    [detail],
  )
  // Detail line picked_qty describes shipment boxes; pick-options contains actual picking.
  const printPickedByProduct = useMemo(
    () => new Map(pickOptions.map((product) => [product.product_id, product.picked_qty])),
    [pickOptions],
  )

  // WMS-575: места подбора перечитываются после снятия, но скан их не ждёт —
  // счётчик меняется по ответу pick/scan. Здесь живёт последнее начатое
  // перечитывание: его ждёт только следующий скан товара без выбранного места,
  // которому нужно знать, где товар ещё доступен.
  const optionsRefresh = useRef<Promise<ApiPickProduct[] | null> | null>(null)
  const optionsRefreshSeq = useRef(0)

  const updateOption = useCallback((): Promise<ApiPickProduct[] | null> => {
    if (!requestId || activeContext.current !== requestContext || !mounted.current) return Promise.resolve(null)
    optionsRefreshSeq.current += 1
    const seq = optionsRefreshSeq.current
    const isCurrent = () => seq === optionsRefreshSeq.current && activeContext.current === requestContext && mounted.current
    setPickOptionsReady(false)
    const refresh = (async () => {
      try {
        const res = await fetch(apiUrl(`${BASE}/${requestId}/pick-options`), {
          headers: headers(token),
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
        const next = (await res.json()) as ApiPickProduct[]
        // Перечитывания могут вернуться не по порядку: на экран ложится только
        // последнее начатое, иначе старый ответ вернул бы уже снятое.
        if (isCurrent()) {
          setPickOptions(next)
          setPickOptionsReady(true)
        }
        return next
      } catch {
        if (isCurrent()) {
          setPickOptionsReady(false)
          setError('Снятие сохранено, список не обновлён. Обновите страницу.')
        }
        return null
      }
    })()
    optionsRefresh.current = refresh
    void refresh.then(() => {
      if (optionsRefresh.current === refresh) optionsRefresh.current = null
    })
    return refresh
  }, [BASE, requestContext, requestId, token])

  const confirmedPicked = useRef<PickedMap>({})
  useEffect(() => {
    if (screenData) confirmedPicked.current = screenData.picked
  }, [screenData])
  const saveChain = useRef<Promise<unknown>>(Promise.resolve())

  const setPicked = useCallback(
    (payload: { productId: string; place: { key: string }; quantity: number }) => {
      const save = async () => {
        if (!requestId) return
        const placeSource = screenData?.placeSource.get(payload.place.key)
        const locationId = placeSource?.locationId ?? sourceLocationId(payload.place.key)
        if (!locationId) {
          setError('Сервер не вернул ячейку, из которой снимается товар')
          await load(false)
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
              ...(source === 'fbs' ? { expected_quantity: confirmedPicked.current[pickKey(payload.productId, payload.place.key)] ?? 0 } : {}),
              // Тара, из которой снимаем. Пусто — снимаем россыпью с ячейки.
              container_kind: placeSource?.containerKind ?? null,
              container_id: placeSource?.containerId ?? null,
            }),
          })
          if (!res.ok) throw new Error(await readApiErrorMessage(res))
          confirmedPicked.current[pickKey(payload.productId, payload.place.key)] = payload.quantity
          // FBO (R19): если подобрано стало меньше, чем КИЗ, сервер отвязал последние коды.
          let unlinkedKiz: string[] = []
          if (isFbo) {
            const body = (await res.json().catch(() => null)) as { unlinked_marking_codes?: unknown } | null
            if (Array.isArray(body?.unlinked_marking_codes)) {
              unlinkedKiz = body.unlinked_marking_codes.filter((one): one is string => typeof one === 'string')
            }
          }
          await updateOption()
          void refreshKiz()
          notifyChanged()
          return { unlinkedKiz } satisfies PickSaveResult
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Не удалось сохранить снятое количество'
          setError(message)
          await load(false)
          setError(message)
          throw new Error(message)
        } finally {
          setBusy(false)
        }
      }
      const run = saveChain.current.then(save, save)
      saveChain.current = run.catch(() => undefined)
      // FBO: отказ, который оператор уже увидел на открытом экране, не возвращается ошибкой
      // загрузки при следующем открытии вкладки — иначе вместо подбора стоит красная плашка.
      trackPickSave([`${BASE}/${requestId}`], run, () => !isFbo || !mounted.current)
      return run
    },
    [isFbo, load, notifyChanged, refreshKiz, requestId, screenData, source, token, updateOption],
  )

  /** WMS-686 · FBO: скан КИЗ — привязка к товару, штука не прибавляется. */
  const scanKiz = useCallback(
    async (code: string, productId: string | null): Promise<UnloadPickScanResult> => {
      setBusy(true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`${BASE}/${requestId}/marking-codes/scan`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify({
            code,
            ...(productId ? { product_id: productId } : {}),
            mutation_id: randomId(),
          }),
        })
        if (!res.ok) throw new Error(await readFboKizError(res))
        const body = (await res.json()) as FboKizScanResponse
        if (!body.already_linked) {
          // Число КИЗ меняется сразу; сверка со списком сервера идёт следом.
          setKizCodes((current) =>
            current.some((one) => one.marking_code_id === body.marking_code_id)
              ? current
              : [
                  ...current,
                  {
                    marking_code_id: body.marking_code_id,
                    cis_code: body.cis_code,
                    product_id: body.product_id,
                    line_id: body.line_id,
                    status: 'applied',
                    intake_document_number: null,
                    linked_at: null,
                    has_label_artifact: false,
                  },
                ],
          )
          notifyChanged()
        }
        void refreshKiz()
        return {
          kind: 'kiz',
          productId: body.product_id,
          cisCode: body.cis_code,
          alreadyLinked: body.already_linked,
          kizCount: body.kiz_count,
          pickedQty: body.picked_qty,
        }
      } finally {
        setBusy(false)
      }
    },
    [BASE, notifyChanged, refreshKiz, requestId, token],
  )

  const removeKiz = useCallback(
    async (code: FboKizCode) => {
      const res = await fetch(apiUrl(`${BASE}/${requestId}/marking-codes/${code.marking_code_id}`), {
        method: 'DELETE',
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await readFboKizError(res))
      setKizCodes((current) => current.filter((one) => one.marking_code_id !== code.marking_code_id))
      void refreshKiz()
      notifyChanged()
    },
    [BASE, notifyChanged, refreshKiz, requestId, token],
  )

  const reprintKiz = useCallback(
    async (code: FboKizCode) => {
      const keys = reprintKeys.current
      const key = keys.get(code.marking_code_id) ?? `fbo-kiz-reprint:${code.marking_code_id}:${randomId()}`
      keys.set(code.marking_code_id, key)
      await printFboKizLabel(code, token, key)
      // Принято — следующая перепечатка этого кода будет новой операцией.
      keys.delete(code.marking_code_id)
    },
    [token],
  )

  /**
   * WMS-686 · FBO: короб целиком в подбор (двойной скан и кнопка). Отказ — исключение с текстом
   * сервера; повтор уже перенесённого короба возвращает спокойное сообщение (R8).
   */
  const takeWholeBox = useCallback(
    async (barcode: string): Promise<string | void> => {
      if (!requestId) throw new Error('Не указан номер отгрузки')
      const res = await fetch(apiUrl(`${BASE}/${requestId}/boxes/attach`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({ barcode, allow_over_plan: false }),
      })
      if (!res.ok) {
        const refusal = await readFboBoxRefusal(res)
        if (refusal.neutral) return refusal.message
        throw new Error(refusal.message)
      }
      await updateOption()
      void refreshKiz()
      notifyChanged()
    },
    [BASE, notifyChanged, refreshKiz, requestId, token, updateOption],
  )

  const scan = useCallback(
    async ({ barcode, sourceKey }: { barcode: string; sourceKey: string | null }) => {
      if (!requestId) throw new Error('Не указан номер отгрузки')

      // FBO: код Честного знака уходит в привязку КИЗ тем же признаком, что в приёмке;
      // к товару его относит последний отсканированный ШК товара, если он был сразу перед ним.
      if (isFbo && isInboundMarkingScan(barcode)) {
        const productId = lastProductScan.current
        lastProductScan.current = null
        return scanKiz(barcode, productId)
      }

      const normalized = barcode.trim().toLowerCase()
      const matchedProduct = screenData?.products.find((product) => {
        const catalog = catalogById.get(product.id)
        return (
          product.sku.toLowerCase() === normalized ||
          product.barcode === barcode ||
          catalog?.wb_barcodes.some((one) => one === barcode)
        )
      })
      // Контекст штуки для следующего КИЗ — даже если снятие отказано (сверх плана):
      // недостающий КИЗ для уже подобранной штуки привязать всё равно можно.
      const previousProductScan = lastProductScan.current
      if (isFbo) {
        lastProductScan.current =
          matchedProduct?.id ??
          pickOptions.find((one) => one.barcode === barcode || one.sku_code?.toLowerCase() === normalized)?.product_id ??
          null
      }
      // Тара — источник, из которого спишется товар (§Ж-03): сначала ищем её
      // среди уже известных pick-options источников, затем среди того, что
      // оператор только что отсканировал сам (см. scannedContainers выше).
      // Для скана товара без выбранного места считаем физические источники
      // из ответа сервера, а не число ячеек: в одной ячейке бывает несколько коробов.
      let containerSource = sourceKey
        ? (screenData?.placeSource.get(sourceKey) ?? scannedContainers.current.get(sourceKey))
        : null
      let locationId = containerSource?.locationId ?? sourceLocationId(sourceKey)
      if (matchedProduct) {
        // Место не выбрано — источник ищется по доступному остатку. Сразу после
        // прошлого снятия этот остаток перечитывается: берём свежий ответ, а
        // не список до снятия, иначе опустевшее место сочлось бы ещё раз.
        let options = pickOptions
        const refreshing = optionsRefresh.current
        if (!containerSource && !locationId && refreshing) {
          options = (await refreshing) ?? options
        }
        const option = options.find((one) => one.product_id === matchedProduct.id)
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
        if (!res.ok) {
          // FBO (R7): не товар, не ячейка и не тара — значит, это КИЗ; отказ сервера не показываем.
          if (isFbo && !matchedProduct && (await isUnknownBarcodeResponse(res))) {
            lastProductScan.current = null
            return scanKiz(barcode, previousProductScan)
          }
          throw new Error(await readApiErrorMessage(res))
        }
        const result = (await res.json()) as ApiScanResult
        if (isFbo) lastProductScan.current = result.kind === 'product' ? result.product_id : null
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
          if (isFbo) saveFboContainers(requestId, scannedContainers.current)
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
        if (result.storage_location_id || containerSource) {
          // Счётчик и звук — по ответу pick/scan; места догоняют в фоне (WMS-575, Д5).
          void updateOption()
        }
        notifyChanged()
        return {
          kind: 'product',
          sourceKey: containerSource ? scanSourceKey(containerSource) : null,
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
      isFbo,
      notifyChanged,
      pickOptions,
      requestId,
      scanKiz,
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
        // FBO не перемонтируется при перечитывании: вид, раскрытия, источник и история
        // отмены переживают ошибку (WMS-686, D1.2). Поставка FBS — как прежде.
        key={isFbo ? requestId : `${requestId}-${version}`}
        onNote={() => undefined}
        hideHeader={hideHeader}
        hideFooterActions={source === 'fbs'}
        // WMS-637: подбор поставки FBS — по ячейкам, как в окне «Сборка».
        // У отгрузки FBO вид выбирает оператор (WMS-686), по умолчанию — по ячейкам.
        groupByCell={source === 'fbs'}
        fboMode={isFbo}
        fbo={
          isFbo && requestId
            ? {
                stateKey: requestId,
                marketplace: detail?.marketplace,
                printReady: pickOptionsReady && !loading,
                printPickedByProduct,
                kizCodes,
                markingProducts,
                onKizRemove: removeKiz,
                onKizReprint: reprintKiz,
                onTakeWholeBox: takeWholeBox,
              }
            : undefined
        }
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
