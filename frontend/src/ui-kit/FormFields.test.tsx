import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { MoscowDateTimeInput, NumberInput, SelectInput, TextInput } from './FormFields'

describe('generic form fields', () => {
  it('renders label, linked error/help and disabled loading state without a screen-specific contract', () => {
    const markup = renderToStaticMarkup(
      createElement(TextInput, {
        label: 'Название',
        value: 'Тест',
        onChange: () => undefined,
        error: 'Проверьте значение',
        disabled: true,
        loading: true,
        testId: 'form-text',
      }),
    )

    expect(markup).toContain('Название')
    expect(markup).toContain('Проверьте значение')
    expect(markup).toContain('data-testid="form-text"')
    expect(markup).toContain('aria-invalid="true"')
    expect(markup).toContain('aria-busy="true"')
    expect(markup).toContain('disabled=""')
  })

  it('gives a number field numeric right-aligned semantics and does not emit out-of-range input', () => {
    const onChange = vi.fn()
    const element = NumberInput({
      label: 'Ставка',
      value: 12,
      onChange,
      min: 0,
      max: 100,
      step: 0.5,
      testId: 'form-number',
    })
    const field = (element.props as { children: ReactElement }).children
    const props = field.props as { onChange: (event: { target: { value: string } }) => void }

    props.onChange({ target: { value: '12.5' } })
    props.onChange({ target: { value: '101' } })

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith(12.5)
    const markup = renderToStaticMarkup(element)
    expect(markup).toContain('type="number"')
    expect(markup).toContain('text-align:right')
    expect(markup).toContain('inputMode="decimal"')
  })

  it('renders a selectable accessible empty choice and disabled option', () => {
    const markup = renderToStaticMarkup(
      createElement(SelectInput, {
        label: 'Единица',
        value: '',
        onChange: () => undefined,
        emptyLabel: 'Выберите единицу',
        options: [
          { value: 'item', label: 'За единицу' },
          { value: 'document', label: 'За документ', disabled: true },
        ],
        error: 'Выберите единицу',
        testId: 'form-select',
      }),
    )

    expect(markup).toContain('Единица')
    expect(markup).toContain('Выберите единицу')
    expect(markup).toContain('За единицу')
    expect(markup).toContain('За документ')
    expect(markup).toContain('aria-invalid="true"')
  })

  it('presents a UTC instant as Moscow wall time and keeps the input accessible', () => {
    const markup = renderToStaticMarkup(
      createElement(MoscowDateTimeInput, {
        label: 'Действует с',
        value: '2026-01-15T09:00:00.000Z',
        onChange: () => undefined,
        error: 'Укажите существующее однозначное время Москвы',
        testId: 'form-moscow-time',
      }),
    )

    expect(markup).toContain('type="datetime-local"')
    expect(markup).toContain('data-testid="form-moscow-time"')
    expect(markup).toContain('value="2026-01-15T12:00"')
    expect(markup).toContain('Укажите существующее однозначное время Москвы')
  })

  it('emits one UTC instant for valid Moscow wall time and emits nothing for an invalid value', async () => {
    vi.resetModules()
    vi.doMock('react', async () => {
      const actual = await vi.importActual<typeof import('react')>('react')
      return {
        ...actual,
        useMemo: <T,>(factory: () => T) => factory(),
        useState: <T,>(initial: T) => [initial, () => undefined] as const,
      }
    })
    const { MoscowDateTimeInput: DirectMoscowDateTimeInput } = await import('./FormFields')
    const onChange = vi.fn()
    const frame = DirectMoscowDateTimeInput({
      label: 'Действует с',
      value: null,
      onChange,
      testId: 'form-moscow-time-direct',
    })
    const field = (frame.props as { children: ReactElement }).children
    const props = field.props as { onChange: (event: { target: { value: string } }) => void }

    props.onChange({ target: { value: '2026-01-15T12:00' } })
    props.onChange({ target: { value: '2026-02-30T12:00' } })

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('2026-01-15T09:00:00.000Z')
    vi.doUnmock('react')
  })
})
