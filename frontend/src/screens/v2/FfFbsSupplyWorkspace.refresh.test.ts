// WMS-477 R4: тихое обновление раз в 15 с при видимом окне должно работать и на вкладке
// «Упаковка и маркировка», тем же таймером, что на «Подборе» и «Коробах». Как и
// FfFbsSupplyWorkspace.load.test.ts, тест читает исходник компонента через TS AST:
// хук нельзя вызвать без React-дерева, а список стадий таймера — единственное, что
// здесь менялось. Проверка экрана руками остаётся обязательной.
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

type RefreshTimer = { stages: string[]; intervalMs: number; body: string }

function findRefreshTimer(): RefreshTimer | null {
  let found: RefreshTimer | null = null
  function visit(node: ts.Node) {
    if (found) return
    if (ts.isCallExpression(node) && node.expression.getText(file) === 'useEffect') {
      const body = node.arguments[0]?.getText(file) ?? ''
      if (body.includes('window.setInterval') && body.includes('load(true)')) {
        let stages: string[] = []
        let intervalMs = 0
        function inner(child: ts.Node) {
          if (ts.isCallExpression(child) && child.expression.getText(file).endsWith('.includes')
            && child.arguments[0]?.getText(file) === 'stage') {
            const target = (child.expression as ts.PropertyAccessExpression).expression
            if (ts.isArrayLiteralExpression(target)) {
              stages = target.elements.map((element) => element.getText(file).replaceAll("'", ''))
            }
          }
          if (ts.isCallExpression(child) && child.expression.getText(file) === 'window.setInterval') {
            intervalMs = Number(child.arguments[1]?.getText(file).replaceAll('_', ''))
          }
          ts.forEachChild(child, inner)
        }
        inner(node)
        found = { stages, intervalMs, body }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return found
}

describe('WMS-477 silent refresh of the packing tab', () => {
  const timer = findRefreshTimer()
  if (!timer) throw new Error('Refresh timer effect not found in FfFbsSupplyWorkspace.tsx')

  it('polls the workspace on packing with the same 15 s timer as picking and boxes', () => {
    expect(timer.stages).toEqual(['picking', 'packing', 'boxes'])
    expect(timer.intervalMs).toBe(15_000)
  })

  it('polls only while the browser tab is visible and never touches the stage', () => {
    expect(timer.body).toContain("document.visibilityState === 'visible'")
    expect(timer.body).not.toContain('setStage')
    expect(timer.body).not.toContain('setBusy')
  })
})
