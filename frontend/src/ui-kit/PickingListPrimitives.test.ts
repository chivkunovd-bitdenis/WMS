import type { ReactElement, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { PrintAction } from './Actions'
import { CheckCell } from './Cells'
import { ChoiceFilter } from './FilterBar'
import { ModalFrame } from './ModalFrame'

type DialogElementProps = {
  disableEscapeKeyDown: boolean
  'aria-busy': boolean
  onClose: (event: unknown, reason: unknown) => void
}

type TooltipElementProps = {
  title: ReactNode
  children: ReactElement<{ children: ReactElement<Record<string, unknown>> }>
}

describe('picking list UI-kit primitives', () => {
  it('does not close ModalFrame while it is busy', () => {
    const onClose = vi.fn()
    const busyFrame = ModalFrame({
      open: true,
      title: 'Лист подбора',
      busy: true,
      onClose,
      actions: null,
      children: null,
    }) as ReactElement<DialogElementProps>

    expect(busyFrame.props.disableEscapeKeyDown).toBe(true)
    expect(busyFrame.props['aria-busy']).toBe(true)
    busyFrame.props.onClose({}, 'backdropClick')
    expect(onClose).not.toHaveBeenCalled()

    const readyFrame = ModalFrame({
      open: true,
      title: 'Лист подбора',
      onClose,
      actions: null,
      children: null,
    }) as ReactElement<DialogElementProps>

    readyFrame.props.onClose({}, 'escapeKeyDown')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('keeps ChoiceFilter interactive and exposes its disabled reason', () => {
    const onChange = vi.fn()
    const readyFilter = ChoiceFilter({
      value: 'all',
      options: [
        { value: 'all', label: 'Все' },
        { value: 'unpicked', label: 'Не собраны' },
      ],
      onChange,
      ariaLabel: 'Фильтр листа',
    }) as ReactElement<TooltipElementProps>
    const readyGroup = readyFilter.props.children.props.children
    const readyButtons = readyGroup.props.children as ReactElement<{
      disabled: boolean
      'aria-pressed': boolean
      onClick: () => void
    }>[]

    expect(readyButtons[0].props['aria-pressed']).toBe(true)
    expect(readyButtons[1].props.disabled).toBe(false)
    readyButtons[1].props.onClick()
    expect(onChange).toHaveBeenCalledWith('unpicked')

    const disabledFilter = ChoiceFilter({
      value: 'all',
      options: [{ value: 'all', label: 'Все' }],
      onChange,
      ariaLabel: 'Фильтр листа',
      disabledReason: 'Лист подбора ещё загружается',
    }) as ReactElement<TooltipElementProps>
    const disabledGroup = disabledFilter.props.children.props.children
    const disabledButtons = disabledGroup.props.children as ReactElement<{ disabled: boolean }>[]

    expect(disabledFilter.props.title).toBe('Лист подбора ещё загружается')
    expect(disabledGroup.props['aria-disabled']).toBe(true)
    expect(disabledButtons[0].props.disabled).toBe(true)
  })

  it('keeps CheckCell focusable when enabled and explains why it is disabled', () => {
    const onChange = vi.fn()
    const readyCheck = CheckCell({
      checked: false,
      onChange,
      ariaLabel: 'Собрал Футболка базовая',
    }) as ReactElement<{ disabled: boolean; onChange: (event: { target: { checked: boolean } }) => void }>

    expect(readyCheck.props.disabled).toBe(false)
    readyCheck.props.onChange({ target: { checked: true } })
    expect(onChange).toHaveBeenCalledWith(true)

    const disabledCheck = CheckCell({
      checked: false,
      onChange,
      ariaLabel: 'Упаковал Футболка базовая',
      disabledReason: 'Сначала отметьте сборку',
    }) as ReactElement<TooltipElementProps>
    const disabledCheckbox = disabledCheck.props.children.props.children

    expect(disabledCheck.props.title).toBe('Сначала отметьте сборку')
    expect(disabledCheckbox.props.disabled).toBe(true)
  })

  it('supports order stickers and disables PrintAction while busy', () => {
    const readyPrint = PrintAction({ what: 'стикеры заказов', placement: 'panel' }) as ReactElement<{
      children: ReactNode
      disabledReason?: string
    }>
    expect(readyPrint.props.children).toBe('Печать стикеров')
    expect(readyPrint.props.disabledReason).toBeUndefined()

    const busyPrint = PrintAction({ what: 'стикеры заказов', placement: 'panel', busy: true }) as ReactElement<{
      disabledReason?: string
    }>
    expect(busyPrint.props.disabledReason).toBe('Подготовка печати…')
  })
})
