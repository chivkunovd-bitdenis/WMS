import { describe, expect, it } from 'vitest'
import {
  applyScanResponse,
  changedActualIds,
  confirmedTouchedIds,
  markUncountedEmptyIn,
  mergeInFlightActuals,
  setActual,
} from './InventoryRows'
import type { InventoryCount, ProductNode } from './InventoryTypes'

// WMS-154: «Здесь пусто» — не удаление сущностей и не отдельный жизненный
// цикл, а простой обход поддерева выбранного места и установка `actual = 0`
// у непосчитанных строк. Ниже — минимальный документ, чтобы обходчик было на
// чём проверить, без всей серверной обвязки.

function baseCount(): InventoryCount {
  return {
    id: 'count-1',
    number: 'ИНВ-1',
    status: 'draft',
    warehouseId: 'wh-1',
    warehouseName: 'Склад',
    fill: { mode: 'all' },
    createdAt: '01.09.2026 10:00',
    createdBy: 'kladovshchik',
    postedAt: null,
    postedBy: null,
    comment: '',
    addressStorage: true,
    cells: [
      {
        id: 'cell-1',
        label: 'A-1',
        barcode: null,
        children: [
          {
            kind: 'box',
            id: 'box-1',
            code: 'K-1',
            barcode: null,
            children: [
              {
                kind: 'product',
                id: 'p-1',
                name: 'Товар А',
                sku: 'SKU-A',
                seller: 'Селлер',
                category: '—',
                barcode: '',
                wbVendorCode: null,
                wbBarcode: null,
                wbSize: null,
                photoUrl: null,
                expected: 5,
                actual: null,
              },
              {
                kind: 'product',
                id: 'p-2',
                name: 'Товар Б',
                sku: 'SKU-B',
                seller: 'Селлер',
                category: '—',
                barcode: '',
                wbVendorCode: null,
                wbBarcode: null,
                wbSize: null,
                photoUrl: null,
                expected: 3,
                actual: 3,
              },
            ],
          },
        ],
      },
    ],
    scannableCells: [],
    scannableContainers: [],
  }
}

describe('markUncountedEmptyIn', () => {
  it('ставит 0 только непосчитанным строкам внутри выбранной тары', () => {
    const { count, touched } = markUncountedEmptyIn(baseCount(), {
      kind: 'container',
      containerId: 'box-1',
    })
    const box = count.cells[0].children[0]
    if (box.kind !== 'box') throw new Error('short: expected a box')
    const productA = box.children.find((c) => c.kind === 'product' && c.id === 'p-1')
    const productB = box.children.find((c) => c.kind === 'product' && c.id === 'p-2')
    // p-1 был непосчитан → теперь 0; p-2 уже был 3 → не тронули.
    if (productA?.kind !== 'product' || productB?.kind !== 'product') {
      throw new Error('short: products missing')
    }
    expect(productA.actual).toBe(0)
    expect(productB.actual).toBe(3)
    expect(touched).toEqual(['p-1'])
  })

  it('ставит 0 всем непосчитанным по всей ячейке', () => {
    const { touched } = markUncountedEmptyIn(baseCount(), { kind: 'cell', cellId: 'cell-1' })
    expect(touched).toEqual(['p-1'])
  })

  it('без непосчитанных строк — не создаёт нового объекта документа', () => {
    const source = baseCount()
    // Все листы уже посчитаны — «Здесь пусто» ничего не меняет.
    const box = source.cells[0].children[0]
    if (box.kind !== 'box') throw new Error('short: expected a box')
    for (const child of box.children) {
      if (child.kind === 'product') child.actual = 0
    }
    const applied = markUncountedEmptyIn(source, { kind: 'cell', cellId: 'cell-1' })
    expect(applied.touched).toEqual([])
    expect(applied.count).toBe(source)
  })

  it('не найденное место — пустой touched, документ не меняется', () => {
    const source = baseCount()
    const applied = markUncountedEmptyIn(source, { kind: 'cell', cellId: 'unknown-cell' })
    expect(applied.touched).toEqual([])
    expect(applied.count).toBe(source)
  })
})

describe('WMS-155 concurrent edits', () => {
  it('preserves in-flight comment and quantities while accepting other server changes', () => {
    const sent = baseCount()
    const current = { ...setActual(sent, 'p-1', 7), comment: 'Entered while saving' }
    const server = { ...setActual(sent, 'p-2', 6), comment: 'Server comment' }
    const merged = mergeInFlightActuals(server, sent, current)
    expect(merged.comment).toBe('Entered while saving')
    expect(changedActualIds(merged, server)).toEqual(new Set(['p-1']))
  })
  it('does not reopen a previous document when its response arrives late', () => {
    const old = baseCount()
    const current = { ...baseCount(), id: 'another-document' }
    expect(mergeInFlightActuals(old, old, current)).toBe(current)
  })
  it('does not send untouched quantities from the map dialog', () => {
    const original = baseCount()
    expect(changedActualIds({ ...original, comment: 'Only a comment' }, original).size).toBe(0)
  })
})

