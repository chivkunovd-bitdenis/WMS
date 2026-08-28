import { isCellRef, refId } from '../sorting-objects/objectsStub'
import {
  KIND_TITLE,
  cellRef,
  objRef,
  productById,
  STOCK,
  type Cell,
  type GoodsLine,
  type Holder,
  type ObjKind,
  type PickProduct,
  type PlanLine,
  type WarehouseObject,
} from './pickStub'

// Строки экрана подбора. Одна строка внешней таблицы — один товар из плана
// отгрузки, внутри неё списком идут места, откуда его можно снять.
//
// Раздел мест — плоский список, а не дерево: владелец посмотрел раскрывашку со
// ступенькой отступа и структурными строками и отменил её дословно (28.08):
// «у тебя раздел — россыпь, короба, паллета, каждый на своей ячейке, вот
// откуда я выбрал оттуда и взял». Каждая строка места — это реальное место, с
// которого физически можно снять товар, и у каждой есть число и поле; строк
// без числа и без поля («ячейка вообще», «палета целиком, если в ней есть
// короб») здесь нет — считать в них нечего.

/** Сколько снято по каждому месту: ключ — товар + место. */
export type PickedMap = Record<string, number>

export const pickKey = (productId: string, placeKey: string) => `${productId}|${placeKey}`

/** Чем именно является место: россыпь на ячейке или вид тары, в которой лежит товар. */
export type PlaceKind = 'loose' | ObjKind

export type PickPlace = {
  /** Ссылка на то, что физически держит товар (ячейка или объект): она же ключ строки места. */
  key: string
  holder: Holder
  /** «А 1.1 · палета П-000131 · короб КР-000472» — полный адрес одной строкой, для сканера и истории. */
  label: string
  /** Россыпь на ячейке или вид тары — определяет иконку и текст «Откуда снимаем». */
  kind: PlaceKind
  /** «Россыпью», «Палета П-000131», «Короб КР-000472», «Грузоместо ГМ-000318» — что снимаем. */
  sourceTitle: string
  /** ШК того, что физически сканируешь на этом месте: тара, а если её нет — сама ячейка. */
  barcode: string | null
  /** «А 1.1», «А 1.1 · на палете П-000131», «Без ячейки» — где это место стоит. */
  standing: string
  /** Ячейка есть или объект стоит без ячейки. Нужно для порядка сортировки. */
  cellCode: string | null
  /** На сколько ступеней это место вложено: короб на палете — одна ступень. */
  depth: number
  /** Сколько физически лежит. */
  qty: number
  /** Сколько уже снято в этом подборе. */
  picked: number
  /** Сколько ещё можно снять отсюда. */
  left: number
}

export type PickRow = {
  key: string
  product: PickProduct
  plan: number
  picked: number
  left: number
  places: PickPlace[]
}

/**
 * Путь от места наружу: в чём оно лежит и на чём стоит, снизу вверх.
 *
 * Ячейка в цепочке всегда последняя ступень и всегда одна. Если её нет — объект
 * стоит без ячейки; это не ошибка данных, а обычное состояние склада: палета
 * приехала и стоит в проходе, товар с неё снимают точно так же.
 */
export function chainOf(
  holder: Holder,
  objects: WarehouseObject[],
  cells: Cell[],
): { cell: Cell | null; chain: WarehouseObject[] } {
  const chain: WarehouseObject[] = []
  let cursor = holder
  while (cursor) {
    if (isCellRef(cursor)) {
      return { cell: cells.find((one) => one.id === refId(cursor!)) ?? null, chain }
    }
    const object = objects.find((one) => one.id === refId(cursor!))
    if (!object) break
    chain.unshift(object)
    cursor = object.holder
  }
  return { cell: null, chain }
}

/**
 * Адрес места одной строкой: ячейка, потом объекты снаружи внутрь.
 *
 * «Без ячейки» пишется у самого внешнего объекта, а не отдельным словом впереди:
 * кладовщику важно, что искать надо палету П-000140, а не то, что у неё нет
 * адреса на полке.
 */
