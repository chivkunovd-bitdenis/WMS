import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { fbsOrderPrintDone } from './fbsUx'

// Проверяем обработчик кнопки и расчёт экрана; браузерная приёмка остаётся отдельно.
const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const expressions = new Map<string, string>()
function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.initializer) {
    expressions.set(node.name.getText(file), node.initializer.getText(file))
  }
  if (ts.isCallExpression(node) && node.expression.getText(file) === 'openBulkOrderMarkingPrint') {
    expressions.set('bulkPrint', node.getText(file))
  }
  ts.forEachChild(node, visit)
}
visit(file)

function printMode(codes: boolean[], options = { skipped: false, ozon: false }) {
  const orders = codes.map((hasCode, id) => ({
    product: { id: String(id) },
    sticker: { status: 'print_opened', applied_at: null },
    metadata: {
      required: [], optional: ['sgtin'], delivery_allowed: true, last_checked_at: null,
      states: hasCode ? [{ kind: 'sgtin', status: 'accepted', reason: null, value_tail: 'TAIL0487' }] : [],
    },
  }))
  const script = `
    const requiresOrderHonestSign = ${expressions.get('requiresOrderHonestSign')};
    const orderPrintDone = ${expressions.get('orderPrintDone')};
    return { done: printPackingOrders.map(orderPrintDone), mode: ${expressions.get('bulkPrint')} };
  `
  const run = new Function('fbsOrderPrintDone', 'workspace', 'packLineByProduct', 'isOzonSupply',
    'printPackingOrders', 'openBulkOrderMarkingPrint',
    ts.transpile(script, { target: ts.ScriptTarget.ES2023 }))
  return run(fbsOrderPrintDone, { supply: { honest_sign_skipped: options.skipped } },
    new Map(orders.map((order) => [order.product.id, { requires_honest_sign: true }])),
    options.ozon, orders, (_orders: unknown, reprint: boolean) => reprint)
}

describe('WMS-487: режим групповой печати', () => {
  it('выбирает обычную печать, если всем или части заказов нужны коды', () => {
    expect(printMode([false, false])).toEqual({ done: [false, false], mode: false })
    expect(printMode([true, false])).toEqual({ done: [true, false], mode: false })
  })

  it('выбирает повторную печать, только когда все заказы напечатаны', () => {
    expect(printMode([true, true])).toEqual({ done: [true, true], mode: true })
  })

  it('сохраняет снятие требования новых кодов после honest_sign_skipped', () => {
    expect(printMode([true, false], { skipped: true, ozon: false }))
      .toEqual({ done: [true, true], mode: true })
  })

  it('сохраняет прежний расчёт для Ozon', () => {
    expect(printMode([true, false], { skipped: false, ozon: true }))
      .toEqual({ done: [true, true], mode: true })
  })
})
