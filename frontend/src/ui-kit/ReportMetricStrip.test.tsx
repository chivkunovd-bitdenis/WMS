import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReportMetricStrip, type ReportMetricItem } from './ReportMetricStrip'

const items = [
  { key: 'current', label: 'Остаток сейчас', value: 12480 },
  { key: 'inbound', label: 'Приход за период', value: 0 },
  { key: 'outbound', label: 'Расход за период', value: 2918 },
  {
    key: 'comparison',
    label: 'Расход к прошлому периоду',
    value: 184,
    delta: { value: 6.7, direction: 'up', a11yLabel: 'Расход вырос на 6,7 процента' },
  },
] satisfies ReportMetricItem[]

describe('ReportMetricStrip', () => {
  it('renders four metrics, including zero, units, and accessible delta explanation', () => {
    const markup = renderToStaticMarkup(<ReportMetricStrip items={items} testId="report-metrics" />)

    expect(markup).toContain('data-testid="report-metrics"')
    expect(markup).toContain('Остаток сейчас')
    expect(markup).toContain('Приход за период')
    expect(markup).toContain('Расход за период')
    expect(markup).toContain('Расход к прошлому периоду')
    // Число и единица теперь рисуются отдельными элементами: цифра крупная,
    // подпись рядом мельче. Поэтому проверяем их по отдельности.
    expect(markup).toContain('12\u00A0480')
    expect(markup).toContain('2\u00A0918')
    expect(markup).toContain('184')
    expect(markup).toContain('шт.')
    expect(markup).toContain('Расход вырос на 6,7 процента')
    expect(markup).toContain('+6,7 %')
    expect(markup).not.toContain('+6,7 шт.')
    expect((markup.match(/data-testid="report-metrics-[^"]+"/g) ?? []).length).toBe(4)
  })

  it('renders an inapplicable value as a dash with its explanation', () => {
    const markup = renderToStaticMarkup(
      <ReportMetricStrip
        items={[
          ...items.slice(0, 3),
          {
            ...items[3],
            value: null,
            delta: undefined,
            nullValueLabel: 'В прошлом периоде расхода не было',
          },
        ]}
      />,
    )

    expect(markup).toContain('—')
    expect(markup).toContain('В прошлом периоде расхода не было')
    expect(markup).not.toContain('184 шт.')
  })

  it('formats a minor-money metric once through the canonical formatter', () => {
    const markup = renderToStaticMarkup(
      <ReportMetricStrip items={[
        { key: 'money-null', label: 'Нет данных', moneyMinor: null },
        { key: 'money-zero', label: 'Ноль', moneyMinor: 0 },
        { key: 'money-string', label: 'Строка', moneyMinor: '63000.00' },
        { key: 'money-reversal', label: 'Сторно', moneyMinor: -60000 },
      ]} />,
    )

    expect(markup).toContain('—')
    expect(markup).toContain('0,00 ₽')
    expect(markup).toContain('630,00 ₽')
    expect(markup).toContain('-600,00 ₽')
    expect(markup).not.toContain('63000 ₽')
    expect(markup).not.toContain('63 000 ₽')
  })

  it('does not permit a numeric value alongside a minor-money metric', () => {
    // @ts-expect-error moneyMinor and value are intentionally mutually exclusive.
    const invalid: ReportMetricItem = { key: 'invalid', label: 'Нельзя', value: 12, moneyMinor: 1200 }

    expect(invalid).toBeDefined()
  })

  it('replaces all values with loading skeletons', () => {
    const markup = renderToStaticMarkup(<ReportMetricStrip items={items} loading testId="report-metrics" />)

    expect((markup.match(/data-testid="report-metrics-[^"]+-skeleton"/g) ?? []).length).toBe(4)
    expect(markup).not.toContain('12 480 шт.')
    expect(markup).not.toContain('0 шт.')
    expect(markup).not.toContain('2 918 шт.')
    expect(markup).not.toContain('184 шт.')
    expect(markup).not.toContain('+6,7 %')
  })
})
