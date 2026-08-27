import {
  KIND_TITLE,
  UNASSIGNED_ID,
  UNASSIGNED_LABEL,
  type CellNode,
  type ContainerKind,
  type ContainerNode,
  type MapNode,
  type MovementEntry,
  type ProductNode,
  type WarehouseMapData,
} from './WarehouseMapTypes'

// Заглушечные данные и правила перекладывания для макета. Сервера в этой волне
// нет: экран должен быть виден и щупаем целиком, включая перетаскивание, иначе
// смотреть на картинку бессмысленно — половина решений про то, как оно ведёт себя
// в руке, а не про то, как выглядит на снимке.

function product(
  id: string,
  name: string,
  seller: string,
  barcode: string,
  qty: number,
): ProductNode {
  return {
    kind: 'product',
    id,
    product_id: `p-${id}`,
    name,
    seller_name: seller,
    barcode,
    photo_url: null,
    qty,
  }
}

function container(
  kind: ContainerKind,
  id: string,
  code: string,
  barcode: string | null,
  children: MapNode[],
): ContainerNode {
  return { kind, id, code, barcode, seller_name: null, qty: 0, children }
}

const GORYACHKINA = 'ИП Горячкина'
const CITYPACK = 'ООО Ситипак'
const LARIN = 'ИП Ларин'

function yartsevo(): { cells: CellNode[]; unassigned: MapNode[] } {
  const cells: CellNode[] = [
    {
      id: 'cell-a11',
      code: 'А 1.1',
      barcode: '2000000000114',
      qty: 0,
      children: [
        container('pallet', 'plt-123', 'П-000123', '2100000001236', [
          container('box', 'box-451', 'КР-000451', '2200000004516', [
            product('bal-1', 'Футболка хлопок белая, M', GORYACHKINA, '4680123456789', 24),
            product('bal-2', 'Худи оверсайз серое, L', GORYACHKINA, '4680123456796', 8),
          ]),
          container('box', 'box-452', 'КР-000452', '2200000004523', []),
        ]),
        container('box', 'box-460', 'КР-000460', '2200000004608', [
          product('bal-3', 'Кроссовки беговые, 42', CITYPACK, '4600987654321', 12),
        ]),
        product('bal-4', 'Термокружка 450 мл', LARIN, '4601122334455', 5),
      ],
    },
    {
      id: 'cell-a12',
      code: 'А 1.2',
      barcode: '2000000000121',
      qty: 0,
      children: [
        product('bal-5', 'Носки спортивные, 3 пары', CITYPACK, '4600987654338', 60),
        product('bal-6', 'Ремень кожаный, 110 см', LARIN, '4601122334462', 14),
      ],
    },
    { id: 'cell-a13', code: 'А 1.3', barcode: '2000000000138', qty: 0, children: [] },
    {
      id: 'cell-a21',
      code: 'А 2.1',
      barcode: '2000000000213',
      qty: 0,
      children: [
        container('cargo_place', 'cp-318', 'ГМ-000318', '2300000003185', [
          product('bal-7', 'Футболка хлопок белая, M', GORYACHKINA, '4680123456789', 40),
        ]),
      ],
    },
    {
      id: 'cell-b11',
      code: 'Б 1.1',
      barcode: '2000000000411',
      qty: 0,
      children: [
        container('pallet', 'plt-124', 'П-000124', '2100000001243', [
          product('bal-8', 'Кроссовки беговые, 42', CITYPACK, '4600987654321', 36),
          product('bal-9', 'Носки спортивные, 3 пары', CITYPACK, '4600987654338', 90),
        ]),
      ],
    },
  ]

  const unassigned: MapNode[] = [
    container('pallet', 'plt-130', 'П-000130', '2100000001304', [
      container('box', 'box-471', 'КР-000471', '2200000004715', [
        product('bal-10', 'Худи оверсайз серое, L', GORYACHKINA, '4680123456796', 18),
      ]),
    ]),
    container('box', 'box-470', 'КР-000470', '2200000004707', [
      product('bal-11', 'Ремень кожаный, 110 см', LARIN, '4601122334462', 7),
    ]),
    product('bal-12', 'Термокружка 450 мл', LARIN, '4601122334455', 3),
  ]

  return { cells, unassigned }
}

function himki(): { cells: CellNode[]; unassigned: MapNode[] } {
  return {
    cells: [
      {
        id: 'cell-h11',
        code: 'Х 1.1',
        barcode: '2000000001111',
        qty: 0,
        children: [
          container('box', 'box-901', 'КР-000901', '2200000009018', [
            product('bal-20', 'Носки спортивные, 3 пары', CITYPACK, '4600987654338', 30),
          ]),
        ],
      },
      { id: 'cell-h12', code: 'Х 1.2', barcode: '2000000001128', qty: 0, children: [] },
    ],
    unassigned: [product('bal-21', 'Термокружка 450 мл', LARIN, '4601122334455', 11)],
  }
}

