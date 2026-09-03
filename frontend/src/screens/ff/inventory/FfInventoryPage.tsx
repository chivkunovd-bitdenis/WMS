import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import { mergeInFlightActuals } from './InventoryRows'
import { createFoundQueue, type FoundPlace } from './foundQueue'
import type { WbProductPickerCatalogRow } from '../../../components/WbProductPickerDialog'

/**
 * Строка каталога для модалки «Добавить товар» — тот же WbProductPickerCatalogRow,
 * плюс seller_id: он нужен, чтобы отобрать товары одного продавца самим на
 * экране, а не просить сервер фильтровать (ff-catalog фильтрует по seller_id
 * только для админа — обычный кладовщик с правом PERM_INVENTORY получил бы 403).
 */
type ManualAddCatalogRow = WbProductPickerCatalogRow & { seller_id: string | null }

type FoundResponse = Awaited<ReturnType<typeof recordCountFound>>
import { FfInventoryListScreen } from './FfInventoryListScreen'
import { InventoryCreateDialog, type CreateFill } from './InventoryCreateDialog'
import type { CountListItem, InventoryCount } from './InventoryTypes'
import {
  INVENTORY_BASE as BASE,
  actualPayload,
  inventoryAuthHeaders as authHeaders,
  postResultNote,
  toCount,
  toListItem,
  type ApiDetail,
  type ApiSummary,
  recordCountFound,
  saveCountActuals,
  createCountContainer,
  addManualLine,
  InventoryHttpError,
} from './inventoryCountApi'

// Экран инвентаризации, подключённый к серверу.
//
// Вся работа с документом — в FfInventoryCountScreen, список — в
// FfInventoryListScreen; здесь только загрузка, сохранение и проведение.
// Разделено намеренно: те два экрана уже приняты владельцем по макету и не
// должны знать про сеть, иначе их нельзя будет открыть в превью без сервера.
//
// Разбор ответов сервера и отправка факта живут в inventoryCountApi: тем же
// путём документ заводится со строки карты склада, и расходиться им нельзя.

type Props = {
  token: string
  sellers: Array<{ id: string; name: string }>
  warehouses: Array<{ id: string; name: string }>
}

