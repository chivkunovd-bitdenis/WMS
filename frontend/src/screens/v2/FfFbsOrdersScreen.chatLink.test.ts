import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

// Execute the actual source callbacks: no browser access or reimplementation of load/select.
const source = readFileSync(process.env.WMS_FBS_SOURCE ?? new URL('./FfFbsOrdersScreen.tsx', import.meta.url), 'utf8')
const ast = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
function find(predicate: (node: ts.Node) => boolean): ts.Node {
  let found: ts.Node | undefined
  const visit = (node: ts.Node) => { if (!found && predicate(node)) found = node; if (!found) ts.forEachChild(node, visit) }
  visit(ast)
  if (!found) throw Error('Source callback missing')
  return found
}
function variable(name: string): ts.Expression {
  const node = find((n) => ts.isVariableDeclaration(n) && n.name.getText(ast) === name) as ts.VariableDeclaration
  const init = node.initializer!
  return ts.isCallExpression(init) ? init.arguments[0] : init
}
function evaluate(node: ts.Node, ctx: Record<string, unknown>): unknown {
  const js = ts.transpileModule(`(${node.getText(ast)})`, { compilerOptions: { target: ts.ScriptTarget.ES2022, alwaysStrict: false } }).outputText.trim().replace(/;$/, '')
  return new Function('ctx', `with (ctx) { return ${js} }`)(ctx)
}
function harness() {
  const ctx: Record<string, unknown> = {
    linkedOrderId: 'exact', linkedSellerId: 'seller', token: 'isolated',
    authHeaders: () => ({}), apiUrl: (url: string) => url,
    loadSequence: { current: 0 }, loadingRef: { current: false }, resolvedLinkedOrder: { current: null },
    selected: new Set(), selectedCache: new Map(), orders: [],
    selectionBlockers: [], mixedMarketplaceMessage: null,
  }
  for (const name of ['Busy', 'Error', 'Selected', 'SelectedCache', 'Search', 'ActiveSearch', 'StatusGroup', 'SellerId', 'Marketplace', 'WbWarehouseId', 'Orders', 'ActiveSupplies', 'ExternalActiveOrders', 'WarehouseOptions', 'SearchTotal', 'ServerNow', 'LastLoadedAt']) {
    const key = name[0].toLowerCase() + name.slice(1)
    ctx[`set${name}`] = (value: unknown) => { ctx[key] = typeof value === 'function' ? value(ctx[key]) : value }
  }
  const row = (status = 'new') => ({ id: 'exact', seller: { id: 'seller' }, marketplace: 'wb', status })
  const respond = (order = row()) => { ctx.fetch = async () => ({ ok: true, json: async () => ({ order, status_group: order.status, server_now: 'now' }) }) }
  respond()
  const load = evaluate(variable('load'), ctx) as () => Promise<void>
  const selectAll = () => {
    ctx.selectableIds = (ctx.orders as { id: string }[]).map((order) => order.id)
    ;(evaluate(variable('toggleVisibleSelectable'), ctx) as (checked: boolean) => void)(true)
    ctx.selectedOrders = (evaluate(variable('selectedOrders'), ctx) as () => unknown)()
  }
  const contextChanged = () => {
    const effects: ts.ArrowFunction[] = []
    const visit = (n: ts.Node) => {
      if (ts.isCallExpression(n) && n.expression.getText(ast) === 'useEffect' && n.arguments[0]?.getText(ast).includes('setSelectedCache')) effects.push(n.arguments[0] as ts.ArrowFunction)
      ts.forEachChild(n, visit)
    }
    visit(ast)
    effects.forEach((effect) => (evaluate(effect, ctx) as () => void)())
  }
  return { ctx, row, respond, load, selectAll, contextChanged }
}

describe('WMS-397 exact order actual load and header selection', () => {
  it('select-all supplies the real row to selectedOrders and action enablement after context effects', async () => {
    const h = harness()
    await h.load(); h.contextChanged(); h.selectAll()
    expect(h.ctx.selected).toEqual(new Set(['exact']))
    expect(h.ctx.selectedOrders).toEqual([h.row()])
    const disabled = find((n) => ts.isJsxAttribute(n) && n.name.getText(ast) === 'disabled' && n.getText(ast).includes('selectedOrders.length !== selected.size')) as ts.JsxAttribute
    expect(evaluate((disabled.initializer as ts.JsxExpression).expression!, h.ctx)).toBe(false)
  })
  it('refreshes the cached row on poll and retains valid selection', async () => {
    const h = harness()
    await h.load(); h.selectAll()
    const updated = { ...h.row(), title: 'updated server row' }
    h.respond(updated); await h.load(); expect(h.ctx.selected).toEqual(new Set(['exact'])); h.selectAll()
    expect(h.ctx.selectedOrders).toEqual([updated])
    h.respond(h.row('packed')); await h.load(); h.contextChanged(); h.selectAll()
    expect(h.ctx.selectedOrders).toEqual([h.row('packed')])
  })
  it('ignores a stale success from an older exact-order request', async () => {
    const h = harness()
    let finishOld!: (value: unknown) => void
    h.ctx.fetch = () => new Promise((resolve) => { finishOld = resolve })
    const old = h.load()
    h.respond(); await h.load(); h.selectAll()
    finishOld({ ok: true, json: async () => ({ order: { ...h.row(), id: 'obsolete' }, status_group: 'done' }) })
    await old
    expect(h.ctx.orders).toEqual([h.row()])
    expect(h.ctx.selectedCache).toEqual(new Map([['exact', h.row()]]))
  })
  it('ignores stale failure, but clears rows/selection/cache on current access failure', async () => {
    const h = harness()
    let rejectOld!: (error: Error) => void
    h.ctx.fetch = () => new Promise((_, reject) => { rejectOld = reject })
    const old = h.load()
    h.respond(); await h.load(); h.selectAll()
    rejectOld(Error('stale forbidden')); await old
    expect(h.ctx.selectedOrders).toEqual([h.row()])
    expect(h.ctx.selectedCache).toEqual(new Map([['exact', h.row()]]))
    h.ctx.fetch = async () => ({ ok: false })
    await h.load()
    expect(h.ctx.orders).toEqual([])
    expect(h.ctx.selected).toEqual(new Set())
    expect(h.ctx.selectedCache).toEqual(new Map())
  })
})
