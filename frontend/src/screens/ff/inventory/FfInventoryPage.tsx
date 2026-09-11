import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import { changedActualIds, mergeInFlightActuals } from './InventoryRows'
import { createFoundQueue, FoundPlaceDeferredError, type FoundPlace } from './foundQueue'
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
  markCountPlaceEmpty,
  createCountContainer,
  addManualLine,
  moveCountLine,
  deleteCountContainer,
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

/**
 * Коды ошибок «Переложить в тару» и «Удалить тару» (WMS-153), которых нет в
 * общей таблице `readApiErrorMessage`: они специфичны для этих двух действий,
 * а часть — коды `warehouse_map_service.move_object` (тот же перенос
 * остатка, что и на карте склада), у которой уже есть своя локальная
 * таблица в FfWarehouseMapPage. Тот файл не трогаем — берём те же
 * формулировки здесь же, локально, а не правим общую таблицу под один экран.
 */
const INVENTORY_ERROR_MESSAGES: Record<string, string> = {
  already_there: 'Товар уже лежит в этой таре.',
  product_already_at_destination:
    'В этой таре уже есть этот товар. Выберите пустую тару или обновите пересчёт.',
  move_source_empty: 'Здесь по остатку сейчас пусто — переносить нечего.',
  container_not_empty: 'В этой таре есть товар — сначала переложите его, потом удаляйте.',
  comment_changed: 'Другой сотрудник изменил комментарий. Откройте документ заново и сверьте текст.',
  container_linked_to_inbound: 'Тара привязана к приёмке — удалить её отсюда нельзя.',
  object_not_found: 'Этот товар уже переместили или списали — обновите документ.',
  insufficient_stock: 'На исходном месте уже нет нужного количества — обновите документ.',
  destination_not_found: 'Тара назначения уже недоступна — обновите документ.',
}

