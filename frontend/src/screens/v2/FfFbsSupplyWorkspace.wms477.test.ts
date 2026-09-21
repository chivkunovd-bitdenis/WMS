// WMS-477 разбирается прямо из исходника экрана, потому что в проекте нет jsdom и
// отрисовать компонент в тесте нечем. Проверяется контракт тихого обновления — на
// каких вкладках таймер живёт, как часто ходит, что делает при скрытом окне и
// снимается ли при закрытии, — поведение run() и обоих диалогов при пересечении
// запросов и смене поставки, что сбрасывает открытие поставки, судьба сохранённого
// «Повторить» и условия показа кнопки «Проверить в WB».
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { fbsMarkingVerdictsSummary } from './fbsUx'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

let effect = ''
let deps = ''
let resetEffect = ''
let runSource = ''
let button: ts.JsxElement | null = null
const helpers: Record<string, string> = {}
function visit(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(file) === 'useEffect') {
    const effectDeps = node.arguments[1]?.getText(file) ?? ''
    if (node.getText(file).includes('setInterval')) {
      effect = node.arguments[0].getText(file)
      deps = effectDeps
    }
    // Сброс при открытии поставки ищется по зависимостям, а не по телу: иначе
    // проверка находила бы ровно то, наличие чего сама же и утверждает.
    if (effectDeps === '[open, supplyId, initialWorkspace, load]') resetEffect = node.arguments[0].getText(file)
  }
  if (ts.isVariableDeclaration(node) && node.initializer) {
    const name = node.name.getText(file)
    if (name === 'run' && ts.isArrowFunction(node.initializer)) runSource = node.initializer.getText(file)
    else if (ts.isArrowFunction(node.initializer)) helpers[name] = node.initializer.getText(file)
    else if (ts.isCallExpression(node.initializer) && node.initializer.expression.getText(file) === 'useCallback') {
      helpers[name] = node.initializer.arguments[0].getText(file)
    }
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
if (!resetEffect) throw new Error('Supply opening reset effect not found')
if (!runSource) throw new Error('Production run() helper not found')
if (!button) throw new Error('«Проверить в WB» button not found')
for (const name of ['beginWorkspaceWrite', 'refreshAfterLostRace', 'performSkipHonestSign',
  'addOrdersToCurrentSupply', 'load', 'checkMarkingsInWb']) {
  if (!helpers[name]) throw new Error(`Production ${name} helper not found`)
}
// У кода экрана описаны типы, поэтому он сначала переводится в JS: исполняется тот
// же код, только без аннотаций.
const asJs = (name: string, code: string) => ts.transpileModule(`const ${name} = ${code}`, {
  compilerOptions: { target: ts.ScriptTarget.ESNext },
}).outputText

const attribute = (name: string) => attributeOf(button!, name)
const flush = () => new Promise((resolve) => { setTimeout(resolve, 0) })

/** Условие, под которым кнопка вообще попадает на экран. */
function renderCondition(node: ts.Node): string {
  if (ts.isConditionalExpression(node)) return node.condition.getText(file)
  if (!node.parent) throw new Error('«Проверить в WB» button is rendered unconditionally')
  return renderCondition(node.parent)
}

/**
 * Исполняет функцию экрана целиком: подменённые имена берутся из `given`,
 * остальные свободные имена становятся записывающими заглушками. Так тело
 * проверяется как есть — добавленный в экран вызов не потеряется из-за того,
 * что тест о нём не знал. `with` разрешён: тело new Function разбирается вне
 * строгого режима модуля.
 */
function sandbox(code: string, given: Record<string, unknown>) {
  const calls: Array<[string, unknown]> = []
  const scope = new Proxy({}, {
    has: () => true,
    get: (_target, name) => {
      if (typeof name !== 'string') return undefined
      if (name in given) return given[name]
      if (name in globalThis) return (globalThis as unknown as Record<string, unknown>)[name]
      return (value?: unknown) => { calls.push([name, value]) }
    },
  })
  const invoke = (new Function('scope', `with (scope) { return (${code}) }`) as (
    outer: unknown,
  ) => (...args: unknown[]) => unknown)(scope)
  return { calls, invoke }
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

class TestApiError extends Error {
  retryable: boolean
  constructor(message: string, retryable: boolean) { super(message); this.retryable = retryable }
}

/**
 * Исполняет продуктовый run() с настоящим билетом записи из экрана. Ответ держится
 * до `answer()`/`fail()`, поэтому тест успевает изменить обстановку ровно так, как
 * её меняет оператор: занять номер более поздним чтением, открыть другую поставку
 * или сменить показанный состав.
 */
function operator(options: {
  success: string | ((next: { revision: string }) => string)
  supply?: string
}) {
  const answer = {
    supply: { id: options.supply ?? 'supply-1', marketplace: 'wb' },
    stage: 'packing',
    revision: 'answer',
  }
  const seen = {
    workspace: null as unknown, stage: 'packing', notice: null as string | null,
    error: null as string | null, busy: false, reread: 0,
  }
  const generation = { current: 1 }
  const writeSeq = { current: 0 }
  const shownSupplyId = { current: 'supply-1' as string | null }
  const responses: Array<{ resolve: (value: unknown) => void; reject: (cause: unknown) => void }> = []
  // Восстановительное чтение зовёт обратно только применённым снимком, поэтому
  // тест решает сам, дошло ли оно до экрана.
  const recoveries: Array<((fresh: unknown) => void) | undefined> = []
  let retryAction: (() => void) | null = null
  let calls = 0
  const operation = () => {
    calls += 1
    return new Promise((resolve, reject) => { responses.push({ resolve, reject }) })
  }
  const beginWorkspaceWrite = (new Function('workspaceOpenGeneration', 'workspaceWriteSeq', 'shownSupplyId',
    `${asJs('beginWorkspaceWrite', helpers.beginWorkspaceWrite)}; return beginWorkspaceWrite`) as (
    ...args: unknown[]) => () => unknown)(generation, writeSeq, shownSupplyId)
  const run = (new Function(
    'beginWorkspaceWrite', 'refreshAfterLostRace', 'setBusy', 'setError', 'setNotice',
    'setRetryAction', 'setWorkspace', 'setStage', 'fbsStageAfterWorkspaceRefresh', 'visualStage',
    'FbsApiError', 'fbsErrorText', `${asJs('run', runSource)}; return run`,
  ) as (...args: unknown[]) => (operation: () => Promise<unknown>, success: unknown) => Promise<unknown>)(
    beginWorkspaceWrite,
    (onApplied?: (fresh: unknown) => void) => { seen.reread += 1; recoveries.push(onApplied) },
    (next: boolean) => { seen.busy = next },
    (next: string | null) => { seen.error = next },
    (next: string | null) => { seen.notice = next },
    (update: ((previous: (() => void) | null) => (() => void) | null) | null) => {
      retryAction = typeof update === 'function' ? update(retryAction) : update
    },
    (next: unknown) => { seen.workspace = next },
    (update: (previous: string) => string) => { seen.stage = update(seen.stage) },
    (_marketplace: string, _current: string, next: string) => next,
    (stage: string) => stage,
    TestApiError,
    (message: string) => message,
  )
  return {
    seen, answer, generation, writeSeq, shownSupplyId,
    start: () => run(operation, options.success),
    recover: (fresh: unknown) => { recoveries.at(-1)?.(fresh) },
    answer_: () => responses.shift()!.resolve(answer),
    fail: (cause: unknown) => responses.shift()!.reject(cause),
    retry: () => retryAction?.(),
    hasRetry: () => retryAction !== null,
    calls: () => calls,
  }
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

// Действие оператора и тихое обновление идут одновременно, и ответы возвращаются
// в произвольном порядке. Строки при этом не откатываем, молчать в ответ на нажатие
// кнопки нельзя, а начатое позже чтение не делает свои данные более свежими:
// оно могло прочитать базу ещё до того, как действие сохранилось.
describe('WMS-477 operator action that crossed a silent refresh', () => {
  it('applies the answer and its computed text while it is the newest', async () => {
    const call = operator({ success: (next) => `Проверено в WB: ${next.revision}.` })
    const result = call.start()
    call.answer_()
    await result
    expect(call.seen.workspace).toEqual(call.answer)
    expect(call.seen.notice).toBe('Проверено в WB: answer.')
    expect(call.seen.busy).toBe(false)
    expect(call.seen.reread).toBe(0)
  })

  // Тихое обновление заняло номер позже действия, но ответило раньше — значит,
  // базу оно могло прочитать ещё до сохранения действия. Свой снимок поверх
  // показанного не кладём, но и оставлять экран без результата действия нельзя:
  // просим новое чтение, начатое уже после успеха.
  it('asks for a snapshot taken after the write instead of trusting the newer reader', async () => {
    const call = operator({ success: 'Задание создано.' })
    const result = call.start()
    call.writeSeq.current += 1
    call.answer_()
    await expect(result).resolves.toEqual(call.answer)
    expect(call.seen.workspace).toBeNull()
    expect(call.seen.notice).toBe('Задание создано.')
    expect(call.seen.busy).toBe(false)
    expect(call.seen.reread).toBe(1)
  })

  // Счётчик по отброшенному снимку спорил бы со строками, но и молчать об
  // удавшейся ручной проверке нельзя (R2, D5). Итог называет восстановительное
  // чтение — и только тот его снимок, который дошёл до экрана.
  it('does not read a discarded snapshot out loud but names the recovered one', async () => {
    const call = operator({ success: (next) => `Проверено в WB: ${next.revision}.` })
    const result = call.start()
    call.writeSeq.current += 1
    call.answer_()
    await expect(result).resolves.toEqual(call.answer)
    expect(call.seen.notice).toBeNull()
    expect(call.seen.workspace).toBeNull()
    expect(call.seen.reread).toBe(1)
    expect(call.seen.busy).toBe(false)
    call.recover({ ...call.answer, revision: 'recovered' })
    expect(call.seen.notice).toBe('Проверено в WB: recovered.')
  })

  // Не дошло до экрана — говорить не о чем: строки показывают чужой, более новый
  // снимок, и счётчик по нашему ответу оказался бы рядом с чужим вердиктом.
  it('keeps quiet while the recovery read has not reached the screen', async () => {
    const call = operator({ success: (next) => `Проверено в WB: ${next.revision}.` })
    const result = call.start()
    call.writeSeq.current += 1
    call.answer_()
    await result
    expect(call.seen.reread).toBe(1)
    expect(call.seen.notice).toBeNull()
  })

  it('does not name a recovered snapshot of a supply the operator no longer sees', async () => {
    const call = operator({ success: (next) => `Проверено в WB: ${next.revision}.` })
    const result = call.start()
    call.writeSeq.current += 1
    call.answer_()
    await result
    call.generation.current += 1
    call.recover({ ...call.answer, revision: 'recovered' })
    expect(call.seen.notice).toBeNull()
    call.generation.current -= 1
    call.shownSupplyId.current = 'supply-2'
    call.recover({ ...call.answer, revision: 'recovered' })
    expect(call.seen.notice).toBeNull()
  })

  // Постоянный текст не зависит от снимка: он уже сказан и восстановительным
  // чтением не переписывается.
  it('does not wait for a read to tell what does not depend on the answer', async () => {
    const call = operator({ success: 'Задание создано.' })
    const result = call.start()
    call.writeSeq.current += 1
    call.answer_()
    await result
    expect(call.seen.notice).toBe('Задание создано.')
    call.recover({ ...call.answer, revision: 'recovered' })
    expect(call.seen.notice).toBe('Задание создано.')
  })

  it('leaves the rows, notice and busy flag of another supply alone', async () => {
    const call = operator({ success: 'Задание создано.' })
    const result = call.start()
    call.generation.current += 1
    call.answer_()
    await expect(result).resolves.toBeNull()
    expect(call.seen).toEqual({
      workspace: null, stage: 'packing', notice: null, error: null, busy: true, reread: 0,
    })
  })

  // Билет занят уже в новом открытии, поэтому по поколению и по номеру записи
  // ответ проходит. Назвал он при этом прежнюю поставку — её состав на экран
  // открытой поставки не попадает.
  it('refuses an answer that names a supply the operator no longer sees', async () => {
    const call = operator({ success: 'Задание создано.', supply: 'supply-1' })
    const result = call.start()
    call.shownSupplyId.current = 'supply-2'
    call.answer_()
    await expect(result).resolves.toBeNull()
    expect(call.seen.workspace).toBeNull()
    expect(call.seen.notice).toBeNull()
    expect(call.seen.reread).toBe(0)
  })

  it('re-reads the composition silently, without moving the tab or the progress bar', () => {
    const loads: unknown[] = []
    new Function('load', `${asJs('refresh', helpers.refreshAfterLostRace)}; refresh()`)(
      (silent: boolean) => { loads.push(silent); return Promise.resolve() },
    )
    expect(loads).toEqual([true])
  })
})

// «Повторить» — единственная кнопка окна, которая хранит уже собранную операцию
// и переживает закрытие диалогов. После смены поставки её нажатие отправило бы
// запрос по прежней поставке, а ответ лёг бы на состав открытой.
describe('WMS-477 saved «Повторить»', () => {
  it('replays the failed operation inside the same opening', async () => {
    const call = operator({ success: 'Задание создано.' })
    const first = call.start()
    call.fail(new TestApiError('WB не ответил.', true))
    await first
    expect(call.seen.error).toBe('WB не ответил.')
    expect(call.hasRetry()).toBe(true)
    call.retry()
    await flush()
    expect(call.calls()).toBe(2)
    call.answer_()
    await flush()
    expect(call.seen.workspace).toEqual(call.answer)
    expect(call.seen.notice).toBe('Задание создано.')
  })

  it('does not send the previous supply operation after the workspace moved on', async () => {
    const call = operator({ success: 'Задание создано.' })
    const first = call.start()
    call.fail(new TestApiError('WB не ответил.', true))
    await first
    call.generation.current += 1
    call.retry()
    await flush()
    expect(call.calls()).toBe(1)
    expect(call.seen.workspace).toBeNull()
    expect(call.seen.notice).toBeNull()
  })

  it('keeps no retry for a failure the operator cannot repeat', async () => {
    const call = operator({ success: 'Задание создано.' })
    const first = call.start()
    call.fail(new TestApiError('WB отказал по составу поставки.', false))
    await first
    expect(call.seen.error).toBe('WB отказал по составу поставки.')
    expect(call.hasRetry()).toBe(false)
  })
})

// Открытие поставки обязано отдать экран новой поставке целиком. Всё, что осталось
// от прежнего открытия, либо врёт оператору, либо действует по чужой поставке.
describe('WMS-477 opening a supply drops the previous state', () => {
  const reset = () => {
    const run = sandbox(resetEffect, {
      open: true,
      supplyId: 'supply-2',
      initialWorkspace: null,
      load: () => Promise.resolve(),
      visualStage: (stage: string) => stage,
      persistentOperationKey: () => 'delivery-key',
      deliveryKeyRef: { current: '' },
      kizSelectedStickerRef: { current: 'sticker' },
    })
    run.invoke()
    return run.calls
  }

  it('drops the saved retry and the Честный знак dialog with its busy flag', () => {
    const calls = reset()
    expect(calls).toContainEqual(['setRetryAction', null])
    // У открытого окна снятия ЧЗ по занятости отключены обе кнопки и закрытие:
    // оставленная занятость прежней поставки заперла бы оператора в диалоге.
    expect(calls).toContainEqual(['setSkipHonestSignOpen', false])
    expect(calls).toContainEqual(['setSkipHonestSignBusy', false])
    expect(calls).toContainEqual(['setAddOrdersOpen', false])
    expect(calls).toContainEqual(['setAddOrdersBusy', false])
  })

  it('still clears the notice, the error and the scan state of the previous supply', () => {
    const calls = reset()
    expect(calls).toContainEqual(['setNotice', null])
    expect(calls).toContainEqual(['setError', null])
    expect(calls).toContainEqual(['setBusy', false])
    expect(calls).toContainEqual(['setKizScanActive', null])
    expect(calls).toContainEqual(['setKizScanBusy', false])
    expect(calls).toContainEqual(['setKizScanValue', ''])
  })
})

// Снятие требования ЧЗ сохраняется на сервере независимо от гонки, поэтому оно
// само закрывает своё окно и отчитывается. Ответ прежней поставки при этом не
// распоряжается окном открытой.
describe('WMS-477 «Сдать без Честного знака» under crossing requests', () => {
  const skip = (given: { latest: boolean; current: boolean; shown?: string }) => {
    const applied: Array<[string, unknown]> = []
    const run = sandbox(helpers.performSkipHonestSign, {
      workspace: { supply: { id: 'supply-1' } },
      token: 'synthetic',
      authHeaders: () => ({}),
      skipFbsSupplyHonestSign: () => Promise.resolve({ supply: { id: 'supply-1' }, revision: 'answer' }),
      beginWorkspaceWrite: () => ({
        isCurrent: () => given.current,
        isLatest: () => given.latest,
        matchesShownSupply: (next: { supply: { id: string } }) =>
          next.supply.id === (given.shown ?? 'supply-1'),
      }),
      refreshAfterLostRace: () => { applied.push(['refreshAfterLostRace', null]) },
    })
    return (run.invoke() as Promise<void>)
      .then(() => [...applied, ...run.calls] as Array<[string, unknown]>)
  }

  it('applies its own snapshot and closes the dialog when nothing overtook it', async () => {
    const calls = await skip({ latest: true, current: true })
    expect(calls).toContainEqual(['setWorkspace', { supply: { id: 'supply-1' }, revision: 'answer' }])
    expect(calls).toContainEqual(['setSkipHonestSignOpen', false])
    expect(calls).toContainEqual(['setSkipHonestSignBusy', false])
    expect(calls).toContainEqual(['setNotice', 'Требование Честного знака снято со всей поставки.'])
    expect(calls).not.toContainEqual(['refreshAfterLostRace', null])
  })

  // Требование снято на сервере, а на экране остались прежние строки: чтение,
  // начатое позже, могло прочитать базу до записи. Иначе оператор видел бы
  // сообщение об успехе рядом с невыполненным требованием.
  it('re-reads the composition when a newer reader answered first', async () => {
    const calls = await skip({ latest: false, current: true })
    expect(calls).toContainEqual(['refreshAfterLostRace', null])
    expect(calls.some(([name]) => name === 'setWorkspace')).toBe(false)
    expect(calls).toContainEqual(['setSkipHonestSignOpen', false])
    expect(calls).toContainEqual(['setNotice', 'Требование Честного знака снято со всей поставки.'])
  })

  // Позднему ответу прежней поставки принадлежит только её собственное окно;
  // состояние открытой поставки задаёт переход, а не этот ответ.
  it('touches neither the dialog nor the busy flag of the supply opened meanwhile', async () => {
    const calls = await skip({ latest: false, current: false })
    expect(calls).toEqual([['setSkipHonestSignBusy', true], ['setError', null]])
  })

  it('ignores an answer that describes the previous supply', async () => {
    const calls = await skip({ latest: true, current: true, shown: 'supply-2' })
    expect(calls.some(([name]) => name === 'setWorkspace')).toBe(false)
    expect(calls.some(([name]) => name === 'setNotice')).toBe(false)
    expect(calls).toContainEqual(['setSkipHonestSignBusy', false])
  })
})

describe('WMS-477 «Добавить заказы» under crossing requests', () => {
  const answer = { supply: { id: 'supply-1', marketplace: 'wb' }, stage: 'picking', revision: 'answer' }
  const add = (given: { latest: boolean; current: boolean; shown?: string }) => {
    const applied: Array<[string, unknown]> = []
    const run = sandbox(helpers.addOrdersToCurrentSupply, {
      workspace: { supply: { id: 'supply-1' } },
      addableSelected: new Set(['order-1']),
      token: 'synthetic',
      authHeaders: () => ({}),
      createFbsIdempotencyKey: () => 'synthetic-key',
      addFbsOrdersToSupply: () => Promise.resolve(answer),
      beginWorkspaceWrite: () => ({
        isCurrent: () => given.current,
        isLatest: () => given.latest,
        matchesShownSupply: (next: { supply: { id: string } }) =>
          next.supply.id === (given.shown ?? 'supply-1'),
      }),
      refreshAfterLostRace: () => { applied.push(['refreshAfterLostRace', null]) },
    })
    return (run.invoke() as Promise<void>)
      .then(() => [...applied, ...run.calls] as Array<[string, unknown]>)
  }

  it('applies its own snapshot and closes the dialog when nothing overtook it', async () => {
    const calls = await add({ latest: true, current: true })
    expect(calls).toContainEqual(['setWorkspace', answer])
    expect(calls).toContainEqual(['setAddOrdersOpen', false])
    expect(calls).toContainEqual(['setNotice', 'Заказы добавлены в поставку.'])
    expect(calls).not.toContainEqual(['refreshAfterLostRace', null])
  })

  // Заказы уже в поставке, а на экране их ещё нет: чтение, начатое позже записи,
  // могло прочитать базу до неё. Без нового чтения оператор увидел бы сообщение
  // об успехе над прежним составом и добавил бы те же заказы второй раз.
  it('re-reads the composition when a newer reader answered first', async () => {
    const calls = await add({ latest: false, current: true })
    expect(calls).toContainEqual(['refreshAfterLostRace', null])
    expect(calls.some(([name]) => name === 'setWorkspace')).toBe(false)
    expect(calls.some(([name]) => name === 'setStage')).toBe(false)
    expect(calls).toContainEqual(['setAddOrdersOpen', false])
    expect(calls).toContainEqual(['setNotice', 'Заказы добавлены в поставку.'])
  })

  it('ignores an answer that describes the previous supply', async () => {
    const calls = await add({ latest: true, current: true, shown: 'supply-2' })
    expect(calls.some(([name]) => name === 'setWorkspace')).toBe(false)
    expect(calls.some(([name]) => name === 'setNotice')).toBe(false)
    expect(calls).toContainEqual(['setAddOrdersBusy', false])
  })

  it('touches neither the dialog nor the busy flag of the supply opened meanwhile', async () => {
    const calls = await add({ latest: false, current: false })
    expect(calls).toEqual([['setAddOrdersBusy', true], ['setError', null]])
  })
})

// Итог ручной проверки проверяется не «в принципе», а на настоящем пересечении
// запросов: нажатие заняло номер раньше тихого чтения, а ответило позже него.
// Здесь связаны настоящие обработчик кнопки, run(), refreshAfterLostRace(), load()
// и продуктовый счётчик; порядок ответов POST и GET задаёт тест.
describe('WMS-477 «Проверено в WB» after the manual check crossed a silent read', () => {
  const snapshot = (status: string, revision: string) => ({
    supply: { id: 'supply-1', marketplace: 'wb' },
    stage: 'packing',
    revision,
    orders: [{
      id: 'order-1',
      metadata: {
        required: ['sgtin'], optional: [], delivery_allowed: status === 'accepted',
        last_checked_at: null,
        states: [{ kind: 'sgtin', status, reason: null, value_tail: 'QA-CODE' }],
      },
    }],
  })

  function screen() {
    const generation = { current: 1 }
    const writeSeq = { current: 0 }
    const shownSupplyId = { current: 'supply-1' as string | null }
    const onScreen = snapshot('pending', 'initial')
    const seen = {
      workspace: onScreen as unknown, stage: 'packing',
      notice: null as string | null, error: null as string | null, busy: false,
    }
    const reads: Array<{ resolve: (value: unknown) => void; reject: (cause: unknown) => void }> = []
    const posts: Array<{ resolve: (value: unknown) => void; reject: (cause: unknown) => void }> = []
    const journal: string[] = []
    const beginWorkspaceWrite = (new Function('workspaceOpenGeneration', 'workspaceWriteSeq',
      'shownSupplyId',
      `${asJs('beginWorkspaceWrite', helpers.beginWorkspaceWrite)}; return beginWorkspaceWrite`) as (
      ...args: unknown[]) => () => unknown)(generation, writeSeq, shownSupplyId)
    // Показанную поставку экран ведёт эффектом вслед за применённым снимком.
    const setWorkspace = (next: { supply: { id: string } }) => {
      seen.workspace = next
      shownSupplyId.current = next.supply.id
    }
    const setStage = (update: (previous: string) => string) => { seen.stage = update(seen.stage) }
    const setError = (next: string | null) => { seen.error = next }
    const setBusy = (next: boolean) => { seen.busy = next }
    const keepStage = (_marketplace: string, _current: string, next: string) => next
    const same = (value: string) => value
    const load = (new Function('fetchFbsWorkspace', 'beginWorkspaceWrite', 'setWorkspace', 'setStage',
      'setError', 'setBusy', 'fbsErrorText', 'fbsStageAfterWorkspaceRefresh', 'visualStage',
      'open', 'supplyId', 'token', 'authHeaders', `${asJs('load', helpers.load)}; return load`) as (
      ...args: unknown[]) => (silent?: boolean, onApplied?: (fresh: unknown) => void) => Promise<unknown>)(
      () => {
        journal.push('GET')
        return new Promise((resolve, reject) => { reads.push({ resolve, reject }) })
      },
      beginWorkspaceWrite, setWorkspace, setStage, setError, setBusy, same, keepStage, same,
      true, 'supply-1', 'synthetic', () => ({}),
    )
    const refreshAfterLostRace = (new Function('load',
      `${asJs('refreshAfterLostRace', helpers.refreshAfterLostRace)}; return refreshAfterLostRace`) as (
      load: unknown) => (onApplied?: (fresh: unknown) => void) => void)(load)
    const run = (new Function(
      'beginWorkspaceWrite', 'refreshAfterLostRace', 'setBusy', 'setError', 'setNotice',
      'setRetryAction', 'setWorkspace', 'setStage', 'fbsStageAfterWorkspaceRefresh', 'visualStage',
      'FbsApiError', 'fbsErrorText', `${asJs('run', runSource)}; return run`) as (
      ...args: unknown[]) => unknown)(
      beginWorkspaceWrite, refreshAfterLostRace, setBusy, setError,
      (next: string | null) => { seen.notice = next }, () => {}, setWorkspace, setStage,
      keepStage, same, TestApiError, same,
    )
    const press = (new Function('workspace', 'run', 'syncFbsSupplyMarkings', 'token', 'authHeaders',
      'fbsMarkingVerdictsSummary',
      `${asJs('checkMarkingsInWb', helpers.checkMarkingsInWb)}; return checkMarkingsInWb`) as (
      ...args: unknown[]) => () => void)(
      onScreen, run,
      () => {
        journal.push('POST')
        return new Promise((resolve, reject) => { posts.push({ resolve, reject }) })
      },
      'synthetic', () => ({}), fbsMarkingVerdictsSummary,
    )
    return {
      seen, generation, journal, press,
      // Тик тихого обновления: занимает свой номер записи в момент вызова.
      silentRead: () => { void load(true); return reads.length - 1 },
      answerPost: (value: unknown) => { posts.shift()!.resolve(value) },
      answerRead: (index: number, value: unknown) => { reads[index].resolve(value) },
      failRead: (index: number) => { reads[index].reject(new Error('network down')) },
      reads: () => reads.length,
    }
  }
  // Номер восстановительного чтения: тихое чтение теста — 0, его просит сам экран.
  const recovery = 1

  it('names the result by the read that actually reached the screen', async () => {
    const s = screen()
    s.press()
    expect(s.seen.busy).toBe(true)
    const stale = s.silentRead()
    s.answerPost(snapshot('accepted', 'write'))
    await flush()
    // Свой снимок отброшен, поэтому счётчик по нему не называется; оператор при
    // этом не заперт ожиданием восстановительного чтения.
    expect(s.seen.notice).toBeNull()
    expect(s.seen.busy).toBe(false)
    expect(s.reads()).toBe(2)
    s.answerRead(stale, snapshot('pending', 'stale'))
    await flush()
    expect(s.seen.workspace).toMatchObject({ revision: 'initial' })
    expect(s.seen.notice).toBeNull()
    s.answerRead(recovery, snapshot('accepted', 'recovered'))
    await flush()
    expect(s.seen.workspace).toMatchObject({ revision: 'recovered' })
    expect(s.seen.notice).toBe('Проверено в WB: подтверждено 1 из 1.')
    // Состав восстановлен чтением, а не повторной записью в WB.
    expect(s.journal).toEqual(['POST', 'GET', 'GET'])
  })

  it('says nothing when a newer rejected verdict reached the screen instead', async () => {
    const s = screen()
    s.press()
    const stale = s.silentRead()
    s.answerPost(snapshot('accepted', 'write'))
    await flush()
    // Следующий тик читает базу уже после того, как WB отказал коду.
    const newer = s.silentRead()
    s.answerRead(newer, snapshot('rejected', 'newer'))
    await flush()
    expect(s.seen.workspace).toMatchObject({ revision: 'newer' })
    s.answerRead(recovery, snapshot('accepted', 'recovered'))
    await flush()
    s.answerRead(stale, snapshot('pending', 'stale'))
    await flush()
    // На экране отказ, поэтому «подтверждено 1 из 1» рядом с ним не появляется.
    expect(s.seen.workspace).toMatchObject({ revision: 'newer' })
    expect(s.seen.notice).toBeNull()
  })

  it('does not claim success when the recovery read itself failed', async () => {
    const s = screen()
    s.press()
    s.silentRead()
    s.answerPost(snapshot('accepted', 'write'))
    await flush()
    s.failRead(recovery)
    await flush()
    expect(s.seen.notice).toBeNull()
    // Сорванное тихое чтение не бросает оператору красную ошибку и не запирает
    // кнопку: повтор — то же самое нажатие, рядом идёт обычный тик обновления.
    expect(s.seen.error).toBeNull()
    expect(s.seen.busy).toBe(false)
  })

  it('does not carry the result into a supply the operator opened meanwhile', async () => {
    const s = screen()
    s.press()
    s.silentRead()
    s.answerPost(snapshot('accepted', 'write'))
    await flush()
    s.generation.current += 1
    s.answerRead(recovery, snapshot('accepted', 'recovered'))
    await flush()
    expect(s.seen.notice).toBeNull()
    expect(s.seen.workspace).toMatchObject({ revision: 'initial' })
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
