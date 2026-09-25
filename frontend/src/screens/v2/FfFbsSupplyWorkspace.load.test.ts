// Execute the production load callback with deferred HTTP responses. Hook lifecycle
// is modelled by generation changes; this does not replace browser navigation checks.
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const hooks: Record<string, string> = {}
function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)
      && node.initializer.expression.getText(file) === 'useCallback') {
    hooks[node.name.getText(file)] = node.initializer.arguments[0].getText(file)
  }
  ts.forEachChild(node, visit)
}
visit(file)
const callback = hooks.load
const beginWrite = hooks.beginWorkspaceWrite
if (!callback) throw new Error('Production load callback not found')
if (!beginWrite) throw new Error('Production beginWorkspaceWrite helper not found')

function deferred() {
  let resolve!: (value: unknown) => void
  let reject!: (error: Error) => void
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function fixture() {
  const generation = { current: 1 }
  const writeSeq = { current: 0 }
  // Поставка, чей состав на экране, идёт следом за применённым снимком — так же,
  // как её ведёт эффект экрана.
  const shownSupplyId = { current: null as string | null }
  const pending = new Map<string, ReturnType<typeof deferred>>()
  const visible = { workspace: null as unknown, stage: '', error: '', busy: false }
  // Билет занимает настоящий продуктовый beginWorkspaceWrite, а не копия из теста:
  // иначе проверялось бы правило, которого в экране может уже не быть. У билета
  // описаны типы, поэтому исходник сначала переводится в JS.
  const beginWriteJs = ts.transpileModule(`const beginWorkspaceWrite = ${beginWrite}`, {
    compilerOptions: { target: ts.ScriptTarget.ESNext },
  }).outputText
  const beginWorkspaceWrite = (new Function('workspaceOpenGeneration', 'workspaceWriteSeq',
    'shownSupplyId', `${beginWriteJs}; return beginWorkspaceWrite`) as (
    ...args: unknown[]) => () => unknown)(generation, writeSeq, shownSupplyId)
  // У чтения описаны типы (признак применения снимка), поэтому оно тоже сначала
  // переводится в JS: исполняется тот же код, только без аннотаций.
  const callbackJs = ts.transpileModule(`const load = ${callback}`, {
    compilerOptions: { target: ts.ScriptTarget.ESNext },
  }).outputText
  const callbackFactory = new Function('fetchFbsWorkspace', 'beginWorkspaceWrite',
    'setWorkspace', 'setStage', 'setError', 'setBusy', 'fbsErrorText',
    'fbsStageAfterWorkspaceRefresh', 'visualStage', 'open', 'supplyId', 'token',
    'authHeaders', `${callbackJs}; return load`) as (...args: unknown[]) => (
      silent?: boolean, onApplied?: (applied: unknown) => void) => Promise<unknown>
  const load = (id: string) => callbackFactory(
    (_token: string, _headers: unknown, supplyId: string) => {
      const response = deferred(); pending.set(supplyId, response); return response.promise
    }, beginWorkspaceWrite,
    (next: { supply: { id: string } }) => { visible.workspace = next; shownSupplyId.current = next.supply.id },
    (update: (previous: string) => string) => { visible.stage = update(visible.stage) },
    (next: string) => { visible.error = next }, (next: boolean) => { visible.busy = next },
    (message: string) => message, (_marketplace: string, _old: string, next: string) => next,
    (stage: string) => stage, true, id, 'synthetic', () => ({}),
  )
  return { generation, writeSeq, pending, visible, load }
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
  // WMS-477: тихое обновление раз в 15 с идёт рядом с действиями оператора, и ответы
  // возвращаются в произвольном порядке. Запоздалый ответ не должен возвращать строки
  // к вердиктам, которые на экране уже сменились.
  it('keeps the newest silent refresh when an earlier one answers last', async () => {
    const f = fixture()
    const load = f.load('A')
    const first = load(true)
    const firstResponse = f.pending.get('A')!
    const second = load(true)
    f.pending.get('A')!.resolve({ ...workspace('A'), revision: 'new' }); await second
    firstResponse.resolve({ ...workspace('A'), revision: 'stale' }); await first
    expect(f.visible.workspace).toEqual({ ...workspace('A'), revision: 'new' })
  })

  it('lets an operator action outrank a silent refresh that started earlier', async () => {
    const f = fixture()
    const silent = f.load('A')(true)
    // Действие оператора завершилось и записало свой ответ — как это делает run().
    f.writeSeq.current += 1
    f.visible.workspace = { ...workspace('A'), revision: 'operator' }
    f.pending.get('A')!.resolve({ ...workspace('A'), revision: 'stale' }); await silent
    expect(f.visible.workspace).toEqual({ ...workspace('A'), revision: 'operator' })
  })

  // Опрос снимает свой замок в finally, поэтому load обязан завершаться даже при
  // сорванной сети. Иначе первая же ошибка заперла бы тихое обновление навсегда.
  it('settles a failed silent refresh quietly instead of rejecting', async () => {
    const f = fixture()
    const silent = f.load('A')(true)
    f.pending.get('A')!.reject(new Error('network down'))
    await expect(silent).resolves.toBeUndefined()
    expect(f.visible).toEqual({ workspace: null, stage: '', error: '', busy: false })
  })

  // Скан ЧЗ ждёт ответ этого же чтения, чтобы назвать вердикт. Проигравший гонку
  // снимок не попадает на экран, но вызвавшему возвращается.
  it('returns the fetched snapshot to its caller even after losing the race', async () => {
    const f = fixture()
    const load = f.load('A')
    const first = load(true)
    const firstResponse = f.pending.get('A')!
    const second = load(true)
    f.pending.get('A')!.resolve({ ...workspace('A'), revision: 'new' }); await second
    firstResponse.resolve({ ...workspace('A'), revision: 'stale' })
    await expect(first).resolves.toEqual({ ...workspace('A'), revision: 'stale' })
    expect(f.visible.workspace).toEqual({ ...workspace('A'), revision: 'new' })
  })

  // WMS-477: итог операции, посчитанный по ответу, вправе назвать только снимок,
  // который лёг на экран. Признак применения идёт вместе с самим применением,
  // иначе оператор увидел бы счётчик, спорящий со строками.
  it('tells its caller about the snapshot it put on the screen', async () => {
    const f = fixture()
    const applied: unknown[] = []
    const read = f.load('A')(true, (next) => { applied.push(next) })
    f.pending.get('A')!.resolve(workspace('A')); await read
    expect(applied).toEqual([workspace('A')])
    expect(f.visible.workspace).toEqual(workspace('A'))
  })

  it('says nothing about a snapshot that lost the race to a newer one', async () => {
    const f = fixture()
    const load = f.load('A')
    const applied: unknown[] = []
    const first = load(true, (next) => { applied.push(next) })
    const firstResponse = f.pending.get('A')!
    const second = load(true)
    f.pending.get('A')!.resolve({ ...workspace('A'), revision: 'newer' }); await second
    firstResponse.resolve({ ...workspace('A'), revision: 'stale' }); await first
    expect(applied).toEqual([])
    expect(f.visible.workspace).toEqual({ ...workspace('A'), revision: 'newer' })
  })

  it('says nothing when the read itself failed or the supply was already closed', async () => {
    const f = fixture()
    const applied: unknown[] = []
    const broken = f.load('A')(true, (next) => { applied.push(next) })
    f.pending.get('A')!.reject(new Error('network down')); await broken
    expect(applied).toEqual([])
    const closed = f.load('A')(true, (next) => { applied.push(next) })
    f.generation.current += 1
    f.pending.get('A')!.resolve(workspace('A')); await closed
    expect(applied).toEqual([])
    expect(f.visible.workspace).toBeNull()
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
