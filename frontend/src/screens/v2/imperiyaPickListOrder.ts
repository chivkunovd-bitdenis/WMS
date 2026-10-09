// ⛔️⛔️⛔️ КЛИЕНТСКОЕ ИСКЛЮЧЕНИЕ — ТОЛЬКО ДЛЯ «ИМПЕРИЯ ФФ» (WMS-710) ⛔️⛔️⛔️
//
// Владелец 09.10.2026: «то, что они видят на подборе, точно в этой
// последовательности у них должно печататься в листе подбора… сделай это
// фичер-тоглом только для империи львов… сам лист подбора ты не меняешь».
//
// Поэтому у Империи ФФ печатный лист подбора берёт те же строки мест, что и
// раньше (текст строк приходит с сервера, picking-context), но выстраивает их в
// составе и порядке вкладки «Подбор» (pickRows.cellPickRowsOf — та же функция,
// что рисует вкладку). Заголовок документа («П: 96 от 06.10.2026») ставится
// заново каждый раз, когда в этом порядке меняется приёмка/возврат.
// У всех остальных клиентов печать остаётся прежней байт-в-байт.
// Реестр исключений: docs/KLIENTSKIE_ISKLYUCHENIYA.md. Не переносить на других
// клиентов и не удалять без решения владельца.
//
// ВНИМАНИЕ: сборка данных вкладки ниже повторяет FfUnloadPickPage (ячейки, тара,
// остаток и снятое по местам). Меняешь там — поправь и здесь.

import { cellPickRowsOf, rowsOf, pickKey, type PickedMap } from '../ff/unload-pick/pickRows'
import { cellRef, objRef } from '../ff/unload-pick/pickStub'
import type { Cell, GoodsLine, ObjKind, PickProduct, WarehouseObject } from '../ff/unload-pick/pickStub'
import type { FbsPickOptionProduct, FbsPickingContext } from './fbsApi'

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

/** ТОЛЬКО Империя ФФ печатает лист подбора в порядке вкладки «Подбор». */
export function usesTabOrderPickList(token: string | null | undefined): boolean {
  return tenantIdFromToken(token) === IMPERIYA_FF_TENANT_ID
}

type Group = { key: string; title: string; lines: string[] }

/** «Короб №19 · INB-VSA97KFYK5YRAX · Ж-1-7: 1 шт.» → «Короб №19 · Ж-1-7: 1 шт.» */
export function withoutInbCode(line: string): string {
  return line.replace(/\s·\s*INB-[0-9A-Z]+/g, '')
}
type ContextGroup = FbsPickingContext['source_groups'][number] & { date?: string | null; line_keys?: string[] }
type ApiSource = FbsPickOptionProduct['locations'][number]['sources'][number] & { quantity?: number; picked?: number }

/**
 * Группы мест одного товара для печати Империи: строки и заголовки из контекста
 * печати, порядок и состав — как на вкладке «Подбор». Если мест нет: полностью
 * подобранный товар печатает «Подобрано», иначе — пустой список (лист покажет
 * прежнее «Нет текущего остатка»).
 */
export function imperiyaSourceGroups(
  productId: string,
  options: FbsPickOptionProduct[],
  contexts: FbsPickingContext[],
  required: number,
): Group[] {
  const cellsById = new Map<string, Cell>()
  const objectsById = new Map<string, WarehouseObject>()
  const stockByHolder = new Map<string, GoodsLine & { pickCapacity?: number }>()
  const picked: PickedMap = {}
  const placeKey = new Map<string, string>()
  let pickedTotal = 0
  for (const option of options) {
    if (option.product_id !== productId) continue
    pickedTotal += option.picked_qty
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
            objectsById.set(step.id, { id: step.id, kind: step.kind as ObjKind, code: step.code, barcode: step.code, holder })
          }
          holder = objRef(step.id)
        }
        const quantity = source.quantity ?? source.available
        const takenHere = source.picked ?? 0
        if (quantity <= 0 && takenHere <= 0) continue
        // Групповая сборка: одно и то же физическое место приходит от каждой
        // поставки — остаток берём один раз, снятое суммируем.
        const previous = stockByHolder.get(holder)
        stockByHolder.set(holder, {
          id: `${productId}-${holder}`,
          productId,
          qty: Math.max(previous?.qty ?? 0, quantity),
          pickCapacity: Math.max(previous?.pickCapacity ?? 0, (source.available ?? quantity) + takenHere),
          holder,
        })
        picked[pickKey(productId, holder)] = (picked[pickKey(productId, holder)] ?? 0) + takenHere
        const innermost = source.container_path.at(-1)
        placeKey.set(holder, `${location.storage_location_id}|${innermost ? innermost.id : 'loose'}`)
      }
    }
  }
  const objects = [...objectsById.values()]
  const cells = [...cellsById.values()]
  const product: PickProduct = { id: productId, name: '', sku: '', sellerArticle: '', barcode: '', photo: '', size: null }
  const rows = rowsOf([{ id: productId, productId, plan: required }], [...stockByHolder.values()], objects, cells, picked, [product])

  const byKey = new Map<string, { groupKey: string; title: string; line: string }>()
  for (const context of contexts) {
    if (context.product_id !== productId) continue
    for (const group of context.source_groups as ContextGroup[]) {
      const title = group.date ? `${group.title.replace(/:\s*$/, '')} от ${group.date}` : group.title
      group.lines.forEach((line, index) => {
        const key = group.line_keys?.[index]
        // Владелец 09.10.2026: «Инб убирай вообще». Империя ищет короб по «Короб №N»,
        // системный код INB-… в строке только переносит её на две. У других клиентов
        // код остаётся (например, ArtMaks ищет короб по самому коду, см. WMS-565).
        if (key && !byKey.has(key)) byKey.set(key, { groupKey: group.key, title, line: withoutInbCode(line) })
      })
    }
  }

  const out: Group[] = []
  // Состав вкладки: свёрнутый раздел «Уже подобрано» сотрудник не видит — не печатаем.
  for (const item of cellPickRowsOf(rows, objects, cells)) {
    if (item.kind !== 'goods' || !item.place || item.alreadyPicked) continue
    const place = item.place
    const found = byKey.get(placeKey.get(place.key) ?? '')
    const groupKey = found?.groupKey ?? 'unlinked'
    const title = found?.title ?? 'Без привязки к документу:'
    const line = found?.line ?? `${place.standing} · ${place.sourceTitle}: ${place.qty} шт.`
    const last = out.at(-1)
    if (last && last.key === groupKey) {
      if (!last.lines.includes(line)) last.lines.push(line)
    } else {
      out.push({ key: groupKey, title, lines: [line] })
    }
  }
  if (!out.length && required > 0 && pickedTotal >= required) {
    return [{ key: 'picked', title: 'Подобрано', lines: [] }]
  }
  return out
}
