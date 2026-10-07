// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { CreateCellDialog } from './WarehouseMapToolbar'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
  root = null
  host = null
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

async function renderDialog(onCreate: ReturnType<typeof vi.fn>) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <CreateCellDialog
        open
        legacyCreateCell
        warehouseName="Основной"
        existingCodes={['А 1.9']}
        onCreate={onCreate}
        onClose={vi.fn()}
      />,
    )
  })
}

function field(label: string): HTMLInputElement | null {
  const labels = [...document.querySelectorAll<HTMLLabelElement>('label')]
  const found = labels.find((element) => element.textContent?.replace(/\s*\*$/, '').trim() === label)
  return (found?.control ?? found?.querySelector('input')) as HTMLInputElement | null ?? null
}

async function input(element: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function click(element: Element | null) {
  expect(element, 'Visible action must be present').not.toBeNull()
  await act(async () => (element as HTMLElement).click())
}

describe('WMS-654 legacy CreateCellDialog contract', () => {
  it('C11 keeps the side-only address and next automatic position for string callers', async () => {
    const onCreate = vi.fn()
    await renderDialog(onCreate)

    const rack = field('Стеллаж')
    expect(rack, 'Legacy form must expose rack input').not.toBeNull()
    await input(rack!, 'А')

    await click(document.querySelector('[data-testid="warehouse-map-cell-submit"]'))
    expect(onCreate).toHaveBeenCalledWith('А 1.10')

    expect(field('Ярус')).toBeNull()
    expect(document.querySelector('[data-testid="wms-654-use-sides"]')).toBeNull()
    expect(document.querySelector('[data-testid="wms-654-use-tiers"]')).toBeNull()
    expect(field('Сторона')?.value).toBe('1')
    expect(field('Позиция')?.value).toBe('10')
  })
})
