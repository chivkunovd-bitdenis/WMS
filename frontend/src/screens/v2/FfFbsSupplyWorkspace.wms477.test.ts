// WMS-477 разбирается прямо из исходника экрана, потому что в проекте нет jsdom и
// отрисовать компонент в тесте нечем. Проверяется контракт тихого обновления — на
// каких вкладках таймер живёт, как часто ходит, что делает при скрытом окне и
// снимается ли при закрытии — и условия показа кнопки «Проверить в WB».
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

let effect = ''
let deps = ''
let button: ts.JsxElement | null = null
function visit(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(file) === 'useEffect'
    && node.getText(file).includes('setInterval')) {
    effect = node.arguments[0].getText(file)
    deps = node.arguments[1].getText(file)
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
if (!button) throw new Error('«Проверить в WB» button not found')

const attribute = (name: string) => attributeOf(button!, name)

/** Условие, под которым кнопка вообще попадает на экран. */
function renderCondition(node: ts.Node): string {
  if (ts.isConditionalExpression(node)) return node.condition.getText(file)
  if (!node.parent) throw new Error('«Проверить в WB» button is rendered unconditionally')
  return renderCondition(node.parent)
}

/** Исполняет тело эффекта на подставных зависимостях и возвращает то, что оно сделало. */
function runEffect(options: { open: boolean; supplyId: string; stage: string; visibility: string }) {
  const loads: boolean[] = []
  let tick: (() => void) | null = null
  let cleared: number | null = null
  const factory = new Function('open', 'supplyId', 'stage', 'load', 'window', 'document',
    `return (${effect})()`) as (...args: unknown[]) => (() => void) | undefined
  const cleanup = factory(
    options.open, options.supplyId, options.stage,
    (silent: boolean) => { loads.push(silent); return Promise.resolve() },
    {
      setInterval: (callback: () => void, delay: number) => { tick = callback; return delay },
      clearInterval: (timer: number) => { cleared = timer },
    },
    { get visibilityState() { return options.visibility } },
  )
  return { loads, tick: () => tick?.(), cleanup, cleared: () => cleared }
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

  // Пропажа зависимости оставила бы таймер с устаревшим load или не сняла бы его
  // при закрытии окна — оба случая означают запросы по уже закрытой поставке.
  it('re-arms the timer on every input it reads', () => {
    expect(deps).toBe('[open, supplyId, stage, load]')
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
