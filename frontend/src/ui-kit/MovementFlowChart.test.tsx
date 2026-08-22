import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MovementFlowChart } from './MovementFlowChart'

const series = [
  { date: '2026-08-21', inbound: 12, outbound: 8, previousOutbound: 6 },
  { date: '2026-08-22', inbound: 15, outbound: 10, previousOutbound: 9 },
]

describe('MovementFlowChart', () => {
  it('renders a visible legend and accessible description for all enabled series', () => {
    const markup = renderToStaticMarkup(<MovementFlowChart series={series} showPrevious ariaDescription="Дневной приход и расход" testId="flow" />)
    expect(markup).toContain('Приход')
    expect(markup).toContain('Расход')
    expect(markup).toContain('Расход, прошлый период')
    expect(markup).toContain('aria-label="Дневной приход и расход"')
    expect(markup).toContain('stroke-dasharray="9 7"')
  })

  it('does not render the dashed comparison series when comparison is disabled', () => {
    const markup = renderToStaticMarkup(<MovementFlowChart series={series} showPrevious={false} ariaDescription="Описание" />)
    expect(markup).not.toContain('Расход, прошлый период')
    expect(markup).not.toContain('stroke-dasharray')
  })

  it('renders the empty-period message and loading skeleton', () => {
    const empty = renderToStaticMarkup(<MovementFlowChart series={[]} showPrevious ariaDescription="Описание" />)
    expect(empty).toContain('За выбранный период движений нет')
    const loading = renderToStaticMarkup(<MovementFlowChart series={series} showPrevious loading ariaDescription="Описание" testId="flow" />)
    expect(loading).toContain('MuiSkeleton-root')
    expect(loading).not.toContain('stroke-dasharray')
  })
})
