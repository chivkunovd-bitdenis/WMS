import type {
  CellNode,
  CountListItem,
  InventoryCount,
  InventoryNode,
  ProductNode,
} from './InventoryTypes'
import { totals } from './InventoryRows'

// Данные для превью. Сервера под экраном ещё нет: цифры выдуманы, но форма и
// объём взяты как на живом складе — ячейка с палетой, короб внутри палеты,
// грузоместо и товар россыпью рядом.

let seq = 0
const nextId = () => `n${(seq += 1)}`

function product(
  name: string,
  sku: string,
  seller: string,
  category: string,
  barcode: string,
  expected: number,
  actual: number | null = null,
  expectedNow?: number,
): ProductNode {
  return {
    kind: 'product',
    id: nextId(),
    productId: `product-${sku}`,
    name,
    sku,
    seller,
    category,
    barcode,
    photoUrl: null,
    expected,
    actual,
    ...(expectedNow === undefined ? {} : { expectedNow }),
  }
}

function box(code: string, barcode: string, children: InventoryNode[]): InventoryNode {
  return { kind: 'box', id: nextId(), code, barcode, children }
}

function pallet(code: string, children: InventoryNode[]): InventoryNode {
  // Штрихкод у палеты есть: её тоже пикают, чтобы открыть и считать внутрь.
  return { kind: 'pallet', id: nextId(), code, barcode: `21000000${code.slice(-4)}`, children }
}

function cargoPlace(code: string, barcode: string, children: InventoryNode[]): InventoryNode {
  return { kind: 'cargo_place', id: nextId(), code, barcode, children }
}

function cell(label: string, children: InventoryNode[]): CellNode {
  return { id: nextId(), label, children }
}

const LOVIANA = 'ООО Ловиана'
const FASHION = 'ООО Фэшн'
const RYABOV = 'ИП Рябов'

export function stubCount(): InventoryCount {
  seq = 0
  return {
    id: 'inv-124',
    number: 'ИНВ-000124',
    status: 'draft',
    warehouseName: 'Ярцево',
    fill: { mode: 'filters', seller: null, category: null },
    createdAt: '28.08.2026 14:20',
    createdBy: 'Смирнова Ольга',
    postedAt: null,
    postedBy: null,
    comment: '',
    addressStorage: true,
    cells: [
      cell('А 1.1', [
        pallet('П-000117', [
          box('К-004512', '4680001112223', [
            product('Платье миди «Верона», чёрное, 44', 'LOV-VER-44-BK', LOVIANA, 'Платья', '4680012345671', 24, 24),
            product('Платье миди «Верона», чёрное, 46', 'LOV-VER-46-BK', LOVIANA, 'Платья', '4680012345672', 18, 15),
            product('Платье миди «Верона», синее, 44', 'LOV-VER-44-BL', LOVIANA, 'Платья', '4680012345673', 12, null),
          ]),
          box('К-004513', '4680001112224', [
            product('Жакет «Осло», бежевый, 46', 'LOV-OSL-46-BG', LOVIANA, 'Верхняя одежда', '4680012345681', 9, 9),
            product('Жакет «Осло», бежевый, 48', 'LOV-OSL-48-BG', LOVIANA, 'Верхняя одежда', '4680012345682', 7, null),
          ]),
        ]),
        product('Ремень кожаный «Бари», 95', 'FSH-BAR-95', FASHION, 'Аксессуары', '4680098765431', 30, 33),
      ]),
      cell('А 1.2', [
        box('К-004601', '4680001113001', [
          product('Брюки «Тоскана», графит, 46', 'FSH-TOS-46-GR', FASHION, 'Брюки', '4680098765441', 21, null),
          product('Брюки «Тоскана», графит, 48', 'FSH-TOS-48-GR', FASHION, 'Брюки', '4680098765442', 16, 16),
          // Остаток уехал после наполнения: заказ успели отгрузить.
          product('Брюки «Тоскана», чёрный, 46', 'FSH-TOS-46-BK', FASHION, 'Брюки', '4680098765443', 14, 12, 11),
        ]),
        cargoPlace('ГМ-000042', '4680001114001', [
          product('Шарф «Комо», серый', 'FSH-COM-GY', FASHION, 'Аксессуары', '4680098765451', 40, null),
        ]),
      ]),
      cell('Б 2.4', [
        product('Носки «Порто», 27, чёрные', 'RYB-POR-27-BK', RYABOV, 'Носки', '4600011122233', 120, 0),
        product('Носки «Порто», 29, чёрные', 'RYB-POR-29-BK', RYABOV, 'Носки', '4600011122234', 85, null),
        box('К-004777', '4680001115001', [
          product('Футболка «Ливорно», белая, M', 'RYB-LIV-M-WH', RYABOV, 'Футболки', '4600011122241', 54, 54),
          product('Футболка «Ливорно», белая, L', 'RYB-LIV-L-WH', RYABOV, 'Футболки', '4600011122242', 47, 47),
        ]),
      ]),
      cell('Без ячеек', [
        product('Кардиган «Ареццо», молоко, 44', 'LOV-ARE-44-ML', LOVIANA, 'Верхняя одежда', '4680012345691', 6, null),
      ]),
    ],
  }
}