const JOURNAL: MovementEntry[] = [
  {
    id: 'mv-1',
    at: '2026-08-27T06:12:00Z',
    actor_name: 'Смирнова Ольга',
    subject: 'Футболка хлопок белая, M',
    qty: 40,
    from_label: UNASSIGNED_LABEL,
    to_label: 'Грузоместо ГМ-000318',
  },
  {
    id: 'mv-2',
    at: '2026-08-27T06:40:00Z',
    actor_name: 'Смирнова Ольга',
    subject: 'Грузоместо ГМ-000318',
    qty: 40,
    from_label: UNASSIGNED_LABEL,
    to_label: 'Ячейка А 2.1',
  },
  {
    id: 'mv-3',
    at: '2026-08-27T07:05:00Z',
    actor_name: 'Панов Игорь',
    subject: 'Короб КР-000451',
    qty: 32,
    from_label: 'Ячейка А 1.2',
    to_label: 'Палета П-000123',
  },
  {
    id: 'mv-4',
    at: '2026-08-27T08:31:00Z',
    actor_name: 'Панов Игорь',
    subject: 'Кроссовки беговые, 42',
    qty: 36,
    from_label: UNASSIGNED_LABEL,
    to_label: 'Палета П-000124',
  },
  {
    id: 'mv-5',
    at: '2026-08-27T09:18:00Z',
    actor_name: 'Смирнова Ольга',
    subject: 'Термокружка 450 мл',
    qty: 5,
    from_label: 'Короб КР-000460',
    to_label: 'Ячейка А 1.1',
  },
  {
    id: 'mv-6',
    at: '2026-08-27T10:02:00Z',
    actor_name: 'Кузьмин Артём',
    subject: 'Ремень кожаный, 110 см',
    qty: 7,
    from_label: 'Ячейка А 1.2',
    to_label: 'Короб КР-000470',
  },
]

export function stubData(warehouseId: string): WarehouseMapData {
  const source = warehouseId === 'wh-himki' ? himki() : yartsevo()
  return normalize({
    warehouses: [
      { id: 'wh-yartsevo', name: 'Ярцево' },
      { id: 'wh-himki', name: 'Химки' },
    ],
    cells: source.cells,
    unassigned: source.unassigned,
    journal: warehouseId === 'wh-himki' ? JOURNAL.slice(0, 2) : JOURNAL,
  })
}

export function emptyStubData(): WarehouseMapData {
  return {
    warehouses: [{ id: 'wh-yartsevo', name: 'Ярцево' }],
    cells: [],
    unassigned: [],
    journal: [],
  }
}

export function noWarehousesStubData(): WarehouseMapData {
  return { warehouses: [], cells: [], unassigned: [], journal: [] }
}

// --- пересчёт итогов -------------------------------------------------------

function sellersOf(node: MapNode, into: Set<string>) {
  if (node.kind === 'product') {
    if (node.seller_name) into.add(node.seller_name)
    return
  }
  node.children.forEach((child) => sellersOf(child, into))
}

function normalizeNode(node: MapNode): MapNode {
  if (node.kind === 'product') return node
  const children = node.children.map(normalizeNode)
  const sellers = new Set<string>()
  children.forEach((child) => sellersOf(child, sellers))
  return {
    ...node,
    children,
    qty: children.reduce((sum, child) => sum + child.qty, 0),
    // Подпись селлера честна только когда внутри один селлер: смешанный короб
    // с чьим-то одним именем врал бы прямо в строке.
    seller_name: sellers.size === 1 ? [...sellers][0]! : null,
  }
}

export function normalize(data: WarehouseMapData): WarehouseMapData {
  return {
    ...data,
    cells: data.cells.map((cell) => {
      const children = cell.children.map(normalizeNode)
      return { ...cell, children, qty: children.reduce((sum, child) => sum + child.qty, 0) }
    }),
    unassigned: data.unassigned.map(normalizeNode),
  }
}

// --- перекладывание --------------------------------------------------------

/** Ключ строки — это путь: корень (ячейка или «Без ячеек») и дальше вложения. */
function splitKey(key: string): { rootId: string; path: string[] } {
  const parts = key.split('/')
  return { rootId: parts[0]!, path: parts.slice(1) }
}

function mapRoot(
  data: WarehouseMapData,
  rootId: string,
  updater: (children: MapNode[]) => MapNode[],
): WarehouseMapData {
  if (rootId === UNASSIGNED_ID) {
    return { ...data, unassigned: updater(data.unassigned) }
  }
  return {
    ...data,
    cells: data.cells.map((cell) =>
      cell.id === rootId ? { ...cell, children: updater(cell.children) } : cell,
    ),
  }
}

