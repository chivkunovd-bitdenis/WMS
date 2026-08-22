import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReportMetricStrip, type ReportMetricItem } from './ReportMetricStrip'

const items: ReportMetricItem[] = [
  { key: 'current', label: 'Остаток сейчас', value: 12480 },
  { key: 'inbound', label: 'Приход за период', value: 0 },
  { key: 'outbound', label: 'Расход за период', value: 2918 },
  {
    key: 'comparison',
    label: 'Расход к прошлому периоду',
    value: 184,
    delta: { value: 6.7, direction: 'up', a11yLabel: 'Расход вырос на 6,7 процента' },
  },
]

describe('ReportMetricStrip', () => {
  it('renders four metrics, including zero, units, and accessible delta explanation', () => {
    const markup = renderToStaticMarkup(<ReportMetricStrip items={items} testId="report-metrics" />)

    expect(markup).toContain('data-testid="report-metrics"')
    expect(markup).toContain('Остаток сейчас')
    expect(markup).toContain('12 480 шт.')
    expect(markup).toContain('0 шт.')
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

  it('replaces all values with loading skeletons', () => {
    const markup = renderToStaticMarkup(<ReportMetricStrip items={items} loading testId="report-metrics" />)

    expect(markup).toContain('MuiSkeleton-root')
    expect(markup).not.toContain('12 480 шт.')
    expect(markup).not.toContain('2 918 шт.')
  })
})