export function FfInventoryPage({ token, sellers, warehouses }: Props) {
  const [items, setItems] = useState<CountListItem[]>([])
  const [count, setCount] = useState<InventoryCount | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  // Категории для отбора приходят с сервера: ручка есть давно, экран её просто
  // не спрашивал, и выпадающий список стоял пустым.
  const [categories, setCategories] = useState<string[]>([])
  // Каталог для модалки «Добавить товар». Грузится один раз на весь арендатора
  // (весь каталог, без пагинации — как и остальные каталоги в системе), а по
  // селлеру документа фильтруется на экране при открытии модалки.
  const [productCatalog, setProductCatalog] = useState<ManualAddCatalogRow[] | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)

  const loadList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(BASE), { headers: { ...authHeaders(token) } })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setItems(((await res.json()) as ApiSummary[]).map(toListItem))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить список')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void loadList()
  }, [loadList])

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(apiUrl('/products/categories'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) return
        setCategories((await res.json()) as string[])
      } catch {
        // Без категорий отбор по складу и продавцу продолжает работать —
        // молча оставляем список пустым, а не роняем экран.
      }
    })()
  }, [token])

  useEffect(() => {
    void (async () => {
      setCatalogLoading(true)
      try {
        const res = await fetch(apiUrl('/products/ff-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) return
        setProductCatalog((await res.json()) as ManualAddCatalogRow[])
      } catch {
        // Без каталога кнопка «Добавить товар» просто откроет пустую модалку с
        // ошибкой поиска — сам экран пересчёта из-за этого падать не должен.
      } finally {
        setCatalogLoading(false)
      }
    })()
  }, [token])

  async function open(id: string) {
    setLoading(true)
    setError(null)
    setNote(null)
    try {
      const res = await fetch(apiUrl(`${BASE}/${id}`), { headers: { ...authHeaders(token) } })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setCount(toCount((await res.json()) as ApiDetail))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть документ')
    } finally {
      setLoading(false)
    }
  }

  // Строки, которые правил ИМЕННО этот оператор в этом сеансе. Отправляем на
  // сервер только их: документ один, а кладовщиков в нём может быть двое, и
  // запись всего документа целиком стирает чужую работу.
  const touchedRef = useRef<Set<string>>(new Set())
  // Очередь работает асинхронно и обязана видеть документ, каким он стал
  // к моменту отправки, а не каким был при постановке в очередь.
  const countRef = useRef<InventoryCount | null>(null)
  countRef.current = count

  function noteTouched(lineId?: string) {
    if (lineId) touchedRef.current.add(lineId)
  }

  async function save() {
    if (!count) return
    setLoading(true)
    try {
      const res = await fetch(apiUrl(`${BASE}/${count.id}/lines`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify(actualPayload(count, touchedRef.current)),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setCount(toCount((await res.json()) as ApiDetail))
      touchedRef.current = new Set()
      setNote('Сохранено. Остатки не тронуты.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить')
    } finally {
      setLoading(false)
    }
  }

  async function post() {
    if (!count) return
    setLoading(true)
    try {
      // Сначала кладём введённое, потом проводим: иначе проведём то, что сервер
      // помнит с прошлого сохранения, а не то, что человек видит на экране.
      const saved = await fetch(apiUrl(`${BASE}/${count.id}/lines`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify(actualPayload(count, touchedRef.current)),
      })
      if (!saved.ok) throw new Error(await readApiErrorMessage(saved))
      const res = await fetch(apiUrl(`${BASE}/${count.id}/post`), {
        method: 'POST',
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const result = (await res.json()) as {
        posted_lines: number
        changed_balance_count: number
      }
      setNote(postResultNote(result))
      await open(count.id)
      await loadList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось провести')
    } finally {
      setLoading(false)
    }
  }

  async function cancelDocument() {
    if (!count) return
    try {
      const res = await fetch(apiUrl(`${BASE}/${count.id}`), {
        method: 'DELETE',
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setCount(null)
      await loadList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отменить документ')
    }
  }

  // Недоставленные сканы находок. Пока их больше нуля, документ проводить
  // нельзя: проведение зафиксировало бы остаток без того, что оператор уже
  // отсканировал, а вернуться в проведённый документ уже не получится.
  const [pendingFound, setPendingFound] = useState(0)

  /**
   * Очередь находок: строго по одной и с повтором того же скана при обрыве.
   *
   * Раньше каждый скан улетал независимо. Ответы возвращались вперемешку, и
   * поздний ответ со старым состоянием документа стирал с экрана строку,
   * которую добавил ранний, — оператор видел, что находки нет, и сканировал её
   * заново, получая двойной остаток. А при обрыве связи экран показывал ошибку
   * и выбрасывал запрос: человек пикал ещё раз, это был уже другой скан, и
   * серверная защита от повтора его не узнавала. Теперь повторяем мы сами и тем
   * же идентификатором.
   */
  // Снимок документа на момент отправки скана. Без него слияние сравнивало
  // текущее состояние с самим собой, ничего не находило и молча затирало
  // количества, введённые кладовщиком, пока летел запрос.
  const sentSnapshotRef = useRef<InventoryCount | null>(null)
  const foundQueueRef = useRef<ReturnType<typeof createFoundQueue<FoundResponse>> | null>(null)
  if (foundQueueRef.current === null) {
    foundQueueRef.current = createFoundQueue<FoundResponse>({
      send: async (place) => {
        const live = countRef.current
        if (!live || live.status !== 'draft') throw new Error('Документ уже закрыт')
        if (live.id !== place.countId) {
          throw new Error('Находка относится к другому документу пересчёта')
        }
        // Кладём на сервер то, что оператор насчитал: автосохранения в экране
        // нет, факт живёт в состоянии React до нажатия «Сохранить».
        await saveCountActuals(token, live, touchedRef.current)
        sentSnapshotRef.current = live
        return await recordCountFound(token, live.id, place)
      },
      onApplied: (found) => {
        setCount((live) => {
          if (!live) return found.count
          // Пока летел запрос, кладовщик продолжал сканировать. Эти пики есть
          // на экране, но не в том снимке, который мы отправили.
          return mergeInFlightActuals(found.count, sentSnapshotRef.current ?? live, live)
        })
        setNote(found.notice)
      },
      onRejected: (err) => {
        setError(err instanceof Error ? err.message : 'Не удалось записать находку')
      },
      onPendingChange: setPendingFound,
      isRetryable: (err) => !(err instanceof InventoryHttpError),
    })
  }

  function recordFound(place: Omit<FoundPlace, 'countId'>) {
    if (!count || count.status !== 'draft') return
    setError(null)
    // Находка принадлежит тому документу, в котором её отсканировали, а не
    // тому, который открыт в момент повторной отправки.
    foundQueueRef.current?.push({ ...place, countId: count.id })
  }

  async function createContainer(kind: 'pallet' | 'box' | 'cargo_place') {
    if (!count || count.status !== 'draft') return
    if (!count.warehouseId) {
      setError('Не удалось определить склад документа')
      return
    }

    setLoading(true)
    setError(null)
    try {
      // Ручка документа, а не общая /warehouses/{id}/sorting-objects: она же
      // запоминает тару за документом, чтобы прунинг пустой тары не выбросил
      // её из дерева сразу после создания (см. inventoryCountApi).
      setCount(await createCountContainer(token, count.id, kind))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать тару')
    } finally {
      setLoading(false)
    }
  }

  /**
   * Добавить товар руками — кнопка «Добавить товар» (задача владельца 03.09.2026).
   *
   * Модалка позволяет выбрать сразу несколько товаров с количеством у каждого;
   * кладём их одним за другим той же ручкой, что и приёмка (applyPicker) — так
   * второй товар не потеряется, если первый уже лёг, а третий ещё нет.
   */
  async function addProduct(
    selections: Record<string, number>,
    placement: {
      cellId: string | null
      containerKind: 'pallet' | 'box' | 'cargo_place' | null
      containerId: string | null
    },
  ) {
    if (!count) return
    setLoading(true)
    setError(null)
    try {
      let current = count
      let lastNotice: string | null = null
      for (const [productId, rawQty] of Object.entries(selections)) {
        const quantity = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (quantity <= 0) continue
        const result = await addManualLine(token, current.id, {
          productId,
          quantity,
          cellId: placement.cellId,
          containerKind: placement.containerKind,
          containerId: placement.containerId,
        })
        current = result.count
        lastNotice = result.notice
      }
      setCount(current)
      if (lastNotice) setNote(lastNotice)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить товар')
    } finally {
      setLoading(false)
    }
  }

  async function create(warehouse: string, fill: CreateFill, comment: string) {
    setCreateOpen(false)
    setLoading(true)
    setError(null)
    try {
      const warehouseId = warehouses.find((w) => w.name === warehouse)?.id ?? null
      const sellerId = fill.seller ? (sellers.find((s) => s.name === fill.seller)?.id ?? null) : null
      const res = await fetch(apiUrl(BASE), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify({
          source: 'planned',
          filters: {
            seller_id: sellerId,
            category: fill.category,
            warehouse_id: warehouseId,
            all: !fill.seller && !fill.category,
          },
          comment: comment || null,
        }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setCount(toCount((await res.json()) as ApiDetail))
      await loadList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать документ')
    } finally {
      setLoading(false)
    }
  }

  // Документ по одному селлеру — модалка «Добавить товар» не должна предлагать
  // чужой товар. Документ без селлера (по всем сразу, или по объекту — там
  // фильтра по селлеру и не бывает, см. create_count) показывает весь каталог,
  // как и приёмка, когда у заявки нет селлера.
  const pickerSellerId = count && count.fill.mode === 'filters' ? count.fill.seller : null
  const pickerCatalog = useMemo(() => {
    if (!productCatalog) return null
    if (!pickerSellerId) return productCatalog
    return productCatalog.filter((row) => row.seller_id === pickerSellerId)
  }, [productCatalog, pickerSellerId])

  if (count) {
    return (
      <FfInventoryCountScreen
        count={count}
        loading={loading}
        error={error}
        note={note}
        onChange={(next, touchedLineId) => { noteTouched(touchedLineId); setCount(next) }}
        onSave={() => void save()}
        onPost={() => void post()}
        onCancelDocument={() => void cancelDocument()}
        pendingFound={pendingFound}
        onCreateContainer={(kind) => void createContainer(kind)}
        onFound={(place) => recordFound(place)}
        productCatalog={pickerCatalog}
        catalogLoading={catalogLoading}
        onAddProduct={(selections, placement) => addProduct(selections, placement)}
        onBack={() => {
          setCount(null)
          setNote(null)
          setError(null)
          void loadList()
        }}
      />
    )
  }

  return (
    <>
      <FfInventoryListScreen
        items={items}
        loading={loading}
        onOpen={(id) => void open(id)}
        onCreate={() => setCreateOpen(true)}
      />
      <InventoryCreateDialog
        open={createOpen}
        warehouses={warehouses.map((w) => w.name)}
        sellers={sellers.map((s) => s.name)}
        categories={categories}
        onClose={() => setCreateOpen(false)}
        onCreate={(warehouse, fill, comment) => void create(warehouse, fill, comment)}
      />
    </>
  )
}
