import type { AlreadyAt, SortCell, SortProduct } from './sortingStub'

// Заглушка «настоящего» склада: три склада, сотни ячеек, две сотни строк товара.
// Маленькая заглушка на пять позиций отвечает на вопрос «как это выглядит», а
// эта — на вопрос «работает ли это, когда работы много». Второе важнее: экран
// ломается не на пяти строках, а на двухстах.

export type BigWarehouse = { id: string; name: string; racks: string[]; sides: number; positions: number }

export const WAREHOUSES: BigWarehouse[] = [
  { id: 'wh-yartsevo', name: 'Ярцево', racks: ['А', 'Б', 'В', 'Г', 'Д'], sides: 2, positions: 14 },
  { id: 'wh-himki', name: 'Химки', racks: ['Х', 'Ц'], sides: 2, positions: 10 },
  { id: 'wh-podolsk', name: 'Подольск', racks: ['П', 'Р', 'С'], sides: 1, positions: 12 },
]

const SELLERS = ['ИП Горячкина', 'ООО Ситипак', 'ИП Ларин', 'ООО Северный Путь', 'ИП Дьяченко']

const GOODS: Array<[string, string, string]> = [
  ['Футболка хлопок', 'Футболки', 'ФБ'],
  ['Худи оверсайз', 'Худи и свитшоты', 'ХД'],
  ['Кроссовки беговые', 'Кроссовки', 'КР'],
  ['Носки спортивные', 'Носки', 'НС'],
  ['Термокружка', 'Посуда', 'ТК'],
  ['Ремень кожаный', 'Ремни', 'РМ'],
  ['Джинсы прямые', 'Джинсы', 'ДЖ'],
  ['Куртка ветровка', 'Верхняя одежда', 'КВ'],
  ['Шапка вязаная', 'Головные уборы', 'ШП'],
  ['Рюкзак городской', 'Рюкзаки', 'РЗ'],
]

const SIZES = ['XS', 'S', 'M', 'L', 'XL', '38', '40', '42', '44', '46']
const TONES: Array<[string, string]> = [
  ['#e2e8f0', '#5b21b6'],
  ['#ede9fe', '#4c1d95'],
  ['#e0f2fe', '#0369a1'],
  ['#dcfce7', '#15803d'],
  ['#fef3c7', '#a16207'],
  ['#fee2e2', '#9f1239'],
]

function photo(background: string, accent: string, letters: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
    <rect width="240" height="240" fill="${background}"/>
    <circle cx="120" cy="96" r="54" fill="${accent}" opacity="0.85"/>
    <rect x="42" y="162" width="156" height="42" rx="12" fill="${accent}" opacity="0.55"/>
    <text x="120" y="116" font-family="Inter, sans-serif" font-size="52" font-weight="700"
      fill="${background}" text-anchor="middle">${letters}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg.replace(/\s+/g, ' '))}`
}

/** Псевдослучайное, но одинаковое от запуска к запуску: макет должен выглядеть одинаково. */
function rnd(seed: number): number {
  const value = Math.sin(seed * 12.9898) * 43758.5453
  return value - Math.floor(value)
}

export function bigCells(warehouseId: string): SortCell[] {
  const warehouse = WAREHOUSES.find((one) => one.id === warehouseId) ?? WAREHOUSES[0]!
  const cells: SortCell[] = []
  let seed = warehouse.name.length * 17
  for (const rack of warehouse.racks) {
    for (let side = 1; side <= warehouse.sides; side += 1) {
      for (let position = 1; position <= warehouse.positions; position += 1) {
        seed += 1
        const busy = rnd(seed) > 0.45
        const good = GOODS[Math.floor(rnd(seed * 3) * GOODS.length)]!
        cells.push({
          id: `${warehouse.id}-${rack}-${side}-${position}`,
          code: `${rack} ${side}.${position}`,
          barcode: `29${String(1000000000 + Math.floor(rnd(seed * 7) * 8999999999)).slice(0, 11)}`,
          occupied: busy
            ? [{ name: `${good[0]} ${SIZES[Math.floor(rnd(seed * 11) * SIZES.length)]}`, qty: 4 + Math.floor(rnd(seed * 13) * 180) }]
            : [],
        })
      }
    }
  }
  return cells
}

export function bigProducts(cells: SortCell[]): SortProduct[] {
  const products: SortProduct[] = []
  const busyCells = cells.filter((cell) => cell.occupied.length > 0)
  for (let index = 0; index < 214; index += 1) {
    const good = GOODS[index % GOODS.length]!
    const size = SIZES[Math.floor(rnd(index * 5) * SIZES.length)]!
    const tone = TONES[index % TONES.length]!
    const seller = SELLERS[Math.floor(rnd(index * 3) * SELLERS.length)]!
    const boxNumber = Math.floor(rnd(index * 9) * 14)
    // Подсказка «уже лежит» есть примерно у двух третей строк — как на живом
    // складе, где новинок всегда меньше, чем повторных поставок.
    const alreadyAt: AlreadyAt[] =
      rnd(index * 19) > 0.34 && busyCells.length > 0
        ? [
            {
              cellId: busyCells[Math.floor(rnd(index * 23) * busyCells.length)]!.id,
              code: busyCells[Math.floor(rnd(index * 23) * busyCells.length)]!.code,
              qty: 6 + Math.floor(rnd(index * 29) * 140),
            },
          ]
        : []
    products.push({
      id: `p-${index}`,
      name: `${good[0]} ${size}`,
      sku: `${good[2]}-${1000 + index}`,
      seller,
      barcode: `46${String(80000000000 + index * 7919).slice(0, 11)}`,
      photo: photo(tone[0], tone[1], good[2]),
      source: boxNumber === 0 ? { kind: 'loose', label: 'Россыпь' } : { kind: 'box', label: `Короб №${boxNumber}` },
      accepted: 4 + Math.floor(rnd(index * 31) * 120),
      alreadyAt,
    })
  }
  return products
}
