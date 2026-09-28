import { describe, expect, it } from 'vitest'
import { containerTargetCell, selectionPlacement } from './FfInventoryCountScreen'
import type { InvRow } from './InventoryRows'
import { NOTHING_OPEN, type ScanOpenPlace } from './InventoryScan'

// selectionPlacement переводит строку, на которой стоит выделение (задача 2),
// в адрес для «Добавить товар» (задача 3). Постановка владельца прямо
// описывает только короб (п. 6) и «выделения не было» (п. 7) — ячейку мы ведём
// тем же путём, что и находка со сканера с открытой ячейкой без тары; это
// решение зафиксировано здесь тестом, а не только в docstring.

function row(overrides: Partial<InvRow> = {}): InvRow {
  return {
    key: 'box:11111111-1111-4111-8111-111111111111',
    id: '11111111-1111-4111-8111-111111111111',
    kind: 'box',
    depth: 1,
    title: 'Короб КР-1',
    seller: null,
    category: null,
    barcode: null,
    wbVendorCode: null,
    wbBarcode: null,
    wbSize: null,
    photoUrl: null,
    expected: 0,
    actual: null,
    delta: null,
    surplus: 0,
    shortage: 0,
    mismatchLeaves: 0,
    leaves: 0,
    countedLeaves: 0,
    expandable: false,
    expanded: false,
    empty: true,
    parentKey: 'root',
    stale: false,
    ...overrides,
  }
}

describe('selectionPlacement', () => {
  it('без выделения — ни ячейки, ни тары: строка уйдёт в зону сортировки', () => {
    expect(selectionPlacement(null)).toEqual({
      cellId: null,
      containerKind: null,
      containerId: null,
    })
  })

  it('выделение на коробе — количество идёт в этот короб (п. 6 постановки)', () => {
    const boxRow = row({
      key: 'box:11111111-1111-4111-8111-111111111111',
      id: '11111111-1111-4111-8111-111111111111',
      kind: 'box',
    })
    expect(selectionPlacement(boxRow)).toEqual({
      cellId: null,
      containerKind: 'box',
      containerId: '11111111-1111-4111-8111-111111111111',
    })
  })

  it('выделение на палете и грузоместе тоже читается как тара', () => {
    expect(
      selectionPlacement(row({ kind: 'pallet', id: 'pallet-id', key: 'pallet:pallet-id' })),
    ).toEqual({ cellId: null, containerKind: 'pallet', containerId: 'pallet-id' })
    expect(
      selectionPlacement(
        row({ kind: 'cargo_place', id: 'cargo-id', key: 'cargo_place:cargo-id' }),
      ),
    ).toEqual({ cellId: null, containerKind: 'cargo_place', containerId: 'cargo-id' })
  })

  it('выделение на настоящей ячейке (реальный UUID) — адрес берём из неё', () => {
    const cellRow = row({
      kind: 'cell',
      id: '22222222-2222-4222-8222-222222222222',
      key: 'cell:22222222-2222-4222-8222-222222222222',
    })
    expect(selectionPlacement(cellRow)).toEqual({
      cellId: '22222222-2222-4222-8222-222222222222',
      containerKind: null,
      containerId: null,
    })
  })

  it('служебная строка «Без ячеек» — не настоящий адрес, ведём себя как без выделения', () => {
    const unassignedRow = row({ kind: 'cell', id: 'unassigned', key: 'cell:unassigned' })
    expect(selectionPlacement(unassignedRow)).toEqual({
      cellId: null,
      containerKind: null,
      containerId: null,
    })
    const wrapperRow = row({ kind: 'cell', id: 'inventory', key: 'cell:inventory' })
    expect(selectionPlacement(wrapperRow)).toEqual({
      cellId: null,
      containerKind: null,
      containerId: null,
    })
  })

  it('выделение на товаре невозможно по построению — на всякий случай тоже нейтрально', () => {
    const productRow = row({ kind: 'product', id: 'product-id', key: 'product:product-id' })
    expect(selectionPlacement(productRow)).toEqual({
      cellId: null,
      containerKind: null,
      containerId: null,
    })
  })
})

// WMS-543: «Создать короб / палету / грузоместо» — в какую ячейку ставить тару.
// Выделенная строка важнее; без выделения — ячейка, открытая сканером.
describe('containerTargetCell', () => {
  const OPEN_CELL = '33333333-3333-4333-8333-333333333333'
  const SELECTED_CELL = '22222222-2222-4222-8222-222222222222'
  const openCell: ScanOpenPlace = { containerId: null, cellId: OPEN_CELL }

  it('R1: строка не выделена, сканером открыта ячейка — тара встаёт в неё', () => {
    expect(containerTargetCell(null, openCell)).toBe(OPEN_CELL)
  })

  it('R1: открыта тара в ячейке — новая тара встаёт в ячейку открытой тары', () => {
    expect(containerTargetCell(null, { containerId: 'box-id', cellId: OPEN_CELL })).toBe(OPEN_CELL)
  })

  it('открыта тара из «Без ячеек» — это не адрес склада: тара без ячейки, как раньше', () => {
    expect(containerTargetCell(null, { containerId: 'box-id', cellId: 'unassigned' })).toBeNull()
  })

  it('R2: выделенная ячейка важнее открытой сканером', () => {
    const cellRow = row({ kind: 'cell', id: SELECTED_CELL, key: `cell:${SELECTED_CELL}` })
    expect(containerTargetCell(cellRow, openCell)).toBe(SELECTED_CELL)
  })

  it('R2: выделены тара, товар или «Без ячеек» — результат прежний, открытая ячейка не подставляется', () => {
    const selected = [
      row(),
      row({ kind: 'pallet', id: 'pallet-id', key: 'pallet:pallet-id' }),
      row({ kind: 'cargo_place', id: 'cargo-id', key: 'cargo_place:cargo-id' }),
      row({ kind: 'product', id: 'product-id', key: 'product:product-id' }),
      row({ kind: 'cell', id: 'unassigned', key: 'cell:unassigned' }),
    ]
    for (const selectedRow of selected) {
      expect(containerTargetCell(selectedRow, openCell)).toBe(selectionPlacement(selectedRow).cellId)
      expect(containerTargetCell(selectedRow, openCell)).toBeNull()
    }
  })

  it('R3: ничего не открыто и не выделено — тара без ячейки, как раньше', () => {
    expect(containerTargetCell(null, NOTHING_OPEN)).toBeNull()
  })
})
