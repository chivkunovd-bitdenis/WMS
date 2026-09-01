import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import type {
  ContainerNode,
  CountListItem,
  CountStatus,
  InventoryCount,
  InventoryNode,
  ProductNode,
} from './InventoryTypes'

// Серверная обвязка инвентаризации, общая для двух входов в неё.
//
// Документ создаётся из двух мест: со своего экрана по фильтрам и со строки
// карты склада по конкретному объекту. Обвязка одна, иначе два места начнут
// расходиться в том, как сохраняют факт и как проводят движения.

export const INVENTORY_BASE = '/operations/inventory-counts'

/**
 * Дата документа в человеческом виде: «28.08.2026 23:39».
 *
 * Экраны инвентаризации приняты по макету, где дата уже была строкой, и про
 * машинный формат сервера они не знают. Переводим на границе, иначе оператор
 * видит «2026-08-28T20:39:37.982702+00:00».
 */
function humanMoment(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return iso
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(d)
    .replace(', ', ' ')
}

export function inventoryAuthHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

export type ApiProduct = {
  kind: 'product'
  id: string
  name: string
  sku: string
  seller: string
  category: string | null
  barcode: string | null
  wb_vendor_code: string | null
  wb_barcode: string | null
  wb_size: string | null
  photo_url: string | null
  expected: number
  actual: number | null
  expected_now: number | null
}

export type ApiContainer = {
  kind: 'pallet' | 'box' | 'cargo_place'
  id: string
  code: string
  barcode: string | null
  children: ApiNode[]
}

export type ApiNode = ApiProduct | ApiContainer

export type ApiCell = {
  id: string
  label: string
  barcode: string | null
  children: ApiNode[]
}

export type ApiDetail = {
  id: string
  number: string
  status: string
  warehouse_id: string | null
  warehouse_name: string
  fill: {
    mode: 'object' | 'all' | 'filters'
    seller_id: string | null
    category: string | null
    object_label: string | null
  }
  created_at: string
  created_by: string
  posted_at: string | null
  posted_by: string | null
  comment: string
  address_storage: boolean
  cells: ApiCell[]
}

export type ApiSummary = {
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

export type PostResult = {
  posted_lines: number
  changed_balance_count: number
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
    wbVendorCode: node.wb_vendor_code,
    wbBarcode: node.wb_barcode,
    wbSize: node.wb_size,
    photoUrl: node.photo_url,
    expected: node.expected,
    actual: node.actual,
    // Остаток уехал после наполнения документа — экран покажет предупреждение.
    ...(node.expected_now === null || node.expected_now === node.expected
      ? {}
      : { expectedNow: node.expected_now }),
  }
}

function toNode(node: ApiNode): InventoryNode {
  if (node.kind === 'product') return toProduct(node)
  const container: ContainerNode = {
    kind: node.kind,
    id: node.id,
    code: node.code,
    barcode: node.barcode,
    children: node.children.map(toNode),
  }
  return container
}

export function toCount(detail: ApiDetail): InventoryCount {
  return {
    id: detail.id,
    number: detail.number,
    status: detail.status as CountStatus,
    warehouseId: detail.warehouse_id,
    warehouseName: detail.warehouse_name,
    fill:
      detail.fill.mode === 'object'
        ? { mode: 'object', objectLabel: detail.fill.object_label ?? 'По объекту' }
        : detail.fill.mode === 'all'
          ? { mode: 'all' }
          : { mode: 'filters', seller: detail.fill.seller_id, category: detail.fill.category },
    createdAt: humanMoment(detail.created_at),
    createdBy: detail.created_by,
    postedAt: detail.posted_at === null ? null : humanMoment(detail.posted_at),
    postedBy: detail.posted_by,
    comment: detail.comment,
    addressStorage: detail.address_storage,
    cells: detail.cells.map((cell) => ({
      id: cell.id,
      label: cell.label,
      barcode: cell.barcode,
      children: cell.children.map(toNode),
    })),
  }
}

export function toListItem(row: ApiSummary): CountListItem {
  return {
    id: row.id,
    number: row.number,
    status: row.status as CountStatus,
    warehouseName: row.warehouse_name,
    fillLabel: row.fill_label,
    createdAt: humanMoment(row.created_at),
    createdBy: row.created_by,
    lines: row.lines,
    counted: row.counted,
    discrepancies: row.discrepancies,
    surplus: row.surplus,
    shortage: row.shortage,
  }
}

/** Введённые факты для отправки: сервер ждёт строку и число. */
export function actualPayload(count: InventoryCount) {
  const lines: Array<{ line_id: string; actual_quantity: number | null }> = []
  function collect(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') {
        lines.push({ line_id: node.id, actual_quantity: node.actual })
      } else {
        collect(node.children)
      }
    }
  }
  for (const cell of count.cells) {
    collect(cell.children)
  }
  return { lines }
}

/** Виды объектов, по которым сервер умеет заводить документ. */
export type CountObjectType = 'product' | 'cell' | 'pallet' | 'box' | 'cargo_place'

/**
 * Завести документ по одному объекту: коробу, палете, грузоместу, ячейке, товару.
 *
 * Номер и строки выдаёт сервер — на клиенте документ не выдумывается, иначе
 * сохранение придётся сопоставлять по названиям, а не по строкам.
 */
export async function createObjectCount(
  token: string,
  object: { type: CountObjectType; id: string },
  comment?: string | null,
): Promise<InventoryCount> {
  const res = await fetch(apiUrl(INVENTORY_BASE), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...inventoryAuthHeaders(token) },
    body: JSON.stringify({
      source: 'object',
      object: { type: object.type, id: object.id },
      comment: comment || null,
    }),
  })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return toCount((await res.json()) as ApiDetail)
}

/** Положить введённый факт. Остатки не трогает: документ остаётся черновиком. */
export async function saveCountActuals(
  token: string,
  count: InventoryCount,
): Promise<InventoryCount> {
  const res = await fetch(apiUrl(`${INVENTORY_BASE}/${count.id}/lines`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...inventoryAuthHeaders(token) },
    body: JSON.stringify(actualPayload(count)),
  })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return toCount((await res.json()) as ApiDetail)
}

/**
 * Провести документ: выровнять остаток по факту и записать движения.
 *
 * Сначала кладём введённое, потом проводим — иначе проведётся то, что сервер
 * помнит с прошлого сохранения, а не то, что человек видит на экране.
 */
export async function postCount(token: string, count: InventoryCount): Promise<PostResult> {
  const saved = await fetch(apiUrl(`${INVENTORY_BASE}/${count.id}/lines`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...inventoryAuthHeaders(token) },
    body: JSON.stringify(actualPayload(count)),
  })
  if (!saved.ok) throw new Error(await readApiErrorMessage(saved))
  const res = await fetch(apiUrl(`${INVENTORY_BASE}/${count.id}/post`), {
    method: 'POST',
    headers: { ...inventoryAuthHeaders(token) },
  })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return (await res.json()) as PostResult
}

/** Человеческое сообщение о том, что дало проведение. */
export function postResultNote(result: PostResult): string {
  return result.changed_balance_count > 0
    ? `Проведено движений: ${result.posted_lines}. По ${result.changed_balance_count} строкам остаток успел измениться — посчитано от нового.`
    : `Проведено движений: ${result.posted_lines}.`
}
