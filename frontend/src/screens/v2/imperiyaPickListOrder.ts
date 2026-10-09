// ⛔️⛔️⛔️ КЛИЕНТСКОЕ ИСКЛЮЧЕНИЕ — ТОЛЬКО ДЛЯ «ИМПЕРИЯ ФФ» (WMS-710) ⛔️⛔️⛔️
//
// Владелец 09.10.2026: «то, что они видят на подборе, точно в этой
// последовательности у них должно печататься в листе подбора… сделай это
// фичер-тоглом только для империи львов»; «Инб убирай вообще»; клиент 09.10:
// «лист подбора вмс не совпадает с печатным листом», «в вмс с какой приемки брать
// не понятно — вывести номера приемок и номера возвратов»; владелец: «сделай как
// они просят».
//
// 1. Печатный лист подбора у Империи идёт тем же маршрутом, что вкладка «Подбор»
//    (pickRows.cellPickRowsOf — та же функция, что рисует вкладку): место за
//    местом, в каждой строке — товар из этого места, его приёмка/возврат с датой и
//    короб. Колонки листа прежние. Заказы, стикер и маркировка — в первой строке
//    товара (иначе один заказ выглядит как пять). Номер строки — номер товара.
// 2. На вкладке «Подбор» у Империи к коробу дописана его приёмка/возврат.
// В строке места нет системного кода INB. У всех остальных клиентов всё прежнее.
// Реестр исключений: docs/KLIENTSKIE_ISKLYUCHENIYA.md. Не переносить на других
// клиентов и не удалять без решения владельца.
//
// ВНИМАНИЕ: сборка данных вкладки ниже повторяет FfUnloadPickPage (ячейки, тара,
// остаток и снятое по местам). Меняешь там — поправь и здесь.

import { cellPickRowsOf, rowsOf, pickKey, type PickedMap } from '../ff/unload-pick/pickRows'
import { cellRef, objRef } from '../ff/unload-pick/pickStub'
import type { Cell, GoodsLine, ObjKind, PickProduct, PlanLine, WarehouseObject } from '../ff/unload-pick/pickStub'
import type { FbsPickOptionProduct, FbsPickingContext } from './fbsApi'
import type { FbsPickingListPrintRow } from './fbsUx'

export const IMPERIYA_FF_TENANT_ID = '7b98a8aa-c03c-4649-9677-a645be45c622'

/** Тенант из токена входа (в нём есть tenant_id). Ошибка разбора — «не Империя». */
export function tenantIdFromToken(token: string | null | undefined): string | null {
  try {
    const part = token?.split('.')[1]
    if (!part) return null
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='))
    const value = (JSON.parse(json) as { tenant_id?: unknown }).tenant_id
    return typeof value === 'string' ? value : null
  } catch {
    return null
  }
}

/** ТОЛЬКО Империя ФФ: лист подбора маршрутом вкладки и приёмка у коробов на вкладке. */
export function usesTabOrderPickList(token: string | null | undefined): boolean {
  return tenantIdFromToken(token) === IMPERIYA_FF_TENANT_ID
}

/** «Короб №19 · INB-VSA97KFYK5YRAX · Ж-1-7: 1 шт.» → «Короб №19 · Ж-1-7: 1 шт.» */
export function withoutInbCode(line: string): string {
  return line.replace(/\s·\s*INB-[0-9A-Z]+/g, '')
}

type ContextGroup = FbsPickingContext['source_groups'][number] & { date?: string | null; line_keys?: string[] }
type ApiSource = FbsPickOptionProduct['locations'][number]['sources'][number] & { quantity?: number; picked?: number }
type PrintRow = FbsPickingListPrintRow & { key: string }

function groupTitle(group: ContextGroup): string {
  return group.date ? `${group.title.replace(/:\s*$/, '')} от ${group.date}` : group.title
}

/** Приёмка/возврат каждого короба по контексту печати: id тары → «П: №000090 от 25.09.2026». */
export function boxReceiptLabels(contexts: FbsPickingContext[]): Map<string, string> {
  const labels = new Map<string, string>()
  for (const context of contexts) {
    for (const group of context.source_groups as ContextGroup[]) {
      if (!group.key.startsWith('inbound:')) continue
      for (const key of group.line_keys ?? []) {
        const containerId = key.split('|')[1]
        if (containerId && containerId !== 'loose' && !labels.has(containerId)) labels.set(containerId, groupTitle(group))
      }
    }
  }
  return labels
}

/**
 * Строки печатного листа Империи маршрутом вкладки «Подбор».
 * `rows` — обычные строки листа (по товару, ключ — product_id), `options` — места
 * подбора (pick-options одной поставки или всех поставок группы), `contexts` —
 * контекст печати (строки мест, приёмки, ключи мест).
 */