type Taken = { children: MapNode[]; taken: MapNode | null }

function takeFrom(children: MapNode[], path: string[], qty: number): Taken {
  const [head, ...rest] = path
  if (head === undefined) {
    return { children, taken: null }
  }
  if (rest.length > 0) {
    let taken: MapNode | null = null
    const next = children.map((child) => {
      if (child.id !== head || child.kind === 'product') return child
      const result = takeFrom(child.children, rest, qty)
      taken = result.taken
      return { ...child, children: result.children }
    })
    return { children: next, taken }
  }

  const target = children.find((child) => child.id === head) ?? null
  if (!target) {
    return { children, taken: null }
  }
  // Частичное снятие бывает только у товара: короб и палета переезжают целиком.
  if (target.kind === 'product' && qty > 0 && qty < target.qty) {
    return {
      children: children.map((child) =>
        child.id === head && child.kind === 'product' ? { ...child, qty: child.qty - qty } : child,
      ),
      taken: { ...target, id: `${target.id}-part-${Date.now()}`, qty },
    }
  }
  return { children: children.filter((child) => child.id !== head), taken: target }
}

function putInto(children: MapNode[], path: string[], node: MapNode): MapNode[] {
  const [head, ...rest] = path
  if (head === undefined) {
    // Такой же товар на том же месте складывается в одну строку: две строки
    // одного SKU в одной ячейке оператор читает как ошибку системы.
    if (node.kind === 'product') {
      const twin = children.find(
        (child) => child.kind === 'product' && child.product_id === node.product_id,
      )
      if (twin && twin.kind === 'product') {
        return children.map((child) =>
          child === twin ? { ...twin, qty: twin.qty + node.qty } : child,
        )
      }
    }
    return [...children, node]
  }
  return children.map((child) => {
    if (child.id !== head || child.kind === 'product') return child
    return { ...child, children: putInto(child.children, rest, node) }
  })
}

function journalEntry(
  subject: string,
  qty: number | null,
  fromLabel: string,
  toLabel: string,
  actor: string,
): MovementEntry {
  return {
    id: `mv-${Date.now()}-${Math.round(Math.random() * 1000)}`,
    at: new Date().toISOString(),
    actor_name: actor,
    subject,
    qty,
    from_label: fromLabel,
    to_label: toLabel,
  }
}

export type StubIntent = {
  reason: 'move' | 'takeOff' | 'disband'
  rowKey: string
  rowTitle: string
  fromLabel: string
  toKey: string
  toLabel: string
}

export function applyIntent(
  data: WarehouseMapData,
  intent: StubIntent,
  qty: number,
  actor: string,
): WarehouseMapData {
  const source = splitKey(intent.rowKey)

  if (intent.reason === 'disband') {
    let contents: MapNode[] = []
    let next = mapRoot(data, source.rootId, (children) => {
      const result = takeFrom(children, source.path, 0)
      if (result.taken && result.taken.kind !== 'product') {
        contents = result.taken.children
      }
      return result.children
    })
    next = { ...next, unassigned: [...next.unassigned, ...contents] }
    return normalize({
      ...next,
      journal: [
        journalEntry(intent.rowTitle, null, intent.fromLabel, UNASSIGNED_LABEL, actor),
        ...next.journal,
      ],
    })
  }

  let moved: MapNode | null = null
  let next = mapRoot(data, source.rootId, (children) => {
    const result = takeFrom(children, source.path, qty)
    moved = result.taken
    return result.children
  })
  const takenNode = moved as MapNode | null
  if (!takenNode) {
    return data
  }

  const destination = splitKey(intent.toKey)
  next = mapRoot(next, destination.rootId, (children) =>
    putInto(children, destination.path, takenNode),
  )

  return normalize({
    ...next,
    journal: [
      journalEntry(intent.rowTitle, takenNode.qty, intent.fromLabel, intent.toLabel, actor),
      ...next.journal,
    ],
  })
}

export function addCell(data: WarehouseMapData, code: string): WarehouseMapData {
  return {
    ...data,
    cells: [
      ...data.cells,
      {
        id: `cell-${code.replace(/\s+/g, '-').toLowerCase()}`,
        code,
        barcode: `29${String(Date.now()).slice(-11)}`,
        qty: 0,
        children: [],
      },
    ],
  }
}

export function addWarehouse(data: WarehouseMapData, name: string): WarehouseMapData {
  return {
    ...data,
    warehouses: [...data.warehouses, { id: `wh-${Date.now()}`, name }],
  }
}

/** Подпись контейнера для журнала — та же, что и в дереве. */
export function containerTitle(kind: ContainerKind, code: string): string {
  return `${KIND_TITLE[kind]} ${code}`
}
