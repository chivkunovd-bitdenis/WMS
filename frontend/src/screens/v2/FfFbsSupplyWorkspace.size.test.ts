// Разметку строки упаковки берём из самого экрана: JSX достаётся из файла, компилируется
// в createElement и собирается своим регистратором. Браузерного DOM во фронтовых тестах нет,
// и без такой сборки съехавший столбец «Размер» ловится только глазами.
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { fbsPackingShowsSize, fbsPackingSizes } from './FfFbsSupplyWorkspace'

const wbOrder = (size: string | null) => ({ product: { size }, positions: [] })
const ozonOrder = (sizes: Array<string | null>, productSize: string | null = null) => ({
  product: { size: productSize },
  positions: sizes.map((size) => ({ size })),
})

describe('C4 · размер есть хотя бы у одного товара WB', () => {
  it('показывает столбец всей вкладке и держит прочерк у остальных строк', () => {
    const orders = [wbOrder('38'), wbOrder(null), wbOrder('')]
    expect(fbsPackingShowsSize(orders, false)).toBe(true)
    expect(orders.map((order) => fbsPackingSizes(order, false))).toEqual([['38'], [null], [null]])
  })

  it('не считает размером пробелы из карточки', () => {
    expect(fbsPackingShowsSize([wbOrder('   ')], false)).toBe(false)
    expect(fbsPackingSizes(wbOrder(' 38 '), false)).toEqual(['38'])
  })
})

describe('C5 · размеров нет, затем появился', () => {
  it('прячет столбец на пустом наборе и показывает после добавления заказа с размером', () => {
    const withoutSize = [wbOrder(null), wbOrder(null)]
    expect(fbsPackingShowsSize(withoutSize, false)).toBe(false)
    expect(fbsPackingShowsSize([...withoutSize, wbOrder('L')], false)).toBe(true)
    expect(fbsPackingShowsSize([], false)).toBe(false)
  })
})

describe('C6 · Ozon с несколькими позициями', () => {
  it('отдаёт размер каждой позиции в порядке строк, пустую оставляет прочерком', () => {
    expect(fbsPackingSizes(ozonOrder(['M', 'L', null]), true)).toEqual(['M', 'L', null])
  })

  it('не подставляет размер первой позиции всему отправлению', () => {
    expect(fbsPackingShowsSize([ozonOrder([null, null], '42')], true)).toBe(false)
    expect(fbsPackingSizes(ozonOrder([null, null], '42'), true)).toEqual([null, null])
  })

  it('видит размер у любой позиции, не только у первой', () => {
    expect(fbsPackingShowsSize([ozonOrder([null, 'XL'])], true)).toBe(true)
    expect(fbsPackingSizes(ozonOrder([]), true)).toEqual([])
  })
})

type RenderNode = { type: string; props: Record<string, unknown>; children: unknown[] }

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