// WMS-542, дефект приёмки 26.09.2026: экран из этого worktree показывал
// «Излишек 4» вместо серверных 6 после ответа на собственный скан оператора,
// а следующее «Сохранить» абсолютным PUT стирало два скана ВТОРОГО оператора,
// прилетевших на сервер параллельно. Причина была в двух местах разом:
// mergeInFlightActuals в обработчике ответа сравнивал с тем, что ОТПРАВИЛИ до
// скана (а скан сам локально бампает строку ещё до ответа — значит расхождение
// с отправленным верно для КАЖДОГО скана), и changedActualIds в saveSnapshot/
// save пересчитывал «тронуто» по ВСЕМ строкам документа, а не по тем, что
// реально ушли в PUT. Тесты ниже бьют именно по этим двум функциям — так, как
// просил ведущий, а не только по чистому applyScan.
/** Товары короба box-1 в baseCount(): [p-1, p-2], без риска narrow-ошибок TS. */
function boxProducts(count: InventoryCount): ProductNode[] {
  const box = count.cells[0].children[0]
  if (box.kind !== 'box') throw new Error('short: expected a box')
  return box.children.map((child) => {
    if (child.kind !== 'product') throw new Error('short: expected a product')
    return child
  })
}

describe('WMS-542: ответ на скан — после него источник истины сервер', () => {
  it('чужой скан, прилетевший на сервер параллельно, не подменяется устаревшим локальным числом', () => {
    // Оператор 1 уже досчитал p-2 до 3 и сканирует её четвёртый раз: локально
    // бампает сам себе до 4, не зная, что за это время оператор 2 (другая
    // вкладка/токен) успел сделать два своих скана этой же строки, и сервер
    // в ответе на ЭТОТ скан вернул честные 6 (2 чужих + 3 старых + 1 свой).
    const sent = baseCount() // p-2.actual = 3 — состояние ДО четвёртого скана.
    const server = setActual(sent, 'p-2', 6) // ответ record_found: истинное серверное число.
    const current = setActual(sent, 'p-2', 4) // локальный оптимистичный прирост оператора 1.
    const merged = applyScanResponse(server, current, new Set(), false)
    expect(boxProducts(merged)[1]).toMatchObject({ id: 'p-2', actual: 6 })
  })

  it('несохранённая ручная правка другой строки не затирается ответом на скан', () => {
    const sent = baseCount()
    const server = setActual(sent, 'p-2', 6)
    // p-1 оператор поправил руками на 9 и ещё не сохранил — она в touched.
    const current = setActual(setActual(sent, 'p-2', 4), 'p-1', 9)
    const merged = applyScanResponse(server, current, new Set(['p-1']), false)
    const [p1, p2] = boxProducts(merged)
    expect(p1).toMatchObject({ id: 'p-1', actual: 9 })
    expect(p2).toMatchObject({ id: 'p-2', actual: 6 })
  })

  it('комментарий, введённый оператором, не затирается ответом на скан', () => {
    const sent = baseCount()
    const server = { ...sent, comment: 'Комментарий сервера' }
    const current = { ...sent, comment: 'Ввёл, пока летел скан' }
    const merged = applyScanResponse(server, current, new Set(), true)
    expect(merged.comment).toBe('Ввёл, пока летел скан')
  })

  it('ответ из чужого документа не трогает открытый сейчас', () => {
    const server = { ...baseCount(), id: 'other-document' }
    const current = baseCount()
    expect(applyScanResponse(server, current, new Set(), false)).toBe(current)
  })
})

describe('WMS-542: пересчёт «тронуто» после PUT смотрит только на отправленное', () => {
  it('строка, бампнутая сканом мимо этого PUT, не становится тронутой только из-за разницы во времени', () => {
    // PUT ушёл по p-1 (ручная правка). Пока он летел, скан ДРУГОЙ строки p-2
    // локально поднял её с 3 до 4 — p-2 в этом PUT вообще не участвовала.
    const before = baseCount()
    const after = setActual(before, 'p-2', 4)
    const touched = confirmedTouchedIds(new Set(['p-1']), before, after)
    expect(touched.has('p-2')).toBe(false)
  })

  it('строку, которую реально отправили и сервер подтвердил без изменений, снимает из тронутых', () => {
    const before = baseCount()
    const after = before
    expect(confirmedTouchedIds(new Set(['p-1']), before, after).has('p-1')).toBe(false)
  })

  it('строку, которую поправили ещё раз, пока летел её же PUT, оставляет тронутой', () => {
    const before = baseCount()
    const after = setActual(before, 'p-1', 11)
    expect(confirmedTouchedIds(new Set(['p-1']), before, after).has('p-1')).toBe(true)
  })
})
