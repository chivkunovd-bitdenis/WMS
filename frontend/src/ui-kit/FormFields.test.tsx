import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { __formFieldsTest, MoscowDateInput, MoscowDateRangeInput, MoscowDateTimeInput, NumberInput, PreferenceSwitch, SelectInput, TextInput } from './FormFields'

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

  it('links a label, input and helper without testId, while omitting aria-describedby without helper text', () => {
    const withHelper = renderToStaticMarkup(
      createElement(TextInput, {
        label: 'Название',
        value: 'Тест',
        onChange: () => undefined,
        helperText: 'Подсказка',
      }),
    )
    const inputId = withHelper.match(/<input[^>]*\sid="([^"]+)"[^>]*>/)?.[1]
    const helperId = withHelper.match(/aria-describedby="([^"]+)"/)?.[1]

    expect(inputId).toBeTruthy()
    expect(helperId).toBeTruthy()
    expect(withHelper).toContain(`for="${inputId}"`)
    expect(withHelper).toContain(`id="${helperId}"`)
    expect(helperId).not.toContain('undefined')

    const withoutHelper = renderToStaticMarkup(
      createElement(TextInput, { label: 'Пустое поле', value: '', onChange: () => undefined }),
    )
    expect(withoutHelper).not.toContain('aria-describedby=')

    const explicitId = renderToStaticMarkup(
      createElement(TextInput, { id: 'explicit-name', label: 'Имя', value: '', onChange: () => undefined, testId: 'only-a-test-hook' }),
    )
    expect(explicitId).toMatch(/<label[^>]*for="explicit-name"/)
    expect(explicitId).toMatch(/<input[^>]*id="explicit-name"/)
  })

  it('gives a number field numeric right-aligned semantics and does not emit out-of-range input', () => {
    const markup = renderToStaticMarkup(
      createElement(NumberInput, { label: 'Ставка', value: 12, onChange: () => undefined, min: 0, max: 100, step: 0.5, testId: 'form-number' }),
    )
    expect(markup).toContain('type="number"')
    expect(markup).toContain('text-align:right')
    expect(markup).toContain('inputMode="decimal"')
  })

  it('renders a native keyboard-focusable select with an empty choice, disabled option and change handler', () => {
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
    expect(markup).toContain('<select')
    expect(markup).toContain('tabindex="0"')
    expect(markup).toMatch(/<label[^>]*data-shrink="true"/)
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
    expect(markup).toMatch(/<label[^>]*data-shrink="true"/)
  })

  it('rejects Moscow DST gap and ambiguity, while resolving a valid boundary and invalid calendar precisely', () => {
    expect(__formFieldsTest.resolveMoscowWallTime('2010-03-28T02:30')).toBeNull()
    expect(__formFieldsTest.resolveMoscowWallTime('2010-10-31T02:30')).toBeNull()
    expect(__formFieldsTest.resolveMoscowWallTime('2010-03-28T03:30')).toBe('2010-03-27T23:30:00.000Z')
    expect(__formFieldsTest.resolveMoscowWallTime('2026-02-30T12:00')).toBeNull()
  })

  it('renders stable native Moscow date values with labelled help and bounds', () => {
    const markup = renderToStaticMarkup(
      createElement(MoscowDateInput, {
        label: 'Дата', value: '2026-08-27', onChange: () => undefined,
        minDate: '2026-01-01', maxDate: '2026-12-31', helperText: 'Выберите календарную дату', testId: 'form-date',
      }),
    )

    expect(markup).toContain('type="date"')
    expect(markup).toContain('value="2026-08-27"')
    expect(markup).toContain('min="2026-01-01"')
    expect(markup).toContain('max="2026-12-31"')
    expect(markup).toContain('Выберите календарную дату')
    expect(markup).toContain('aria-describedby=')
  })

  it('validates date-only calendar, range order, inclusive length and caller-supplied future bound', () => {
    expect(__formFieldsTest.validateIsoDate('2026-02-30')).toBe('Укажите корректную дату')
    expect(__formFieldsTest.validateDateRange(
      { start: '2026-08-12', end: '2026-08-11' }, {},
    )).toBe('Дата окончания не может быть раньше даты начала')
    expect(__formFieldsTest.validateDateRange(
      { start: '2026-01-01', end: '2027-01-02' }, { maxDays: 366 },
    )).toBe('Период превышает допустимую длину')
    expect(__formFieldsTest.validateDateRange(
      { start: '2026-08-01', end: '2026-08-01' }, { maxDate: '2026-07-31' },
    )).toBe('Дата вне допустимого диапазона')
    expect(__formFieldsTest.validateDateRange(
      { start: '2026-01-01', end: '2027-01-01' }, { maxDays: 367 },
    )).toBeUndefined()
  })

  it('renders a controlled labelled switch with accessible help and loading disablement', () => {
    const markup = renderToStaticMarkup(
      createElement(PreferenceSwitch, {
        label: 'Дополнительные сведения', checked: true, onChange: () => undefined,
        helperText: 'Можно изменить', loading: true, testId: 'form-preference',
      }),
    )

    expect(markup).toContain('type="checkbox"')
    expect(markup).toContain('checked=""')
    expect(markup).toContain('Дополнительные сведения')
    expect(markup).toContain('Можно изменить')
    expect(markup).toContain('aria-describedby=')
    expect(markup).toContain('disabled=""')
    expect(markup).toContain('aria-busy="true"')
  })

  it('renders a labelled controlled range with stable start and end inputs', () => {
    const markup = renderToStaticMarkup(
      createElement(MoscowDateRangeInput, {
        label: 'Период', value: { start: '2026-08-01', end: '2026-08-07' }, onChange: () => undefined,
        maxDays: 31, helperText: 'Не более месяца', testId: 'form-range',
      }),
    )

    expect(markup).toContain('<fieldset')
    expect(markup).toContain('<legend')
    expect(markup).toContain('Период')
    expect(markup).toContain('value="2026-08-01"')
    expect(markup).toContain('value="2026-08-07"')
    expect(markup).toContain('data-testid="form-range-start"')
    expect(markup).toContain('data-testid="form-range-end"')
  })
})