export function imperiyaWalkRows<T extends PrintRow>(
  rows: T[],
  options: FbsPickOptionProduct[],
  contexts: FbsPickingContext[],
): T[] {
  const cellsById = new Map<string, Cell>()
  const objectsById = new Map<string, WarehouseObject>()
  const stock = new Map<string, GoodsLine & { pickCapacity?: number }>()
  const picked: PickedMap = {}
  const placeKey = new Map<string, string>()
  const pickedByProduct = new Map<string, number>()
  const skuByProduct = new Map<string, string>()
  const receiptLabels = boxReceiptLabels(contexts)
  for (const option of options) {
    pickedByProduct.set(option.product_id, (pickedByProduct.get(option.product_id) ?? 0) + option.picked_qty)
    const sku = (option as FbsPickOptionProduct & { sku_code?: string | null }).sku_code
    if (sku) skuByProduct.set(option.product_id, sku)
    for (const location of option.locations) {
      cellsById.set(location.storage_location_id, {
        id: location.storage_location_id,
        code: location.location_code,
        barcode: location.location_code,
      })
      const loc = location as typeof location & { quantity?: number; picked?: number }
      const sources: ApiSource[] = location.sources?.length
        ? location.sources
        : [{ quantity: loc.quantity ?? location.available, available: location.available, is_loose: true, source_label: 'Россыпью', container_path: [], picked: loc.picked ?? 0 }]
      for (const source of sources) {
        let holder = cellRef(location.storage_location_id)
        for (const step of source.container_path) {
          if (!objectsById.has(step.id)) {
            // The tab sorts same-numbered boxes by the receipt appended to their label.
            const receipt = receiptLabels.get(step.id)
            objectsById.set(step.id, {
              id: step.id,
              kind: step.kind as ObjKind,
              code: receipt ? `${step.code} · ${receipt}` : step.code,
              barcode: step.code,
              holder,
            })
          }
          holder = objRef(step.id)
        }
        const quantity = source.quantity ?? source.available
        const takenHere = source.picked ?? 0
        if (quantity <= 0 && takenHere <= 0) continue
        // Групповая сборка: одно физическое место приходит от каждой поставки —
        // остаток берём один раз, снятое суммируем.
        const id = `${option.product_id}-${holder}`
        const previous = stock.get(id)
        stock.set(id, {
          id,
          productId: option.product_id,
          qty: Math.max(previous?.qty ?? 0, quantity),
          pickCapacity: Math.max(previous?.pickCapacity ?? 0, (source.available ?? quantity) + takenHere),
          holder,
        })
        picked[pickKey(option.product_id, holder)] = (picked[pickKey(option.product_id, holder)] ?? 0) + takenHere
        const innermost = source.container_path.at(-1)
        placeKey.set(holder, `${location.storage_location_id}|${innermost ? innermost.id : 'loose'}`)
      }
    }
  }
  const objects = [...objectsById.values()]
  const cells = [...cellsById.values()]
  const products: PickProduct[] = rows.map((row) => ({
    id: row.key, name: row.name, sku: skuByProduct.get(row.key) ?? '', sellerArticle: '', barcode: '', photo: '', size: row.size,
  }))
  const plan: PlanLine[] = rows.map((row) => ({ id: row.key, productId: row.key, plan: row.required }))
  const screenRows = rowsOf(plan, [...stock.values()], objects, cells, picked, products)

  // Строка места из контекста печати (прежний текст, без INB) и её приёмка.
  const byKey = new Map<string, { key: string; title: string; line: string }>()
  for (const context of contexts) {
    for (const group of context.source_groups as ContextGroup[]) {
      group.lines.forEach((line, index) => {
        const key = group.line_keys?.[index]
        if (key && !byKey.has(`${context.product_id}#${key}`)) {
          byKey.set(`${context.product_id}#${key}`, {
            key: group.key,
            title: groupTitle(group),
            line: withoutInbCode(line),
          })
        }
      })
    }
  }

  // Номер строки — номер товара в обычном листе (как раньше: по штукам).
  const positionByKey = new Map<string, string>()
  let position = 1
  for (const row of rows) {
    const from = position
    const to = from + row.required - 1
    position = to + 1
    positionByKey.set(row.key, from === to ? `${from}` : `${from}–${to}`)
  }
  const rowByKey = new Map(rows.map((row) => [row.key, row]))
  const sourceGroupsByProduct = new Map<string, NonNullable<PrintRow['sourceGroups']>>()
  const addSourceGroup = (row: T, group: NonNullable<PrintRow['sourceGroups']>[number]) => {
    const groups = sourceGroupsByProduct.get(row.key) ?? []
    const previous = groups.at(-1)
    if (previous?.key === group.key && previous.title === group.title) previous.lines.push(...group.lines)
    else groups.push(group)
    sourceGroupsByProduct.set(row.key, groups)
  }
  // Маршрут вкладки; свёрнутое «Уже подобрано» сотрудник не видит — не печатаем.
  for (const item of cellPickRowsOf(screenRows, objects, cells)) {
    if (item.kind !== 'goods' || item.alreadyPicked) continue
    const row = rowByKey.get(item.row.key)
    if (!row) continue
    if (!item.place) {
      const done = row.required > 0 && (pickedByProduct.get(row.key) ?? 0) >= row.required
      addSourceGroup(row, { key: 'none', title: done ? 'Подобрано' : 'Нет текущего остатка', lines: [] })
      continue
    }
    const found = byKey.get(`${row.key}#${placeKey.get(item.place.key) ?? ''}`)
    addSourceGroup(row, {
      key: found?.key ?? item.place.key,
      // Место без приёмки (россыпь и т.п.) подписываем так же, как на вкладке: «Без ячеек», «Ж-1-7».
      title: found ? found.title : item.place.standing,
      lines: [found?.line ?? `${item.place.standing} · ${item.place.sourceTitle}: ${item.place.qty} шт.`],
    })
  }
  // Сохраняем исходный порядок товарной ленты и одну печатную строку на товар.
  return rows.map((row) => {
    let sourceGroups = sourceGroupsByProduct.get(row.key)
    if (!sourceGroups?.length) {
      // «Уже подобрано» не печатается, но полностью подобранный товар остаётся в листе.
      const done = row.required > 0 && (pickedByProduct.get(row.key) ?? 0) >= row.required
      sourceGroups = [{ key: 'none', title: done ? 'Подобрано' : 'Нет текущего остатка', lines: [] }]
    }
    return {
      ...row,
      positionLabel: positionByKey.get(row.key),
      locations: [],
      inboundSupplies: [],
      sourceGroups,
    }
  })
}