function packingRowJsx(): string {
  let found = ''
  const visit = (node: ts.Node) => {
    if (found) return
    if (ts.isJsxElement(node) && node.openingElement.attributes.properties.some((attribute) =>
      ts.isJsxAttribute(attribute) && attribute.name.getText(file) === 'data-order-id')) {
      found = node.getText(file)
      return
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  if (!found) throw new Error('Строка упаковки с data-order-id не найдена')
  return found
}

function sizeCellJsx(): string {
  let found = ''
  const visit = (node: ts.Node) => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === 'PackingSizeCell') {
      for (const statement of node.body?.statements ?? []) {
        if (ts.isReturnStatement(statement) && statement.expression) found = statement.expression.getText(file)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  if (!found) throw new Error('Ячейка размера PackingSizeCell не найдена')
  return found
}

function compile(jsx: string): (scope: object) => RenderNode {
  const emitted = ts.transpileModule(`(${jsx})`, {
    compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
  }).outputText.replace(/^"use strict";?/, '').trim().replace(/;$/, '')
  return new Function('scope', `with (scope) { return ${emitted} }`) as (scope: object) => RenderNode
}

const recorder = {
  createElement(type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): RenderNode {
    const kids = (children as unknown[]).flat(Infinity as 20)
      .filter((child) => child !== null && child !== undefined && child !== false && child !== '')
    if (typeof type === 'function') {
      return (type as (props: Record<string, unknown>) => RenderNode)({ ...(props ?? {}), children: kids })
    }
    return { type: String(type), props: props ?? {}, children: kids }
  },
  Fragment: 'Fragment',
}

function render(compiled: (scope: object) => RenderNode, values: Record<string, unknown>): RenderNode {
  const bindings: Record<string, unknown> = { React: recorder, ...values }
  return compiled(new Proxy(bindings, {
    has: () => true,
    get: (target, key) => {
      if (typeof key !== 'string') return undefined
      if (key in target) return target[key]
      if (key in globalThis) return (globalThis as unknown as Record<string, unknown>)[key]
      // Незаданное имя — это компонент разметки: запоминаем его как тег.
      return key
    },
  }))
}

const renderRow = compile(packingRowJsx())
const renderSizeCell = compile(sizeCellJsx())

type RowOptions = {
  needsHonestSign?: boolean
  showsMarkingAvailable?: boolean
  printed?: boolean
  showsSize?: boolean
  sizes?: Array<string | null>
  isOzon?: boolean
  productName?: string
  positionNames?: string[]
  tail?: string | null
  operatorKiz?: boolean
  markingCodeId?: string
  onOperatorKizReprint?: (...args: unknown[]) => void
}

function packingRow(options: RowOptions = {}): RenderNode {
  const isOzon = options.isOzon ?? false
  const positions = (options.positionNames ?? ['Платок «Весна»']).map((name, index) => ({
    id: `pos-${index}`, product_id: `product-${index}`, name, seller_article: `art-${index}`, sku: `sku-${index}`,
  }))
  const sizes = options.sizes ?? [null]
  return render(renderRow, {
    order: {
      id: 'order-1',
      wb_order_id: 5813479884,
      external_order_id: '0198-0001-1',
      product: { id: 'product-0', name: options.productName ?? 'Палантин кашемировый', image_url: null },
      positions,
      sticker: { code: null },
    },
    printed: options.printed ?? false,
    needsHonestSign: options.needsHonestSign ?? false,
    packingShowsMarkingAvailable: options.showsMarkingAvailable ?? false,
    packingShowsSize: options.showsSize ?? true,
    rowSizes: options.showsSize === false ? [] : sizes,
    isOzonSupply: isOzon,
    ozonPositions: isOzon ? positions : [],
    markingNeeded: 1,
    markingAvailable: 0,
    markingShortage: false,
    mutedColor: 'text.primary',
    kizRowActive: false,
    ids: 'заказ 5813479884',
    czStates: [],
    acceptedCz: 0,
    czRejected: false,
    czReady: true,
    markingView: { tone: 'neutral', label: '', reason: null },
    markingColor: 'text.secondary',
    markingState: options.markingCodeId ? { id: options.markingCodeId } : undefined,
    tail: options.tail ?? null,
    stickerParts: null,
    line: undefined,
    busy: false,
    kizScanBusy: false,
    kizRowRefs: { current: {} as Record<string, unknown> },
    packingSelectedIds: new Set<string>(),
    markingShortOrderIds: new Set<string>(),
    hasRemovableKiz: () => false,
    hasOperatorKiz: () => options.operatorKiz ?? false,
    openOrderMarkingPrint: options.onOperatorKizReprint ?? (() => undefined),
    productBarcodeOptionsForPosition: () => [],
    alpha: () => 'transparent',
    PackingSizeCell: (props: Record<string, unknown>) => render(renderSizeCell, props),
  })
}

const sxOf = (node: RenderNode) => (node.props.sx ?? {}) as Record<string, unknown>

/** Горизонтальный слот колонки: фиксированная ширина, растяжка или собственный размер. */
function slot(child: unknown): string {
  if (typeof child !== 'object' || child === null) return `текст:${String(child)}`
  const node = child as RenderNode
  const sx = sxOf(node)
  if (sx.flex === 1) return `${node.type}:растяжка`
  if (typeof sx.width === 'number') return `${node.type}:${sx.width}px`
  return `${node.type}:по содержимому`
}

/**
 * Колонки правее блока товара определяют, где стоит его правый край, а значит и столбец
 * «Размер». Одинаковый набор слотов при одинаковом зазоре строки = одна вертикаль.
 */
function columnsAfterProduct(row: RenderNode): string[] {
  const slots = row.children.map(slot)
  const productIndex = slots.findIndex((token) => token.endsWith(':растяжка'))
  if (productIndex < 0) throw new Error('Блок товара в строке упаковки не найден')
  return slots.slice(productIndex + 1)
}

function findAll(node: unknown, testId: string, acc: RenderNode[] = []): RenderNode[] {
  if (typeof node !== 'object' || node === null) return acc
  const current = node as RenderNode
  if (current.props?.['data-testid'] === testId) acc.push(current)
  for (const child of current.children ?? []) findAll(child, testId, acc)
  return acc
}

function textOf(node: unknown): string {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (typeof node !== 'object' || node === null) return ''
  return ((node as RenderNode).children ?? []).map(textOf).join(' ')
}

const sizeCells = (row: RenderNode) => findAll(row, 'fbs-packing-size')

/** Строки, у которых ячейка размера стоит непосредственным соседом: товар WB или позиция Ozon. */
function linesWithSize(node: unknown, acc: RenderNode[] = []): RenderNode[] {
  if (typeof node !== 'object' || node === null) return acc
  const current = node as RenderNode
  const children = (current.children ?? []) as RenderNode[]
  if (children.some((child) => child?.props?.['data-testid'] === 'fbs-packing-size')) acc.push(current)
  for (const child of children) linesWithSize(child, acc)
  return acc
}

const flat = (value: string) => value.replace(/\s+/g, ' ').trim()

/** Само значение размера внутри ячейки — подпись «Размер» идёт отдельной строкой сверху. */
const sizeValue = (cell: RenderNode) => (cell.children as RenderNode[])
  .find((child) => child?.props?.variant === 'body2') as RenderNode

describe('C4 · столбец «Размер» стоит на одной вертикали во всех строках', () => {
  const rowWithMarking = packingRow({ needsHonestSign: true, showsMarkingAvailable: true, sizes: ['38'] })
  const rowPrintedWithoutMarking = packingRow({ showsMarkingAvailable: true, printed: true })
  const rowPlain = packingRow({ showsMarkingAvailable: true })

  it('держит одинаковые слоты справа при ЧЗ, без ЧЗ и с отметкой печати', () => {
    expect(columnsAfterProduct(rowPrintedWithoutMarking)).toEqual(columnsAfterProduct(rowWithMarking))
    expect(columnsAfterProduct(rowPlain)).toEqual(columnsAfterProduct(rowWithMarking))
    expect(columnsAfterProduct(rowWithMarking)).toEqual([
      'Box:118px', 'Box:150px', 'Box:118px', 'Typography:16px', 'Stack:по содержимому',
    ])
  })

  it('оставляет слот «Доступно ЧЗ» пустым у строки без ЧЗ, а не выкидывает его', () => {
    const children = rowPlain.children as RenderNode[]
    const stickerIndex = children.findIndex((child) => sxOf(child).width === 150)
    const reserved = children[stickerIndex - 1]
    expect(sxOf(reserved)).toMatchObject({ width: 118, flexShrink: 0 })
    expect(flat(textOf(reserved))).toBe('')
    expect(findAll(rowWithMarking, 'fbs-packing-marking-available')).toHaveLength(1)
    expect(findAll(rowPlain, 'fbs-packing-marking-available')).toHaveLength(0)
  })

  it('держит ячейку размера фиксированной, значение — прочерк без размера', () => {
    for (const row of [rowWithMarking, rowPrintedWithoutMarking, rowPlain]) {
      expect(sizeCells(row)).toHaveLength(1)
      expect(sxOf(sizeCells(row)[0])).toMatchObject({ width: 76, flexShrink: 0, textAlign: 'right' })
    }
    expect(textOf(sizeCells(rowWithMarking)[0])).toContain('38')
    expect(textOf(sizeCells(rowPlain)[0])).toContain('—')
  })

  it('переносит длинный размер WB внутри колонки и не режет значение', () => {
    for (const size of ['универсальный', '44/46/48/50/52/54']) {
      const row = packingRow({ needsHonestSign: true, showsMarkingAvailable: true, sizes: [size] })
      const cell = sizeCells(row)[0]
      expect(sxOf(cell)).toMatchObject({ width: 76, flexShrink: 0, textAlign: 'right' })
      expect(sxOf(sizeValue(cell)).overflowWrap).toBe('anywhere')
      expect(flat(textOf(cell))).toBe(`Размер ${size}`)
      expect(columnsAfterProduct(row)).toEqual(columnsAfterProduct(rowWithMarking))
    }
  })

  it('не двигает столбец длинным названием товара', () => {
    const long = packingRow({ showsMarkingAvailable: true, productName: 'Палантин кашемировый двусторонний с бахромой ручной работы, коллекция «Зима», артикул очень длинный' })
    expect(columnsAfterProduct(long)).toEqual(columnsAfterProduct(rowWithMarking))
    const productBox = long.children.map((child) => child as RenderNode).find((child) => sxOf(child).flex === 1)
    expect(sxOf(productBox as RenderNode)).toMatchObject({ flex: 1, minWidth: 0 })
  })
})

describe('C5 · поставка без ЧЗ и без размеров', () => {
  it('не резервирует пустой слот ЧЗ, если он не нужен ни одной строке', () => {
    const row = packingRow()
    expect(columnsAfterProduct(row)).toEqual(['Box:150px', 'Box:118px', 'Typography:16px', 'Stack:по содержимому'])
    expect(columnsAfterProduct(packingRow({ printed: true }))).toEqual(columnsAfterProduct(row))
  })

  it('убирает ячейку размера, когда столбец скрыт', () => {
    expect(sizeCells(packingRow({ showsSize: false }))).toHaveLength(0)
  })
})

describe('WMS-489 · перепечатка уже привязанного КИЗ на FBS-упаковке', () => {
  it('показывает маленькую круговую стрелку только у KIZ, внесённого оператором', () => {
    const withOperatorKiz = packingRow({ operatorKiz: true, tail: '…KIZ-123' })
    const withoutOperatorKiz = packingRow({ tail: '…KIZ-123' })
    expect(findAll(withOperatorKiz, 'fbs-kiz-reprint-inline')).toHaveLength(1)
    expect(findAll(withoutOperatorKiz, 'fbs-kiz-reprint-inline')).toHaveLength(0)
    expect(source).toContain('ReplayOutlinedIcon')
  })

  it('ставит стрелку слева от показанного KIZ и открывает стандартную печать в reprint-режиме', () => {
    const calls: unknown[][] = []
    const row = packingRow({
      operatorKiz: true,
      tail: '…KIZ-123',
      markingCodeId: 'marking-code-1',
      onOperatorKizReprint: (...args: unknown[]) => { calls.push(args) },
    })
    const reprintButton = findAll(row, 'fbs-kiz-reprint-inline')[0]
    expect(reprintButton.props['aria-label']).toBe('Перепечатать КИЗ')
    ;(reprintButton.props.onClick as () => void)()
    expect(calls).toHaveLength(1)
    expect(calls[0][2]).toBe(true)
    expect(calls[0][3]).toBe('marking-code-1')

    const reprintIndex = source.indexOf('data-testid="fbs-kiz-reprint-inline"')
    const shownKizIndex = source.indexOf('data-testid="fbs-kiz-tail"')
    expect(reprintIndex).toBeGreaterThan(-1)
    expect(reprintIndex).toBeLessThan(shownKizIndex)
  })
})

describe('C6 · Ozon: размер стоит у своей позиции', () => {
  const row = packingRow({
    isOzon: true,
    showsMarkingAvailable: true,
    positionNames: ['Носки детские', 'Шапка зимняя'],
    sizes: ['M', null],
  })

  it('даёт каждой позиции свою ячейку размера в том же порядке', () => {
    expect(sizeCells(row).map((cell) => flat(textOf(cell)))).toEqual(['Размер M', '—'])
  })

  it('связывает размер именно со своей позицией', () => {
    const lines = linesWithSize(row).map((line) => flat(textOf(line)))
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain('Носки детские')
    expect(lines[0]).toContain('M')
    expect(lines[1]).toContain('Шапка зимняя')
    expect(lines[1]).not.toContain('M')
  })

  it('переносит длинный размер второй позиции, не задевая короткий и прочерк', () => {
    const mixed = packingRow({
      isOzon: true,
      showsMarkingAvailable: true,
      positionNames: ['Носки детские', 'Шапка зимняя', 'Платок «Весна»'],
      sizes: ['M', 'универсальный', null],
    })
    const cells = sizeCells(mixed)
    expect(cells.map((cell) => flat(textOf(cell)))).toEqual(['Размер M', 'универсальный', '—'])
    for (const cell of cells) {
      expect(sxOf(cell)).toMatchObject({ width: 76, flexShrink: 0, textAlign: 'right' })
      expect(sxOf(sizeValue(cell)).overflowWrap).toBe('anywhere')
    }
    const lines = linesWithSize(mixed).map((line) => flat(textOf(line)))
    expect(lines[0]).toContain('Носки детские')
    expect(lines[0]).not.toContain('универсальный')
    expect(lines[1]).toContain('Шапка зимняя')
    expect(lines[1]).toContain('универсальный')
    expect(lines[2]).toContain('Платок «Весна»')
    expect(lines[2]).toContain('—')
  })

  it('держит одну вертикаль у отправлений с ЧЗ и без него', () => {
    const ozonWithMarking = packingRow({
      isOzon: true,
      needsHonestSign: true,
      showsMarkingAvailable: true,
      positionNames: ['Носки детские'],
      sizes: ['M'],
    })
    expect(columnsAfterProduct(ozonWithMarking)).toEqual(columnsAfterProduct(row))
    expect(linesWithSize(ozonWithMarking).map((line) => sxOf(line.children[0] as RenderNode)))
      .toEqual([{ flex: 1, minWidth: 0 }])
  })
})
