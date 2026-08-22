import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WarehouseContextSwitch } from './WarehouseContextSwitch'
import { WarningNotice } from './WarningNotice'

const options = [{ id: 'north', name: 'Склад Север' }, { id: 'south', name: 'Склад Юг' }]

describe('WarehouseContextSwitch', () => {
  it('does not render for one warehouse', () => {
    render(<WarehouseContextSwitch options={[options[0]]} value="north" onChange={vi.fn()} />)
    expect(screen.queryByText('Склад')).toBeNull()
  })

  it('opens, shows names, changes immediately, and closes', () => {
    const onChange = vi.fn()
    render(<WarehouseContextSwitch options={options} value="north" onChange={onChange} testId="warehouse" />)
    fireEvent.click(screen.getByTestId('warehouse-button'))
    expect(screen.getByText('Склад Юг')).toBeInTheDocument()
    expect(screen.queryByText('north')).toBeNull()
    expect(screen.queryByText('south')).toBeNull()
    fireEvent.click(screen.getByTestId('warehouse-option-south'))
    expect(onChange).toHaveBeenCalledWith('south')
    expect(screen.queryByTestId('warehouse-option-south')).toBeNull()
  })

  it('shows the loading reason and disables the action', () => {
    render(<WarehouseContextSwitch options={options} value={null} onChange={vi.fn()} loading />)
    expect(screen.getByRole('button', { name: 'Загружаем склады' })).toBeDisabled()
    expect(screen.getByText('Загружаем склады')).toBeInTheDocument()
  })

  it('shows the disabled reason and keeps the menu closed', () => {
    render(
      <WarehouseContextSwitch
        options={options}
        value="north"
        onChange={vi.fn()}
        disabledReason="Склад закреплён: подбор уже начат"
        testId="warehouse"
      />,
    )
    const button = screen.getByTestId('warehouse-button')
    expect(button).toBeDisabled()
    expect(screen.getByText('Склад закреплён: подбор уже начат')).toBeInTheDocument()
    fireEvent.click(button)
    expect(screen.queryByTestId('warehouse-option-south')).toBeNull()
  })

  it('shows an operator-facing error without exposing a selectable action', () => {
    render(
      <WarehouseContextSwitch
        options={options}
        value="north"
        onChange={vi.fn()}
        error="Не удалось загрузить склады. Обновите страницу."
        testId="warehouse-error"
      />,
    )
    expect(screen.getByTestId('warehouse-error')).toHaveTextContent('Не удалось загрузить склады')
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('renders a non-blocking warning notice', () => {
    render(<WarningNotice testId="warehouse-warning">Нужно подобрать товары с другого склада</WarningNotice>)
    expect(screen.getByTestId('warehouse-warning')).toHaveTextContent('Нужно подобрать товары с другого склада')
    expect(screen.getByRole('alert')).toHaveTextContent('Нужно подобрать товары с другого склада')
  })
})
