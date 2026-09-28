import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { fbsMenuReprintRequest, hasOperatorKiz } from './fbsMenuReprint'

// WMS-575, R10 — меню ⋮ → «Перепечатать» в строке заказа упаковки.
// Код оператора, который WB ещё не подтвердил, после хотфикса уходил в печать
// без перепечатки, и сервер отвечал operator_kiz_print_forbidden. Проверяются
// и чистое правило, и то, что сам пункт меню экрана зовёт печать по нему.

type State = { id?: string; kind: string; status: string; source?: string | null; value_tail: string | null; reason: null }
const orderWith = (state: State) => ({ metadata: { states: [state] } }) as Parameters<typeof fbsMenuReprintRequest>[0]

// Так состояние приходит в ответе /workspace: схема ответа сервера не отдаёт id
// кода (FbsWorklistMetadataStateOut), поэтому правило обязано работать без него.
const operatorPending: State = { kind: 'sgtin', status: 'pending', source: 'operator', value_tail: 'AbCd1234', reason: null }
const operatorAccepted: State = { ...operatorPending, status: 'accepted' }
const operatorRejected: State = { ...operatorPending, status: 'rejected' }
const operatorPendingWithId: State = { ...operatorPending, id: 'mark-op' }
const poolAccepted: State = { kind: 'sgtin', status: 'accepted', source: 'pool', value_tail: 'PoOl5678', reason: null }
const cleared: State = { kind: 'sgtin', status: 'missing', source: null, value_tail: null, reason: null }

describe('WMS-575 R10 · правило «Перепечатать» из меню', () => {
  it('код оператора WB, не подтверждённый WB, — перепечатка этого кода, а не печать без перепечатки', () => {
    expect(fbsMenuReprintRequest(orderWith(operatorPending), 'wb', false)).toEqual({ reprint: true })
  })

  it('код оператора WB с известным id — точная копия этого кода, как круговая стрелка «Перепечатать ЧЗ»', () => {
    expect(fbsMenuReprintRequest(orderWith(operatorPendingWithId), 'wb', false)).toEqual({ reprint: true, reprintMarkingId: 'mark-op' })
  })

  it('подтверждённый код оператора — перепечатка, как и было', () => {
    expect(fbsMenuReprintRequest(orderWith(operatorAccepted), 'wb', true)).toEqual({ reprint: true })
  })

  it('код оператора, отклонённый WB, — как после хотфикса (сервер его действующим не считает)', () => {
    expect(fbsMenuReprintRequest(orderWith(operatorRejected), 'wb', false)).toEqual({ reprint: false })
  })

  it('напечатанный заказ с кодом из пула — перепечатка той же ленты, как после хотфикса', () => {
    expect(fbsMenuReprintRequest(orderWith(poolAccepted), 'wb', true)).toEqual({ reprint: true })
  })

  it('заказ без кода после «Очистить ЧЗ» — печать с новым кодом, как после хотфикса', () => {
    expect(fbsMenuReprintRequest(orderWith(cleared), 'wb', false)).toEqual({ reprint: false })
  })

  it('Ozon не меняется: флаг — «заказ напечатан»', () => {
    expect(fbsMenuReprintRequest(orderWith(operatorPending), 'ozon', false)).toEqual({ reprint: false })
    expect(fbsMenuReprintRequest(orderWith(operatorPending), 'ozon', true)).toEqual({ reprint: true })
  })

  it('круговая стрелка «Перепечатать ЧЗ» требует id кода — без него её не видно (WMS-519)', () => {
    expect(hasOperatorKiz(operatorPending as never, 'wb')).toBe(false)
    expect(hasOperatorKiz(operatorPendingWithId as never, 'wb')).toBe(true)
  })
})

// Пункт меню берётся из исходника экрана и исполняется как есть: подменены
// только данные строки и функция печати, которая записывает свои аргументы.
const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const file = ts.createSourceFile('workspace.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)

function reprintMenuOnClick(): string {
  let found = ''
  const visit = (node: ts.Node) => {
    if (found) return
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(file) === 'MenuItem') {
      const attributes = node.openingElement.attributes.properties
      const isReprint = attributes.some((attribute) => ts.isJsxAttribute(attribute)
        && attribute.name.getText(file) === 'data-task-id'
        && attribute.initializer?.getText(file) === '"FBS-11"')
      const onClick = attributes.find((attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText(file) === 'onClick')
      if (isReprint && onClick && ts.isJsxAttribute(onClick) && onClick.initializer && ts.isJsxExpression(onClick.initializer)) {
        found = onClick.initializer.expression!.getText(file)
        return
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  if (!found) throw new Error('Пункт меню «Перепечатать» (FBS-11) не найден')
  return found
}

function pressReprint(order: object, options: { isOzon: boolean; printDone: boolean }) {
  const printed: unknown[][] = []
  const js = ts.transpileModule(`const handler = ${reprintMenuOnClick()}`, {
    compilerOptions: { target: ts.ScriptTarget.ESNext },
  }).outputText
  const handler = new Function(
    'reprintOrder', 'reprintLine', 'isOzonSupply', 'orderPrintDone', 'openOrderMarkingPrint',
    'setReprintMenu', 'fbsMenuReprintRequest', `${js}; return handler`,
  )(
    order, { id: 'line-1' }, options.isOzon, () => options.printDone,
    (...args: unknown[]) => { printed.push(args) }, () => undefined, fbsMenuReprintRequest,
  ) as () => void
  handler()
  return printed
}

describe('WMS-575 R10 · пункт меню «Перепечатать» зовёт печать по правилу', () => {
  it('код оператора в ожидании WB: печать с перепечаткой, а не без неё', () => {
    const order = orderWith(operatorPending)
    const printed = pressReprint(order, { isOzon: false, printDone: false })
    expect(printed).toHaveLength(1)
    expect(printed[0]!.slice(0, 3)).toEqual([order, { id: 'line-1' }, true])
  })

  it('код оператора с известным id: перепечатка и id именно этого кода', () => {
    const order = orderWith(operatorPendingWithId)
    expect(pressReprint(order, { isOzon: false, printDone: false })).toEqual([[order, { id: 'line-1' }, true, 'mark-op']])
  })

  it('после «Очистить ЧЗ»: печать без перепечатки, новый код', () => {
    const order = orderWith(cleared)
    const printed = pressReprint(order, { isOzon: false, printDone: false })
    expect(printed).toHaveLength(1)
    expect(printed[0]!.slice(0, 3)).toEqual([order, { id: 'line-1' }, false])
    expect(printed[0]![3]).toBeUndefined()
  })
})
