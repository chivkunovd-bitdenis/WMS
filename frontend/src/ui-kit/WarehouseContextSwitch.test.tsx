import { Children, isValidElement, type ReactElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  WarehouseContextSwitch,
  type WarehouseContextSwitchProps,
} from './WarehouseContextSwitch'
import { WarningNotice } from './WarningNotice'

const hookState = vi.hoisted(() => ({ anchorEl: null as HTMLElement | null }))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useState: () => [
      hookState.anchorEl,
      (value: HTMLElement | null) => {
        hookState.anchorEl = value
      },
    ],
  }
})

type TestElementProps = {
  children?: ReactNode
  disabled?: boolean
  open?: boolean
  severity?: string
  onClick?: (event: { currentTarget: HTMLElement }) => void
  'aria-expanded'?: boolean
  'data-testid'?: string
}

const options = [
  { id: 'north', name: 'Склад Север' },
  { id: 'south', name: 'Склад Юг' },
]

function renderSwitch(props: WarehouseContextSwitchProps): ReactNode {
  return WarehouseContextSwitch(props)
}

function findByTestId(node: ReactNode, testId: string): ReactElement<TestElementProps> | null {
  if (!isValidElement<TestElementProps>(node)) return null
  if (node.props['data-testid'] === testId) return node

  for (const child of Children.toArray(node.props.children)) {
    const match = findByTestId(child, testId)
    if (match) return match
  }
  return null
}

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!isValidElement<TestElementProps>(node)) return ''
  return Children.toArray(node.props.children).map(textContent).join('')
}

describe('WarehouseContextSwitch', () => {
  beforeEach(() => {
    hookState.anchorEl = null
  })

  it('does not render for an empty warehouse list so the screen can show its empty state', () => {
    expect(renderSwitch({ options: [], value: null, onChange: vi.fn() })).toBeNull()
  })

  it('does not render for one warehouse', () => {
    expect(renderSwitch({ options: [options[0]], value: 'north', onChange: vi.fn() })).toBeNull()
  })

  it('opens, shows names only, changes immediately, and closes', () => {
    const onChange = vi.fn()
    const props = { options, value: 'north', onChange, testId: 'warehouse' }
    const closedTree = renderSwitch(props)
    const button = findByTestId(closedTree, 'warehouse-button')
    expect(button?.props['aria-expanded']).toBe(false)

    const anchor = {} as HTMLElement
    button?.props.onClick?.({ currentTarget: anchor })
    const openTree = renderSwitch(props)
    const menu = findByTestId(openTree, 'warehouse-menu')
    expect(menu?.props.open).toBe(true)
    expect(textContent(findByTestId(openTree, 'warehouse-option-north'))).toBe('Склад Север')
    expect(textContent(findByTestId(openTree, 'warehouse-option-south'))).toBe('Склад Юг')
    expect(textContent(menu)).not.toContain('north')
    expect(textContent(menu)).not.toContain('south')

    findByTestId(openTree, 'warehouse-option-south')?.props.onClick?.({ currentTarget: anchor })
    expect(onChange).toHaveBeenCalledWith('south')
    expect(findByTestId(renderSwitch(props), 'warehouse-menu')?.props.open).toBe(false)
  })

  it('shows the loading reason and disables the action', () => {
    const tree = renderSwitch({ options, value: null, onChange: vi.fn(), loading: true, testId: 'warehouse' })
    const button = findByTestId(tree, 'warehouse-button')
    expect(button?.props.disabled).toBe(true)
    expect(textContent(tree)).toContain('Загружаем склады')
  })

  it('shows the disabled reason and keeps the menu closed', () => {
    const tree = renderSwitch({
      options,
      value: 'north',
      onChange: vi.fn(),
      disabledReason: 'Склад закреплён: подбор уже начат',
      testId: 'warehouse',
    })
    const button = findByTestId(tree, 'warehouse-button')
    expect(button?.props.disabled).toBe(true)
    expect(textContent(tree)).toContain('Склад закреплён: подбор уже начат')
    expect(findByTestId(tree, 'warehouse-menu')?.props.open).toBe(false)
  })

  it('shows an operator-facing error without exposing a selectable action', () => {
    const tree = renderSwitch({
      options: [],
      value: null,
      onChange: vi.fn(),
      error: 'Не удалось загрузить склады. Обновите страницу.',
      testId: 'warehouse-error',
    })
    expect(textContent(tree)).toContain('Не удалось загрузить склады')
    expect(findByTestId(tree, 'warehouse-button')).toBeNull()
  })

  it('renders a non-blocking warning notice', () => {
    const notice = WarningNotice({
      children: 'Нужно подобрать товары с другого склада',
      testId: 'warehouse-warning',
    })
    expect(notice.props.severity).toBe('warning')
    expect(textContent(notice)).toBe('Нужно подобрать товары с другого склада')
    expect(notice.props.disabled).toBeUndefined()
  })
})
