// Execute the production load callback with deferred HTTP responses. Hook lifecycle
// is modelled by generation changes; this does not replace browser navigation checks.
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
let callback = ''
function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(file) === 'load' &&
      node.initializer && ts.isCallExpression(node.initializer)) {
    callback = node.initializer.arguments[0].getText(file)
  }
  ts.forEachChild(node, visit)
}
visit(file)
if (!callback) throw new Error('Production load callback not found')

function deferred() {
  let resolve!: (value: unknown) => void
  let reject!: (error: Error) => void
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function fixture() {
  const generation = { current: 1 }
  const pending = new Map<string, ReturnType<typeof deferred>>()
  const visible = { workspace: null as unknown, stage: '', error: '', busy: false }
  const callbackFactory = new Function('fetchFbsWorkspace', 'workspaceOpenGeneration',
    'setWorkspace', 'setStage', 'setError', 'setBusy', 'fbsErrorText',
    'fbsStageAfterWorkspaceRefresh', 'visualStage', 'open', 'supplyId', 'token',
    'authHeaders', `return (${callback})`) as (...args: unknown[]) => (silent?: boolean) => Promise<unknown>
  const load = (id: string) => callbackFactory(
    (_token: string, _headers: unknown, supplyId: string) => {
      const response = deferred(); pending.set(supplyId, response); return response.promise
    }, generation, (next: unknown) => { visible.workspace = next },
    (update: (previous: string) => string) => { visible.stage = update(visible.stage) },
    (next: string) => { visible.error = next }, (next: boolean) => { visible.busy = next },
    (message: string) => message, (_marketplace: string, _old: string, next: string) => next,
    (stage: string) => stage, true, id, 'synthetic', () => ({}),
  )
  return { generation, pending, visible, load }
}
const workspace = (id: string) => ({ supply: { id, marketplace: 'wb' }, stage: id })

describe('FBS workspace delayed response isolation', () => {
  it('keeps B when the previous A HTTP response finishes last', async () => {
    const f = fixture()
    const a = f.load('A')()
    f.generation.current += 1
    const b = f.load('B')()
    f.pending.get('B')!.resolve(workspace('B')); await b
    f.pending.get('A')!.resolve(workspace('A')); await a
    expect(f.visible).toEqual({ workspace: workspace('B'), stage: 'B', error: '', busy: false })
  })
  it('does not apply old error or stop the new opening loading indicator', async () => {
    const f = fixture()
    const a = f.load('A')()
    f.generation.current += 1
    const b = f.load('B')()
    f.pending.get('A')!.reject(new Error('old request failed')); await a
    expect(f.visible.error).toBe('')
    expect(f.visible.busy).toBe(true)
    f.pending.get('B')!.resolve(workspace('B')); await b
    expect(f.visible.workspace).toEqual(workspace('B'))
  })
  it('ignores a response after close even when the same UUID will reopen', async () => {
    const f = fixture()
    const old = f.load('A')()
    const previousResponse = f.pending.get('A')!
    f.generation.current += 2
    const reopened = f.load('A')()
    f.pending.get('A')!.resolve({ ...workspace('A'), revision: 'new' }); await reopened
    previousResponse.resolve({ ...workspace('A'), revision: 'old' }); await old
    expect(f.visible.workspace).toEqual({ ...workspace('A'), revision: 'new' })
  })
})
