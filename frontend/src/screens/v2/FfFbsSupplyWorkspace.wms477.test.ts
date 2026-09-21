// WMS-477 разбирается прямо из исходника экрана, потому что в проекте нет jsdom и
// отрисовать компонент в тесте нечем. Проверяется контракт тихого обновления — на
// каких вкладках таймер живёт, как часто ходит, что делает при скрытом окне и
// снимается ли при закрытии, — поведение run() при ответе, проигравшем гонку,
// и условия показа кнопки «Проверить в WB».
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

let effect = ''
let deps = ''
let runSource = ''
let button: ts.JsxElement | null = null
function visit(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(file) === 'useEffect'
    && node.getText(file).includes('setInterval')) {
    effect = node.arguments[0].getText(file)
    deps = node.arguments[1].getText(file)
  }
  if (ts.isVariableDeclaration(node) && node.name.getText(file) === 'run'
    && node.initializer && ts.isArrowFunction(node.initializer)) {
    runSource = node.initializer.getText(file)
  }
  if (ts.isJsxElement(node) && attributeOf(node, 'data-testid').includes('fbs-packing-check-wb')) button = node
  ts.forEachChild(node, visit)
}
function attributeOf(element: ts.JsxElement, name: string) {
  const found = element.openingElement.attributes.properties
    .find((property) => ts.isJsxAttribute(property) && property.name.getText(file) === name)
  return found && ts.isJsxAttribute(found) ? found.initializer?.getText(file) ?? '' : ''
}
visit(file)
if (!effect) throw new Error('Silent refresh effect not found')
if (!runSource) throw new Error('Production run() helper not found')
if (!button) throw new Error('«Проверить в WB» button not found')
// У run() описаны типы параметров, поэтому исходник сначала переводится в JS:
// проверяется тот же код экрана, только без аннотаций.
const runJs = ts.transpileModule(`const run = ${runSource}`, {
  compilerOptions: { target: ts.ScriptTarget.ESNext },
}).outputText

const attribute = (name: string) => attributeOf(button!, name)

/** Условие, под которым кнопка вообще попадает на экран. */
function renderCondition(node: ts.Node): string {
  if (ts.isConditionalExpression(node)) return node.condition.getText(file)
  if (!node.parent) throw new Error('«Проверить в WB» button is rendered unconditionally')
  return renderCondition(node.parent)
}

/** Исполняет тело эффекта на подставных зависимостях и возвращает то, что оно сделало. */
function runEffect(options: {
  open: boolean; supplyId: string; stage: string; visibility: string
  respond?: (settle: () => void) => void
}) {
  const loads: boolean[] = []
  let tick: (() => void) | null = null
  let cleared: number | null = null
  const inFlight = { current: false }
  const factory = new Function('open', 'supplyId', 'stage', 'load', 'silentRefreshInFlight',
    'window', 'document', `return (${effect})()`) as (...args: unknown[]) => (() => void) | undefined
  const cleanup = factory(
    options.open, options.supplyId, options.stage,
    (silent: boolean) => {
      loads.push(silent)
      // Ответ приходит, только когда его отпустит сам тест: так проверяется
      // поведение при запросе, который идёт дольше шага опроса.
      return new Promise<void>((resolve) => { (options.respond ?? ((settle) => settle()))(resolve) })
    },
    inFlight,
    {
      setInterval: (callback: () => void, delay: number) => { tick = callback; return delay },
      clearInterval: (timer: number) => { cleared = timer },
    },
    { get visibilityState() { return options.visibility } },
  )
  return { loads, tick: () => tick?.(), cleanup, cleared: () => cleared, inFlight }
}

/** Исполняет продуктовый run() с заранее заданной судьбой его билета. */
function runOperation(options: {
  ticket: { isCurrent: boolean; isLatest: boolean }
  success: string | ((next: { revision: string }) => string)
}) {
  const answer = { supply: { id: 'supply-1', marketplace: 'wb' }, stage: 'packing', revision: 'answer' }
  const seen = { workspace: null as unknown, stage: 'packing', notice: null as string | null, busy: false }
  const factory = new Function(
    'beginWorkspaceWrite', 'setBusy', 'setError', 'setNotice', 'setRetryAction',
    'setWorkspace', 'setStage', 'fbsStageAfterWorkspaceRefresh', 'visualStage',
    'FbsApiError', 'fbsErrorText', `${runJs}; return run`,
  ) as (...args: unknown[]) => (operation: () => Promise<unknown>, success: unknown) => Promise<unknown>
  const run = factory(
    () => ({ isCurrent: () => options.ticket.isCurrent, isLatest: () => options.ticket.isLatest }),
    (next: boolean) => { seen.busy = next },
    () => {},
    (next: string | null) => { seen.notice = next },
    () => {},
    (next: unknown) => { seen.workspace = next },
    (update: (previous: string) => string) => { seen.stage = update(seen.stage) },
    (_marketplace: string, _current: string, next: string) => next,
    (stage: string) => stage,
    class extends Error {},
    (message: string) => message,
  )
  return { seen, answer, result: run(async () => answer, options.success) }
}

