import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

// Execute the dialog's actual guards: copied arithmetic would not catch a UI regression.
const source = ts.createSourceFile('FbsStockDialog.tsx',
  readFileSync(new URL('./FbsStockDialog.tsx', import.meta.url), 'utf8'),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const guards = new Map<string, string>()
function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer &&
      ['increasesCap', 'overAllocated'].includes(node.name.text)) {
    guards.set(node.name.text, node.initializer.getText(source))
  }
  ts.forEachChild(node, visit)
}
visit(source)
if (guards.size !== 2) throw new Error('Stock dialog guards were not found')
const code = ts.transpileModule(
  `const increasesCap = ${guards.get('increasesCap')}; return ${guards.get('overAllocated')};`,
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
).outputText
const evaluate = new Function('rule', 'draft', 'many', 'unitsSum', 'base',
  'publishesAny', 'percentSum', code)

describe('WMS-060 percent to units validation', () => {
  it.each([
    { saved: 5, entered: 5, free: 2, blocked: false },
    { saved: 5, entered: 4, free: 2, blocked: false },
    { saved: 5, entered: 6, free: 2, blocked: true },
    { saved: 0, entered: 5, free: 2, blocked: true },
    { saved: 5, entered: 6, free: 6, blocked: false },
  ])('saved $saved, entered $entered, free $free => blocked $blocked',
    ({ saved, entered, free, blocked }) => {
      const rule = { unitsMode: false, unitsByWarehouse: { 'wb:501001': saved } }
      const draft = { unitsMode: true, unitsByWarehouse: { 'wb:501001': entered } }
      expect(evaluate(rule, draft, false, entered, free, true, 0)).toBe(blocked)
    })
})