export function placeLabel(holder: Holder, objects: WarehouseObject[], cells: Cell[]): string {
  const { cell, chain } = chainOf(holder, objects, cells)
  const parts = chain.map((one, index) => {
    const name = `${KIND_TITLE[one.kind].toLowerCase()} ${one.code}`
    return !cell && index === 0 ? `${name} (без ячейки)` : name
  })
  if (cell) parts.unshift(cell.code)
  if (parts.length === 0) return 'Без ячейки'
  return parts.join(' · ')
}

/** Как назвать промежуточный объект в колонке «Где стоит»: предлог и падеж — не именительный. */
const PARENT_PHRASE: Record<ObjKind, (code: string) => string> = {
  pallet: (code) => `на палете ${code}`,
  box: (code) => `в коробе ${code}`,
  cargo_place: (code) => `в грузоместе ${code}`,
}

/**
 * Что дополнительно лежит на складе — сверх того, что уже описано в
 * `pickStub.ts`. Заглушку `pickStub.ts` эта задача не правит (она вне границ
 * задачи 20260828, поправка владельца): нужные для проверки случаи заводятся
 * здесь же, как уже делалось в варианте Б (`unload-pick-2/routeRows.ts`).
 */
const EXTRA_STOCK: GoodsLine[] = [
  // Футболка лежит ещё и россыпью прямо на ячейке А 1.1 — вместе с уже
  // описанными в стабе местами (палета, короб на палете, короб без ячейки)
  // это ровно тот набор мест, который проверяет задача 20260828.
  { id: 'x-1', productId: 'p-tshirt', qty: 6, holder: cellRef('c-a11') },
  // Худи лежит тремя разными способами сразу: россыпью на полке, в коробе на
  // палете (уже в стабе) и в грузоместе. Владелец прямо просил показать
  // случай «часть на полке, часть в коробе, часть в грузоместе» — раз в
  // заглушке его не было, он заведён здесь (28.08, поправка).
  { id: 'x-2', productId: 'p-hoodie', qty: 8, holder: cellRef('c-a13') },
  { id: 'x-3', productId: 'p-hoodie', qty: 5, holder: objRef('cp-318') },
]

/** Весь остаток склада для экрана подбора: заглушка плюс проверочные места (см. `EXTRA_STOCK`). */
export const ALL_STOCK: GoodsLine[] = [...STOCK, ...EXTRA_STOCK]

/**
 * Места, откуда можно снять этот товар.
 *
 * Место — всегда самый нижний объект, в котором товар лежит: если он в коробе
 * на палете, то место — короб, а палета остаётся частью адреса. Один товар
 * может лежать сразу в нескольких коробах, в коробе и в грузоместе, россыпью
 * и в таре — сочетаний сколько угодно, и список показывает их все, без
 * группировки и без свёртки в одну строку. Порядок такой же, как оператор
 * ходит: сначала то, что стоит на ячейках (по коду ячейки, и внутри ячейки —
 * от неглубокого к вложенному), потом то, что без ячеек.
 */