function inventoryErrorMessage(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback
  return INVENTORY_ERROR_MESSAGES[err.message] ?? err.message ?? fallback
}

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

  const openVersionRef = useRef(0)

  async function open(id: string) {
    const version = ++openVersionRef.current
    setLoading(true)
    setError(null)
    setNote(null)
    try {
      const res = await fetch(apiUrl(`${BASE}/${id}`), { headers: { ...authHeaders(token) } })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const opened = toCount((await res.json()) as ApiDetail)
      if (version !== openVersionRef.current) return
      setCount(opened)
      countRef.current = opened
      savedCommentRef.current = opened.comment
      touchedRef.current = new Set()
      commentTouchedRef.current = false
      // Сканы, отложенные из-за ухода в другой документ, снова в работе — и
      // снова держат проведение, пока не доедут.
      foundQueueRef.current?.resumeFor(opened.id)
    } catch (err) {
      if (version === openVersionRef.current) {
        setError(err instanceof Error ? err.message : 'Не удалось открыть документ')
      }
    } finally {
      if (version === openVersionRef.current) setLoading(false)
    }
  }

  // Строки, которые правил ИМЕННО этот оператор в этом сеансе. Отправляем на
  // сервер только их: документ один, а кладовщиков в нём может быть двое, и
  // запись всего документа целиком стирает чужую работу.
  const touchedRef = useRef<Set<string>>(new Set())
  // WMS-155: тот же принцип для комментария. Правил ли этот оператор поле
  // «Комментарий» в этом сеансе — только тогда посылаем его на сервер, иначе
  // сохранение фактов затрёт чужой комментарий. Флаг сбрасывается после успеха.
  const commentTouchedRef = useRef<boolean>(false)
  const savedCommentRef = useRef('')
  // Очередь работает асинхронно и обязана видеть документ, каким он стал
  // к моменту отправки, а не каким был при постановке в очередь.
  const countRef = useRef<InventoryCount | null>(null)
  countRef.current = count

  function noteTouched(lineId?: string, commentChanged?: boolean) {
    if (lineId) touchedRef.current.add(lineId)
    if (commentChanged) commentTouchedRef.current = true
  }

  async function saveSnapshot(snapshot: InventoryCount): Promise<InventoryCount> {
    const saved = await saveCountActuals(token, snapshot, touchedRef.current,
      commentTouchedRef.current
        ? { updateComment: true, comment: snapshot.comment, expectedComment: savedCommentRef.current }
        : undefined)
    if (countRef.current?.id === snapshot.id) {
      savedCommentRef.current = saved.comment
      // Changes entered while a request was in flight remain local and dirty.
      touchedRef.current = changedActualIds(countRef.current, snapshot)
      commentTouchedRef.current = countRef.current.comment !== snapshot.comment
    }
    return saved
  }

  async function save() {
    if (!count || loading) return
    setLoading(true)
    try {
      const commentOptions = commentTouchedRef.current
        ? { updateComment: true, comment: count.comment, expectedComment: savedCommentRef.current }
        : undefined
      const res = await fetch(apiUrl(`${BASE}/${count.id}/lines`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify(actualPayload(count, touchedRef.current, commentOptions)),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const saved = toCount((await res.json()) as ApiDetail)
      if (countRef.current?.id !== saved.id) return
      setCount((current) => current ? mergeInFlightActuals(saved, count, current) : current)
      savedCommentRef.current = saved.comment
      touchedRef.current = changedActualIds(countRef.current, count)
      commentTouchedRef.current = countRef.current.comment !== count.comment
      setNote('Сохранено. Остатки не тронуты.')
    } catch (err) {
      setError(inventoryErrorMessage(err, 'Не удалось сохранить'))
    } finally {
      setLoading(false)
    }
  }

  async function post() {
    if (!count || loading) return
    setLoading(true)
    try {
      // Сначала кладём введённое, потом проводим: иначе проведём то, что сервер
      // помнит с прошлого сохранения, а не то, что человек видит на экране.
      // WMS-155: комментарий, если оператор его редактировал, уходит здесь же.
      const commentOptions = commentTouchedRef.current
        ? { updateComment: true, comment: count.comment, expectedComment: savedCommentRef.current }
        : undefined
      const saved = await fetch(apiUrl(`${BASE}/${count.id}/lines`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify(actualPayload(count, touchedRef.current, commentOptions)),
      })
      if (!saved.ok) throw new Error(await readApiErrorMessage(saved))
      const savedDetail = toCount(await saved.json() as ApiDetail)
      if (countRef.current?.id === count.id) {
        savedCommentRef.current = savedDetail.comment
        commentTouchedRef.current = false
      }
      const res = await fetch(apiUrl(`${BASE}/${count.id}/post`), {
        method: 'POST',
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const result = (await res.json()) as {
        posted_lines: number
        changed_balance_count: number
      }
      if (countRef.current?.id !== count.id) return
      await open(count.id)
      await loadList()
      setNote(postResultNote(result))
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
        if (!live || live.id !== place.countId) {
          // Оператор ушёл в другой документ, пока скан не доехал. Он не потерян:
          // очередь отложит его до возвращения в свой пересчёт.
          throw new FoundPlaceDeferredError('Находка относится к другому документу пересчёта')
        }
        if (live.status !== 'draft') throw new Error('Документ уже закрыт')
        // Кладём на сервер то, что оператор насчитал: автосохранения в экране
        // нет, факт живёт в состоянии React до нажатия «Сохранить».
        const saved = await saveSnapshot(live)
        sentSnapshotRef.current = { ...live, comment: saved.comment }
        return await recordCountFound(token, live.id, place)
      },
      onApplied: (found) => {
        setCount((live) => {
          if (!live || live.id !== found.count.id) return live
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
    if (!count || loading || count.status !== 'draft') return
    setError(null)
    // Находка принадлежит тому документу, в котором её отсканировали, а не
    // тому, который открыт в момент повторной отправки.
    foundQueueRef.current?.push({ ...place, countId: count.id })
  }

  async function createContainer(kind: 'pallet' | 'box' | 'cargo_place', cellId: string | null) {
    if (!count || loading || count.status !== 'draft') return
    if (!count.warehouseId) {
      setError('Не удалось определить склад документа')
      return
    }

    setLoading(true)
    setError(null)
    try {
      // Ручка документа, а не общая /warehouses/{id}/sorting-objects: она же
      // запоминает тару за документом, чтобы прунинг пустой тары не выбросил
      // её из дерева сразу после создания (см. inventoryCountApi). cellId —
      // выделенная ячейка (задача 1 доработки 03.09.2026): без неё тара
      // уезжает в зону сортировки, как и раньше.
      await saveSnapshot(count)
      const updated = await createCountContainer(token, count.id, kind, cellId)
      setCount((current) => current?.id === updated.id ? updated : current)
    } catch (err) {
      setError(inventoryErrorMessage(err, 'Не удалось создать тару'))
    } finally {
      setLoading(false)
    }
  }

  /**
   * Переложить товар в тару — вторая доработка от 03.09.2026, WMS-153.
   *
   * Тот же перенос остатка, что и на карте склада: сервер сам находит
   * остаток по адресу строки и переносит его (inventoryCountApi.moveCountLine).
   */
  async function moveLine(lineId: string, target: { containerKind: 'pallet' | 'box' | 'cargo_place'; containerId: string }) {
    if (!count || loading || count.status !== 'draft') return
    setLoading(true)
    setError(null)
    try {
      await saveSnapshot(count)
      const updated = await moveCountLine(token, count.id, lineId, target)
      setCount((current) => current?.id === updated.id ? updated : current)
      setNote('Товар перенесён.')
    } catch (err) {
      setError(inventoryErrorMessage(err, 'Не удалось перенести товар'))
    } finally {
      setLoading(false)
    }
  }

  /**
   * Удалить пустую тару прямо из документа — третья доработка от 03.09.2026,
   * WMS-153. Сервер сам отказывает понятным сообщением, если тара не пуста.
   */
  async function deleteContainer(target: { kind: 'pallet' | 'box' | 'cargo_place'; id: string }) {
    if (!count || loading || count.status !== 'draft') return
    setLoading(true)
    setError(null)
    try {
      await saveSnapshot(count)
      const updated = await deleteCountContainer(token, count.id, target)
      setCount((current) => current?.id === updated.id ? updated : current)
      setNote('Тара удалена.')
    } catch (err) {
      setError(inventoryErrorMessage(err, 'Не удалось удалить тару'))
    } finally {
      setLoading(false)
    }
  }

  async function markEmpty(target: { kind: 'cell' | 'container'; id: string }) {
    if (!count || loading) return
    const container = target.kind === 'container'
      ? count.scannableContainers?.find((item) => item.id === target.id)
      : undefined
    function findKind(nodes: InventoryCount['cells'][number]['children']): 'pallet' | 'box' | 'cargo_place' | undefined {
      for (const node of nodes) {
        if (node.kind === 'product') continue
        if (node.id === target.id) return node.kind
        const nested = findKind(node.children)
        if (nested) return nested
      }
    }
    const kind = target.kind === 'cell' ? 'cell'
      : container?.kind ?? count.cells.map((cell) => findKind(cell.children)).find(Boolean)
    if (!kind) return
    setLoading(true)
    setError(null)
    try {
      await saveCountActuals(token, count, touchedRef.current, commentTouchedRef.current
        ? { updateComment: true, comment: count.comment, expectedComment: savedCommentRef.current }
        : undefined)
      const updated = await markCountPlaceEmpty(token, count.id, { kind, id: target.id })
      if (countRef.current?.id !== updated.id) return
      setCount(updated)
      savedCommentRef.current = updated.comment
      touchedRef.current = new Set()
      commentTouchedRef.current = false
      setNote('Пустое место подтверждено. При проведении остатки здесь станут нулевыми; пустая складская тара будет удалена.')
    } catch (err) {
      setError(inventoryErrorMessage(err, 'Не удалось подтвердить пустое место'))
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
    if (!count || loading) return
    setLoading(true)
    setError(null)
    try {
      let current = await saveSnapshot(count)
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
      setCount((live) => live?.id === current.id ? current : live)
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
            product_ids: fill.productIds,
            all: !fill.seller && !fill.category && !fill.productIds.length,
          },
          comment: comment || null,
        }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const created = toCount((await res.json()) as ApiDetail)
      savedCommentRef.current = created.comment
      touchedRef.current = new Set()
      commentTouchedRef.current = false
      setCount(created)
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
        onChange={(next, touchedLineId, commentChanged) => {
          if (loading) return
          noteTouched(touchedLineId, commentChanged)
          setCount(next)
        }}
        onSave={() => void save()}
        onPost={() => void post()}
        onCancelDocument={() => void cancelDocument()}
        pendingFound={pendingFound}
        onCreateContainer={(kind, cellId) => void createContainer(kind, cellId)}
        onMoveLine={(lineId, target) => void moveLine(lineId, target)}
        onDeleteContainer={(target) => void deleteContainer(target)}
        onFound={(place) => recordFound(place)}
        productCatalog={pickerCatalog}
        catalogLoading={catalogLoading}
        onAddProduct={(selections, placement) => addProduct(selections, placement)}
        onMarkEmpty={(target) => void markEmpty(target)}
        onBack={() => {
          openVersionRef.current += 1
          countRef.current = null
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
        products={productCatalog}
        productsLoading={catalogLoading}
        onClose={() => setCreateOpen(false)}
        onCreate={(warehouse, fill, comment) => void create(warehouse, fill, comment)}
      />
    </>
  )
}
