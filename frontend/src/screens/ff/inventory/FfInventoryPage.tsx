import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import { FfInventoryListScreen } from './FfInventoryListScreen'
import { InventoryCreateDialog, type CreateFill } from './InventoryCreateDialog'
import type { CountListItem, CountStatus, InventoryCount, ProductNode } from './InventoryTypes'

// Экран инвентаризации, подключённый к серверу.
//
// Вся работа с документом — в FfInventoryCountScreen, список — в
// FfInventoryListScreen; здесь только загрузка, сохранение и проведение.
// Разделено намеренно: те два экрана уже приняты владельцем по макету и не
// должны знать про сеть, иначе их нельзя будет открыть в превью без сервера.

const BASE = '/operations/inventory-counts'

// Заголовок авторизации собираем здесь: в приложении он живёт локальной функцией
// внутри App.tsx и наружу не отдаётся, а тащить его пропсом через два экрана
// ради одной строки — лишний шов.
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

type ApiProduct = {
  id: string
  name: string
  sku: string
  seller: string
  category: string | null
  barcode: string | null
  photo_url: string | null
  expected: number
  actual: number | null
  expected_now: number | null
}

type ApiCell = { id: string; label: string; children: ApiProduct[] }

type ApiDetail = {
  id: string
  number: string
  status: string
  warehouse_name: string
  fill: { mode: 'object' | 'all' | 'filters'; seller_id: string | null; category: string | null; object_label: string | null }
  created_at: string
  created_by: string
  posted_at: string | null
  posted_by: string | null
  comment: string
  address_storage: boolean
  cells: ApiCell[]
}

type ApiSummary = {
  id: string
  number: string
  status: string
  warehouse_name: string
  fill_label: string
  created_at: string
  created_by: string
  lines: number
  counted: number
  discrepancies: number
  surplus: number
  shortage: number
}

function toProduct(node: ApiProduct): ProductNode {
  return {
    kind: 'product',
    id: node.id,
    name: node.name,
    sku: node.sku,
    seller: node.seller,
    category: node.category ?? '—',
    barcode: node.barcode ?? '',
    photoUrl: node.photo_url,
    expected: node.expected,
    actual: node.actual,
    // Остаток уехал после наполнения документа — экран покажет предупреждение.
    ...(node.expected_now === null || node.expected_now === node.expected
      ? {}
      : { expectedNow: node.expected_now }),
  }
}

function toCount(detail: ApiDetail): InventoryCount {
  return {
    id: detail.id,
    number: detail.number,
    status: detail.status as CountStatus,
    warehouseName: detail.warehouse_name,
    fill:
      detail.fill.mode === 'object'
        ? { mode: 'object', objectLabel: detail.fill.object_label ?? 'По объекту' }
        : detail.fill.mode === 'all'
          ? { mode: 'all' }
          : { mode: 'filters', seller: detail.fill.seller_id, category: detail.fill.category },
    createdAt: detail.created_at,
    createdBy: detail.created_by,
    postedAt: detail.posted_at,
    postedBy: detail.posted_by,
    comment: detail.comment,
    addressStorage: detail.address_storage,
    cells: detail.cells.map((cell) => ({
      id: cell.id,
      label: cell.label,
      children: cell.children.map(toProduct),
    })),
  }
}

function toListItem(row: ApiSummary): CountListItem {
  return {
    id: row.id,
    number: row.number,
    status: row.status as CountStatus,
    warehouseName: row.warehouse_name,
    fillLabel: row.fill_label,
    createdAt: row.created_at,
    createdBy: row.created_by,
    lines: row.lines,
    counted: row.counted,
    discrepancies: row.discrepancies,
    surplus: row.surplus,
    shortage: row.shortage,
  }
}

/** Введённые факты для отправки: сервер ждёт строку и число. */
function actualPayload(count: InventoryCount) {
  const lines: Array<{ line_id: string; actual_quantity: number | null }> = []
  for (const cell of count.cells) {
    for (const node of cell.children) {
      if (node.kind !== 'product') continue
      lines.push({ line_id: node.id, actual_quantity: node.actual })
    }
  }
  return { lines }
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
      setNote(
        result.changed_balance_count > 0
          ? `Проведено движений: ${result.posted_lines}. По ${result.changed_balance_count} строкам остаток успел измениться — посчитано от нового.`
          : `Проведено движений: ${result.posted_lines}.`,
      )
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
