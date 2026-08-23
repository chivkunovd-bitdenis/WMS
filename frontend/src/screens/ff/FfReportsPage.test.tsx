import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FfReportsPage } from './FfReportsPage'

describe('FfReportsPage pagination actions', () => {
  it('keeps CSV primary and renders pagination as outlined disabled navigation', () => {
    const markup = renderToStaticMarkup(<FfReportsPage token="test-token" />)

    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-contained[^"]*"[^>]*data-testid="ff-reports-download-csv"/)
    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-outlined[^"]*"[^>]*disabled=""[^>]*data-testid="ff-reports-previous-page"/)
    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-outlined[^"]*"[^>]*disabled=""[^>]*data-testid="ff-reports-next-page"/)
    expect(markup).toContain('aria-label="Это первая страница"')
    expect(markup).toContain('aria-label="Это последняя страница"')
    expect(markup).toContain('data-testid="ff-reports-metrics-net"')
    expect(markup).not.toContain('ff-reports-comparison')
    expect(markup).not.toContain('ff-reports-chart')
  })
})
