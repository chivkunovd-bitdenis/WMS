import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import {
  CountOpDeferredError,
  createCountOps,
  type CountOps,
  type CountOpsView,
  type ScanPlace,
} from './countOpsQueue'
import type { WbProductPickerCatalogRow } from '../../../components/WbProductPickerDialog'

/**
 * Строка каталога для модалки «Добавить товар» — тот же WbProductPickerCatalogRow,
 * плюс seller_id: он нужен, чтобы отобрать товары одного продавца самим на
 * экране, а не просить сервер фильтровать (ff-catalog фильтрует по seller_id
 * только для админа — обычный кладовщик с правом PERM_INVENTORY получил бы 403).
 */
type ManualAddCatalogRow = WbProductPickerCatalogRow & { seller_id: string | null }

import { FfInventoryListScreen } from './FfInventoryListScreen'
import { InventoryCreateDialog, type CreateFill } from './InventoryCreateDialog'
import type { CountListItem, InventoryCount } from './InventoryTypes'
import {
  INVENTORY_BASE as BASE,
  inventoryAuthHeaders as authHeaders,
  postResultNote,
  toCount,
  toListItem,
  type ApiDetail,
  type ApiSummary,
  recordCountFound,
  fetchCount,
  putCountLines,
  postCountOnly,
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
//
// WMS-542: все изменения открытого документа идут одной очередью операций
// (countOpsQueue.ts) — см. комментарий у её создания ниже.

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
  // WMS-542 (F4): line_id указывал не на ту строку — экран устарел, надо
  // перечитать документ, а не пробовать тем же id ещё раз.
  line_not_found: 'Эта строка уже изменилась — обновите документ.',
  line_barcode_mismatch: 'Код не соответствует этой строке — обновите документ.',
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

  // WMS-542: всё, что меняет открытый документ на сервере, — скан (+1),
  // ручное число строки, комментарий, перечитывание, тара, перенос, «здесь
  // пусто», проведение, отмена — идёт ОДНОЙ очередью по одной операции
  // (countOpsQueue.ts). Раньше скан, ручная правка и «Сохранить» уходили
  // разными путями, обгоняли друг друга и затирали друг друга на сервере и на
  // экране (ревью Astra №1 и №2, F1–F9). Документ на экране — `view.count`:
  // последний ответ сервера плюс ещё не подтверждённые операции и черновики.
  const [view, setView] = useState<CountOpsView>({ count: null, pendingScans: 0 })
  const count = view.count
  const tokenRef = useRef(token)
  tokenRef.current = token
  const opsRef = useRef<CountOps | null>(null)
  if (opsRef.current === null) {
    opsRef.current = createCountOps({
      transport: {
        found: async (countId, place) => {
          const found = await recordCountFound(tokenRef.current, countId, place)
          return { count: found.count, notice: found.notice }
        },
        putLines: (countId, lines, comment) => putCountLines(tokenRef.current, countId, lines, comment),
        get: (countId) => fetchCount(tokenRef.current, countId),
      },
      // Обрыв связи и шлюз, который на секунду отвалился при выкатке, —
      // повторяем той же операцией. Отказ сервера — показываем человеку.
      isRetryable: (err) => !(err instanceof InventoryHttpError) || err.status >= 502,
      onChange: setView,
      // Обычный скан несёт пустой текст — не затираем им «Сохранено» и т.п.
      onScanNotice: (notice) => setNote(notice),
      onRejected: (err) => setError(inventoryErrorMessage(err, 'Не удалось записать находку')),
    })
  }
  const ops = opsRef.current

  async function open(id: string) {
    setLoading(true)
    setError(null)
    setNote(null)
    try {
      // Отложенные сканы этого документа (оператор уходил в другой) уходят
      // раньше перечитывания и снова держат проведение, пока не доедут.
      await ops.open(id)
    } catch (err) {
      if (ops.currentId() === id) {
        setError(err instanceof Error ? err.message : 'Не удалось открыть документ')
      }
    } finally {
      if (ops.currentId() === id) setLoading(false)
    }
  }

  /** Документ ушёл из-под рук (закрыли), пока ждали очередь, — ошибку не показываем. */
  function stillOpen(id: string, err: unknown): boolean {
    return !(err instanceof CountOpDeferredError) && ops.currentId() === id
  }

  async function save() {
    if (!count || loading) return
    const id = count.id
    setLoading(true)
    try {
      // Несохранённые ручные числа и комментарий встают в очередь за всем, что
      // уже отсканировано, и «Сохранить» ждёт их. Нечего отправлять — документ
      // перечитывается в той же очереди: экран подтянет и чужие сканы.
      await ops.save()
      if (ops.currentId() === id) setNote('Сохранено. Остатки не тронуты.')
    } catch (err) {
      if (stillOpen(id, err)) setError(inventoryErrorMessage(err, 'Не удалось сохранить'))
    } finally {
      setLoading(false)
    }
  }

  async function post() {
    if (!count || loading) return
    const id = count.id
    setLoading(true)
    try {
      // Сначала кладём введённое руками, потом проводим: иначе проведём то,
      // что сервер помнит с прошлого сохранения, а не то, что человек видит
      // на экране. WMS-155: комментарий, если оператор его редактировал,
      // уходит здесь же.
      await ops.flush()
      const result = await ops.action(async () => ({ count: null, result: await postCountOnly(tokenRef.current, id) }))
      if (ops.currentId() !== id) return
      await open(id)
      await loadList()
      setNote(postResultNote(result))
    } catch (err) {
      if (stillOpen(id, err)) setError(err instanceof Error ? err.message : 'Не удалось провести')
    } finally {
      setLoading(false)
    }
  }

  async function cancelDocument() {
    if (!count) return
    const id = count.id
    try {
      await ops.action(async () => {
        const res = await fetch(apiUrl(`${BASE}/${id}`), {
          method: 'DELETE',
          headers: { ...authHeaders(tokenRef.current) },
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
        return { count: null, result: null }
      })
      ops.close()
      await loadList()
    } catch (err) {
      if (stillOpen(id, err)) setError(err instanceof Error ? err.message : 'Не удалось отменить документ')
    }
  }

  function recordFound(place: ScanPlace) {
    // Сканы не отбрасываются и во время «Сохранить»: встают в очередь за ним.
    if (!count || count.status !== 'draft') return
    setError(null)
    ops.scan(place)
  }

  /** Ручная правка числа строки — черновик до «Сохранить» (или до скана этой строки). */
  function manualEdit(lineId: string, value: number | null) {
    if (!count || loading) return
    ops.editLine(lineId, value)
  }

  /**
   * Структурное действие над документом: сначала несохранённые ручные числа
   * (иначе действие подхватило бы прошлые числа, а не то, что оператор только
   * что набрал), потом само действие — в той же очереди, после сканов.
   */
  async function runAction(run: () => Promise<InventoryCount>): Promise<InventoryCount> {
    await ops.flush()
    return ops.action(async () => {
      const updated = await run()
      return { count: updated, result: updated }
    })
  }

  async function createContainer(kind: 'pallet' | 'box' | 'cargo_place', cellId: string | null) {
    if (!count || loading || count.status !== 'draft') return
    if (!count.warehouseId) {
      setError('Не удалось определить склад документа')
      return
    }
    const id = count.id

    setLoading(true)
    setError(null)
    try {
      // Ручка документа, а не общая /warehouses/{id}/sorting-objects: она же
      // запоминает тару за документом, чтобы прунинг пустой тары не выбросил
      // её из дерева сразу после создания (см. inventoryCountApi). cellId —
      // выделенная ячейка (задача 1 доработки 03.09.2026): без неё тара
      // уезжает в зону сортировки, как и раньше.
      await runAction(() => createCountContainer(tokenRef.current, id, kind, cellId))
    } catch (err) {
      if (stillOpen(id, err)) setError(inventoryErrorMessage(err, 'Не удалось создать тару'))
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
    const id = count.id
    setLoading(true)
    setError(null)
    try {
      await runAction(() => moveCountLine(tokenRef.current, id, lineId, target))
      setNote('Товар перенесён.')
    } catch (err) {
      if (stillOpen(id, err)) setError(inventoryErrorMessage(err, 'Не удалось перенести товар'))
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
    const id = count.id
    setLoading(true)
    setError(null)
    try {
      await runAction(() => deleteCountContainer(tokenRef.current, id, target))
      setNote('Тара удалена.')
    } catch (err) {
      if (stillOpen(id, err)) setError(inventoryErrorMessage(err, 'Не удалось удалить тару'))
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
    const id = count.id
    setLoading(true)
    setError(null)
    try {
      // Ответ сервера становится документом на экране; сканы, сделанные уже
      // после нажатия, стоят в очереди за этим действием и лягут поверх.
      await runAction(() => markCountPlaceEmpty(tokenRef.current, id, { kind, id: target.id }))
      if (ops.currentId() !== id) return
      setNote('Пустое место подтверждено. При проведении остатки здесь станут нулевыми; пустая складская тара будет удалена.')
    } catch (err) {
      if (stillOpen(id, err)) setError(inventoryErrorMessage(err, 'Не удалось подтвердить пустое место'))
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
    const id = count.id
    setLoading(true)
    setError(null)
    try {
      await ops.flush()
      let lastNotice: string | null = null
      for (const [productId, rawQty] of Object.entries(selections)) {
        const quantity = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (quantity <= 0) continue
        lastNotice = await ops.action(async () => {
          const result = await addManualLine(tokenRef.current, id, {
            productId,
            quantity,
            cellId: placement.cellId,
            containerKind: placement.containerKind,
            containerId: placement.containerId,
          })
          return { count: result.count, result: result.notice }
        })
      }
      if (lastNotice && ops.currentId() === id) setNote(lastNotice)
    } catch (err) {
      if (stillOpen(id, err)) setError(err instanceof Error ? err.message : 'Не удалось добавить товар')
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
      ops.show(created)
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
        onChange={(next, _touchedLineId, commentChanged) => {
          // Числа строк сюда больше не приходят: скан — это операция очереди
          // (onFound), ручное число — onManualEdit. Здесь только комментарий.
          if (loading) return
          if (commentChanged) ops.editComment(next.comment)
        }}
        onManualEdit={(lineId, value) => manualEdit(lineId, value)}
        onSave={() => void save()}
        onPost={() => void post()}
        onCancelDocument={() => void cancelDocument()}
        pendingFound={view.pendingScans}
        onCreateContainer={(kind, cellId) => void createContainer(kind, cellId)}
        onMoveLine={(lineId, target) => void moveLine(lineId, target)}
        onDeleteContainer={(target) => void deleteContainer(target)}
        onFound={(place) => recordFound(place)}
        productCatalog={pickerCatalog}
        catalogLoading={catalogLoading}
        onAddProduct={(selections, placement) => addProduct(selections, placement)}
        onMarkEmpty={(target) => void markEmpty(target)}
        onBack={() => {
          // Несохранённые черновики пропадают, как и раньше; сканы и уже
          // отправленные правки этого документа дождутся возвращения в него.
          ops.close()
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