describe('WMS-477 silent workspace refresh', () => {
  it('runs on picking, packing and boxes every 15 seconds', () => {
    for (const stage of ['picking', 'packing', 'boxes']) {
      const run = runEffect({ open: true, supplyId: 'supply-1', stage, visibility: 'visible' })
      expect(run.cleanup, `${stage} must arm the timer`).toBeTypeOf('function')
      run.cleanup!()
      expect(run.cleared(), `${stage} must use a 15s interval`).toBe(15_000)
    }
  })

  it('refreshes silently so the tab, progress and scan state stay untouched', () => {
    const run = runEffect({ open: true, supplyId: 'supply-1', stage: 'packing', visibility: 'visible' })
    run.tick()
    expect(run.loads).toEqual([true])
  })

  it('does not poll a hidden window', () => {
    const run = runEffect({ open: true, supplyId: 'supply-1', stage: 'packing', visibility: 'hidden' })
    run.tick()
    expect(run.loads).toEqual([])
  })

  it('arms nothing on composition or a closed workspace', () => {
    expect(runEffect({ open: true, supplyId: 'supply-1', stage: 'composition', visibility: 'visible' }).cleanup)
      .toBeUndefined()
    expect(runEffect({ open: false, supplyId: 'supply-1', stage: 'packing', visibility: 'visible' }).cleanup)
      .toBeUndefined()
    expect(runEffect({ open: true, supplyId: '', stage: 'packing', visibility: 'visible' }).cleanup)
      .toBeUndefined()
  })

  it('does not move the operator between tabs or raise the busy indicator', () => {
    expect(effect).not.toContain('setStage')
    expect(effect).not.toContain('setBusy')
  })

  // Ответ WB может идти дольше 15 с. Раньше каждый следующий шаг опроса стартовал
  // поверх незавершённого, и любой успешный ответ оказывался устаревшим к своему
  // приходу: строка не зеленела никогда.
  it('keeps a single silent request in flight when the answer outlasts the interval', async () => {
    let settle: (() => void) | null = null
    const poll = runEffect({
      open: true, supplyId: 'supply-1', stage: 'packing', visibility: 'visible',
      respond: (resolve) => { settle = resolve },
    })
    poll.tick()
    poll.tick()
    poll.tick()
    expect(poll.loads).toEqual([true])
    expect(poll.inFlight.current).toBe(true)
    settle!()
    await Promise.resolve()
    await Promise.resolve()
    expect(poll.inFlight.current).toBe(false)
    poll.tick()
    expect(poll.loads).toEqual([true, true])
  })

  // Замок снимается в finally, а не в then: сорванный запрос иначе запер бы опрос
  // навсегда и строки перестали бы обновляться до переоткрытия поставки.
  // Что сам load не отклоняется, проверяет FfFbsSupplyWorkspace.load.test.ts.
  it('releases the lock through finally, not through a success branch', () => {
    expect(effect).toContain('.finally(')
  })

  // Пропажа зависимости оставила бы таймер с устаревшим load или не сняла бы его
  // при закрытии окна — оба случая означают запросы по уже закрытой поставке.
  it('re-arms the timer on every input it reads', () => {
    expect(deps).toBe('[open, supplyId, stage, load]')
  })
})

// Действие оператора и тихое обновление идут одновременно, и ответ действия может
// прийти уже после более свежего снимка. Строки в этом случае не откатываем, но и
// молчать в ответ на нажатие кнопки нельзя.
describe('WMS-477 operator action that lost the race', () => {
  it('applies the answer and its computed text while it is the newest', async () => {
    const call = runOperation({
      ticket: { isCurrent: true, isLatest: true },
      success: (next) => `Проверено в WB: ${next.revision}.`,
    })
    await call.result
    expect(call.seen.workspace).toEqual(call.answer)
    expect(call.seen.notice).toBe('Проверено в WB: answer.')
  })

  it('still confirms the action itself when a newer snapshot already replaced the rows', async () => {
    const call = runOperation({ ticket: { isCurrent: true, isLatest: false }, success: 'Задание создано.' })
    await expect(call.result).resolves.toEqual(call.answer)
    expect(call.seen.workspace).toBeNull()
    expect(call.seen.notice).toBe('Задание создано.')
    expect(call.seen.busy).toBe(false)
  })

  it('does not read a discarded snapshot out loud', async () => {
    const call = runOperation({
      ticket: { isCurrent: true, isLatest: false },
      success: (next) => `Проверено в WB: ${next.revision}.`,
    })
    await expect(call.result).resolves.toEqual(call.answer)
    expect(call.seen.notice).toBeNull()
    expect(call.seen.workspace).toBeNull()
  })

  it('leaves the rows, notice and busy flag of another supply alone', async () => {
    const call = runOperation({ ticket: { isCurrent: false, isLatest: false }, success: 'Задание создано.' })
    await expect(call.result).resolves.toBeNull()
    expect(call.seen).toEqual({ workspace: null, stage: 'packing', notice: null, busy: true })
  })
})

describe('WMS-477 «Проверить в WB» button', () => {
  it('asks Wildberries only where such a request exists and packing is still editable', () => {
    // На Ozon этой операции нет, а у закрытой для правки упаковки кнопка стала бы
    // действием без последствий.
    expect(renderCondition(button!)).toBe('!isOzonSupply && packagingEditable')
  })

  it('stays out of reach while another operation runs or nothing has a code yet', () => {
    expect(attribute('disabled')).toBe('{busy || packingOrdersWithCode === 0}')
  })

  it('sends one request for the whole supply', () => {
    expect(attribute('onClick')).toBe('{checkMarkingsInWb}')
    expect(source).toContain('syncFbsSupplyMarkings(token, authHeaders, workspace.supply.id)')
  })
})
