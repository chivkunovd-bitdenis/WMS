import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import { mergeInFlightActuals } from './InventoryRows'
import { createFoundQueue, type FoundPlace } from './foundQueue'

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
  const foundQueueRef = useRef<ReturnType<typeof createFoundQueue<FoundResponse>> | null>(null)
  if (foundQueueRef.current === null) {
    foundQueueRef.current = createFoundQueue<FoundResponse>({
      send: async (place) => {
        const live = countRef.current
        if (!live || live.status !== 'draft') throw new Error('Документ уже закрыт')
        // Кладём на сервер то, что оператор насчитал: автосохранения в экране
        // нет, факт живёт в состоянии React до нажатия «Сохранить».
        await saveCountActuals(token, live, touchedRef.current)
        return await recordCountFound(token, live.id, place)
      },
      onApplied: (found) => {
        setCount((live) => {
          if (!live) return found.count
          // Пока летел запрос, кладовщик продолжал сканировать. Эти пики есть
          // на экране, но не в том снимке, который мы отправили.
          return mergeInFlightActuals(found.count, live, live)
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

  function recordFound(place: FoundPlace) {
    if (!count || count.status !== 'draft') return
    setError(null)
    foundQueueRef.current?.push(place)
  }

  async function createContainer(kind: 'pallet' | 'box' | 'cargo_place') {
    if (!count || count.status !== 'draft') return
    const warehouseId = count.warehouseId
    if (!warehouseId) {
      setError('Не удалось определить склад документа')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-objects`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify({ kind }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      await open(count.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать тару')
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
