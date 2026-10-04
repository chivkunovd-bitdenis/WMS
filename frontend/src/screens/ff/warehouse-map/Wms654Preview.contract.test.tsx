// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ThemeProvider } from '@mui/material'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { muiTheme } from '../../../mui/theme'
import { PreviewHarness } from './preview'

// WMS-654 — контракт первого, макетного этапа. Тестируется именно автономное
// React-превью «Карты склада»: рабочий FfWarehouseMapPage и его API в этой задаче
// меняться не должны. Значения разделителей намеренно не зафиксированы точнее
// постановки — макет должен показать их владельцу до продуктовой реализации.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  if (typeof Element.prototype.scrollIntoView !== 'function') {
    Element.prototype.scrollIntoView = function scrollIntoView() {}
  }
})

let root: Root | null = null
let host: HTMLDivElement | null = null

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function mountPreview() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <ThemeProvider theme={muiTheme}>
        <PreviewHarness />
      </ThemeProvider>,
    )
  })
  await settle()
}

async function unmountPreview() {
  if (root) {
    await act(async () => root!.unmount())
  }
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
}

function mustTestId(testId: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`)
  if (!element) throw new Error(`На макете нет data-testid="${testId}"`)
  return element
}

async function click(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
  await settle()
}

function fieldByLabel(label: string): HTMLInputElement | HTMLSelectElement {
  const labels = Array.from(document.querySelectorAll<HTMLLabelElement>('label[for]'))
  const fieldLabel = labels.find((candidate) => candidate.textContent?.trim().startsWith(label))
  const inputId = fieldLabel?.htmlFor
  const field = inputId
    ? document.getElementById(inputId)
    : null
  if (!(field instanceof HTMLInputElement) && !(field instanceof HTMLSelectElement)) {
    throw new Error(`На макете нет поля «${label}»`)
  }
  return field
}

function switchByLabel(label: string): HTMLInputElement {
  const controlLabel = Array.from(document.querySelectorAll<HTMLLabelElement>('label')).find(
    (candidate) => candidate.textContent?.trim() === label,
  )
  const input = controlLabel?.querySelector<HTMLInputElement>('input[type="checkbox"]')
  if (!input) throw new Error(`На макете нет флажка «${label}»`)
  return input
}

async function changeValue(
  field: HTMLInputElement | HTMLSelectElement,
  value: string,
) {
  const prototype = field instanceof HTMLSelectElement
    ? HTMLSelectElement.prototype
    : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  if (!setter) throw new Error('DOM не позволяет изменить значение поля')
  await act(async () => {
    setter.call(field, value)
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? 'change' : 'input', {
      bubbles: true,
    }))
  })
  await settle()
}

async function setSwitch(label: string, checked: boolean) {
  const input = switchByLabel(label)
  if (input.checked !== checked) await click(input)
  expect(switchByLabel(label).checked).toBe(checked)
}

async function openCreateDialog() {
  await click(mustTestId('warehouse-map-create-cell'))
  expect(mustTestId('warehouse-map-cell-dialog')).toBeTruthy()
}

async function configureDimensions(useSides: boolean, useTiers: boolean) {
  await setSwitch('Учитывать стороны', useSides)
  await setSwitch('Учитывать ярусы', useTiers)
}

async function fillBase(rack = 'Р', position = '90') {
  await changeValue(fieldByLabel('Стеллаж'), rack)
  await changeValue(fieldByLabel('Позиция'), position)
}

function previewCode(): string {
  const text = mustTestId('warehouse-map-cell-preview').textContent?.trim() ?? ''
  return text.replace(/^[^:]+:\s*/, '')
}

function expectPartsInOrder(code: string, parts: string[]) {
  let cursor = -1
  for (const part of parts) {
    const next = code.indexOf(part, cursor + 1)
    expect(next, `«${part}» должно идти после предыдущей части в «${code}»`).toBeGreaterThan(cursor)
    cursor = next
  }
}

function positionHint(): string {
  const position = fieldByLabel('Позиция')
  const describedBy = position.getAttribute('aria-describedby')?.split(/\s+/).filter(Boolean) ?? []
  return describedBy
    .map((id) => document.getElementById(id)?.textContent?.trim() ?? '')
    .filter(Boolean)
    .join(' ')
}

function cellRows(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-row-key^="cell-"]'))
    .map((row) => `${row.dataset.rowKey}:${row.textContent?.replace(/\s+/g, ' ').trim()}`)
}

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })))
  await mountPreview()
})

afterEach(async () => {
  await unmountPreview()
  vi.unstubAllGlobals()
})

describe('WMS-654: настраиваемые части адреса в React-макете', () => {
  it('C2: без сторон и ярусов остаются только ряд и позиция', async () => {
    await openCreateDialog()
    await configureDimensions(false, false)
    await fillBase()

    expect(() => fieldByLabel('Сторона')).toThrow()
    expect(() => fieldByLabel('Ярус')).toThrow()
    expect(previewCode()).toMatch(/^Р[ .]+90$/)
  })

  it('C3: только сторона даёт выбор 1/2 и порядок ряд — сторона — позиция', async () => {
    await openCreateDialog()
    await configureDimensions(true, false)
    await fillBase()
    expect(() => fieldByLabel('Ярус')).toThrow()

    await changeValue(fieldByLabel('Сторона'), '1')
    expectPartsInOrder(previewCode(), ['Р', '1', '90'])
    await changeValue(fieldByLabel('Сторона'), '2')
    expectPartsInOrder(previewCode(), ['Р', '2', '90'])
    expect(previewCode()).not.toContain('7')
  })

  it('C4: только ярус даёт порядок ряд — ярус — позиция без поля стороны', async () => {
    await openCreateDialog()
    await configureDimensions(false, true)
    await changeValue(fieldByLabel('Ярус'), '7')
    await fillBase()

    expect(() => fieldByLabel('Сторона')).toThrow()
    expectPartsInOrder(previewCode(), ['Р', '7', '90'])
  })

  it('C5: сторона и ярус входят в адрес в согласованном порядке и стиле', async () => {
    await openCreateDialog()
    await configureDimensions(true, true)
    await changeValue(fieldByLabel('Сторона'), '2')
    await changeValue(fieldByLabel('Ярус'), '7')
    await fillBase()

    const code = previewCode()
    expectPartsInOrder(code, ['Р', '2', '7', '90'])
    // Действующие адреса используют пробел и точку. Точный выбор разделителя
    // между новыми частями остаётся видимым решением макета, а не теста.
    expect(code).toMatch(/^Р[ .]+2[ .]+7[ .]+90$/)
  })

  it('C6: флажки независимы и сразу добавляют либо убирают только свою часть', async () => {
    await openCreateDialog()
    await configureDimensions(true, true)
    await changeValue(fieldByLabel('Сторона'), '2')
    await changeValue(fieldByLabel('Ярус'), '7')
    await fillBase()

    await setSwitch('Учитывать стороны', false)
    expect(switchByLabel('Учитывать ярусы').checked).toBe(true)
    expect(() => fieldByLabel('Сторона')).toThrow()
    expectPartsInOrder(previewCode(), ['Р', '7', '90'])
    expect(previewCode()).not.toContain('2')

    await setSwitch('Учитывать стороны', true)
    expect(fieldByLabel('Сторона')).toBeTruthy()
    await changeValue(fieldByLabel('Сторона'), '2')
    expectPartsInOrder(previewCode(), ['Р', '2', '7', '90'])

    await setSwitch('Учитывать ярусы', false)
    expect(switchByLabel('Учитывать стороны').checked).toBe(true)
    expect(() => fieldByLabel('Ярус')).toThrow()
    expectPartsInOrder(previewCode(), ['Р', '2', '90'])
    expect(previewCode()).not.toContain('7')
  })

  it('C7: подсказка позиции различает все четыре контекста адреса', async () => {
    await openCreateDialog()
    await changeValue(fieldByLabel('Стеллаж'), 'Ж')

    const suggestions: string[] = []
    for (const [useSides, useTiers] of [
      [false, false],
      [true, false],
      [false, true],
      [true, true],
    ] as const) {
      await configureDimensions(useSides, useTiers)
      if (useSides) await changeValue(fieldByLabel('Сторона'), '2')
      if (useTiers) await changeValue(fieldByLabel('Ярус'), '7')
      const hint = positionHint()
      expect(hint).not.toBe('')
      // Макет волен показать контекст в тексте подсказки либо самим
      // демонстрационным номером. Важно, чтобы оператор видел различие всех
      // четырёх сочетаний и чтобы оно не зависело от рабочего API.
      suggestions.push(`${fieldByLabel('Позиция').value}|${hint}`)
    }

    expect(new Set(suggestions).size).toBe(4)
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('C8: действия макета не вызывают API и не меняют ячейки, коды и штрихкоды', async () => {
    const before = cellRows()
    expect(before.length).toBeGreaterThan(0)

    await openCreateDialog()
    for (const [useSides, useTiers] of [
      [false, false],
      [true, false],
      [false, true],
      [true, true],
    ] as const) {
      await configureDimensions(useSides, useTiers)
    }
    await changeValue(fieldByLabel('Сторона'), '2')
    await changeValue(fieldByLabel('Ярус'), '7')
    await fillBase('Ж', '90')
    await click(mustTestId('warehouse-map-cell-submit'))

    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
    expect(cellRows()).toEqual(before)

    await openCreateDialog()
    await click(mustTestId('warehouse-map-cell-cancel'))
    expect(cellRows()).toEqual(before)

    await unmountPreview()
    await mountPreview()
    expect(cellRows()).toEqual(before)
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })
})
