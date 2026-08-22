import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WarehouseContextSwitch } from './WarehouseContextSwitch'

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
    fireEvent.click(screen.getByTestId('warehouse-option-south'))
    expect(onChange).toHaveBeenCalledWith('south')
    expect(screen.queryByTestId('warehouse-option-south')).toBeNull()
  })

  it('shows the loading reason and disables the action', () => {
    render(<WarehouseContextSwitch options={options} value={null} onChange={vi.fn()} loading />)
    expect(screen.getByRole('button', { name: 'Загружаем склады' })).toBeDisabled()
    expect(screen.getByText('Загружаем склады')).toBeInTheDocument()
  })
})