/** Документ, наполненный по одному коробу: вход со значка на карте склада. */
export function stubCountForBox(): InventoryCount {
  const full = stubCount()
  const cellA = full.cells[0]
  const pal = cellA.children.find((n) => n.kind === 'pallet')
  const firstBox = pal && pal.kind === 'pallet' ? pal.children[0] : undefined
  return {
    ...full,
    id: 'inv-125',
    number: 'ИНВ-000125',
    fill: { mode: 'object', objectLabel: 'Короб К-004512' },
    cells: firstBox ? [{ id: cellA.id, label: cellA.label, children: [firstBox] }] : [],
  }
}

export function emptyCount(): InventoryCount {
  return { ...stubCount(), cells: [] }
}

/** Арендатор без адресного хранения: ячеек нет, есть только тара и товар. */
export function noAddressCount(): InventoryCount {
  const base = stubCount()
  return { ...base, id: 'inv-126', number: 'ИНВ-000126', addressStorage: false }
}

export function postedCount(): InventoryCount {
  const base = stubCount()
  return {
    ...base,
    id: 'inv-119',
    number: 'ИНВ-000119',
    status: 'posted',
    postedAt: '27.08.2026 19:04',
    postedBy: 'Смирнова Ольга',
    comment: 'Плановый пересчёт зоны А',
  }
}

function listItem(count: InventoryCount): CountListItem {
  const t = totals(count)
  const fillLabel =
    count.fill.mode === 'all'
      ? 'Весь склад'
      : count.fill.mode === 'object'
        ? count.fill.objectLabel
        : [count.fill.seller, count.fill.category].filter(Boolean).join(', ') || 'По фильтрам'
  return {
    id: count.id,
    number: count.number,
    status: count.status,
    warehouseName: count.warehouseName,
    fillLabel,
    createdAt: count.createdAt,
    createdBy: count.createdBy,
    lines: t.lines,
    counted: t.counted,
    discrepancies: t.discrepancies,
    surplus: t.surplus,
    shortage: t.shortage,
  }
}

export function stubList(): CountListItem[] {
  const draft = listItem(stubCount())
  const byBox = listItem(stubCountForBox())
  const posted = listItem(postedCount())
  return [
    draft,
    { ...byBox, createdAt: '28.08.2026 12:05', createdBy: 'Ким Анна' },
    { ...posted, createdAt: '27.08.2026 18:10' },
    {
      id: 'inv-118',
      number: 'ИНВ-000118',
      status: 'posted',
      warehouseName: 'Ярцево',
      fillLabel: 'ООО Ловиана',
      createdAt: '25.08.2026 09:40',
      createdBy: 'Ким Анна',
      lines: 212,
      counted: 212,
      discrepancies: 7,
      surplus: 4,
      shortage: 19,
    },
    {
      id: 'inv-117',
      number: 'ИНВ-000117',
      status: 'cancelled',
      warehouseName: 'Ярцево',
      fillLabel: 'Короб К-004310',
      createdAt: '24.08.2026 16:22',
      createdBy: 'Смирнова Ольга',
      lines: 8,
      counted: 0,
      discrepancies: 0,
      surplus: 0,
      shortage: 0,
    },
  ]
}
