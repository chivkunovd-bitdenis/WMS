import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
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

  async function save() {
    if (!count) return
    setLoading(true)
    try {
      const res = await fetch(apiUrl(`${BASE}/${count.id}/lines`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify(actualPayload(count)),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      setCount(toCount((await res.json()) as ApiDetail))
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
        body: JSON.stringify(actualPayload(count)),
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
        onChange={setCount}
        onSave={() => void save()}
        onPost={() => void post()}
        onCancelDocument={() => void cancelDocument()}
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
        categories={[]}
        onClose={() => setCreateOpen(false)}
        onCreate={(warehouse, fill, comment) => void create(warehouse, fill, comment)}
      />
    </>
  )
}