export function placesOf(
  productId: string,
  stock: GoodsLine[],
  objects: WarehouseObject[],
  cells: Cell[],
  picked: PickedMap,
): PickPlace[] {
  const byHolder = new Map<string, number>()
  for (const line of stock) {
    if (line.productId !== productId) continue
    const key = line.holder ?? 'none'
    byHolder.set(key, (byHolder.get(key) ?? 0) + line.qty)
  }
  const decorated: { place: PickPlace; depth: number }[] = []
  for (const [key, qty] of byHolder) {
    const holder: Holder = key === 'none' ? null : key
    const { cell, chain } = chainOf(holder, objects, cells)
    // Место — самый нижний объект в цепочке (последний перед ячейкой). Если
    // цепочка пуста, товар лежит прямо в ячейке (или вовсе без адреса) — это
    // и есть «Россыпью».
    const object = chain.length > 0 ? chain[chain.length - 1] : null
    const parents = chain.slice(0, -1)
    const kind: PlaceKind = object ? object.kind : 'loose'
    const sourceTitle = object ? `${KIND_TITLE[object.kind]} ${object.code}` : 'Россыпью'
    const barcode = object ? object.barcode : (cell?.barcode ?? null)
    const parentPhrases = parents.map((one) => PARENT_PHRASE[one.kind](one.code))
    const standing = cell
      ? [cell.code, ...parentPhrases].join(' · ')
      : parentPhrases.length > 0
        ? `${parentPhrases.join(' · ')} (без ячейки)`
        : 'Без ячейки'
    const taken = picked[pickKey(productId, key)] ?? 0
    decorated.push({
      depth: chain.length,
      place: {
        key,
        holder,
        depth: 0,
        label: placeLabel(holder, objects, cells),
        kind,
        sourceTitle,
        barcode,
        standing,
        cellCode: cell?.code ?? null,
        qty,
        picked: taken,
        left: Math.max(0, qty - taken),
      },
    })
  }
  // Ступенька рисуется только под тем родителем, который сам есть в списке.
  // У худи короб стоит на палете, но самой палеты в списке нет — этого товара на
  // ней не лежит. Без этой поправки короб уезжал вправо, а направляющая указывала
  // в пустоту, и строка читалась как сломанная.
  const visible = new Set(decorated.map((entry) => entry.place.key))
  for (const entry of decorated) {
    let seen = 0
    let cursor: Holder = entry.place.holder
    while (cursor && !isCellRef(cursor)) {
      const object = objects.find((one) => one.id === refId(cursor as string))
      if (!object) break
      cursor = object.holder
      if (cursor && !isCellRef(cursor) && visible.has(cursor)) seen += 1
    }
    entry.place.depth = seen
  }

  return decorated
    .sort((a, b) => {
      const aCell = a.place.cellCode
      const bCell = b.place.cellCode
      if (Boolean(aCell) !== Boolean(bCell)) return aCell ? -1 : 1
      if (aCell && bCell && aCell !== bCell) return aCell.localeCompare(bCell, 'ru')
      return a.place.label.localeCompare(b.place.label, 'ru')
    })
    .map((entry) => entry.place)
}

export function rowsOf(
  plan: PlanLine[],
  stock: GoodsLine[],
  objects: WarehouseObject[],
  cells: Cell[],
  picked: PickedMap,
): PickRow[] {
  return plan.map((line) => {
    const places = placesOf(line.productId, stock, objects, cells, picked)
    const taken = places.reduce((sum, place) => sum + place.picked, 0)
    return {
      key: line.id,
      product: productById(line.productId),
      plan: line.plan,
      picked: taken,
      left: Math.max(0, line.plan - taken),
      places,
    }
  })
}

/** Лежит ли место внутри отсканированного источника (или это он сам). */
export function isInside(holder: Holder, source: string, objects: WarehouseObject[]): boolean {
  let cursor = holder
  while (cursor) {
    if (cursor === source) return true
    if (isCellRef(cursor)) return false
    const object = objects.find((one) => one.id === refId(cursor!))
    if (!object) return false
    cursor = object.holder
  }
  return false
}

/**
 * Что из этого товара лежит внутри отсканированного места.
 *
 * Пикнули палету — сюда попадёт и то, что лежит на ней россыпью, и то, что
 * лежит в коробе на этой палете. Разбираться, из чего именно брать, экран будет
 * только если таких мест окажется больше одного.
 */
export function placesUnder(
  places: PickPlace[],
  source: string | null,
  objects: WarehouseObject[],
): PickPlace[] {
  const available = places.filter((place) => place.left > 0)
  if (!source) return available
  return available.filter((place) => isInside(place.holder, source, objects))
}

/** Строки плана, у которых есть хоть одно место внутри отсканированного объекта. */
export function rowsWithin(rows: PickRow[], source: string, objects: WarehouseObject[]): PickRow[] {
  return rows.filter((row) => row.places.some((place) => isInside(place.holder, source, objects)))
}
