import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FfReportsPage, ReportNotices, reportCsvDisabledReason } from './FfReportsPage'

describe('FfReportsPage pagination actions', () => {
  it('keeps CSV primary and renders pagination as outlined disabled navigation', () => {
    const markup = renderToStaticMarkup(<FfReportsPage token="test-token" />)

    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-contained[^"]*"[^>]*data-testid="ff-reports-download-csv"/)
    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-outlined[^"]*"[^>]*disabled=""[^>]*data-testid="ff-reports-previous-page"/)
    expect(markup).toMatch(/<button[^>]*class="[^"]*MuiButton-outlined[^"]*"[^>]*disabled=""[^>]*data-testid="ff-reports-next-page"/)
    expect(markup).toContain('aria-label="Это первая страница"')
    expect(markup).toContain('aria-label="Это последняя страница"')
    // «Нетто» убрано намеренно: цифра не отвечала ни на один вопрос склада.
    // Панель читается как приход → расход → остаток, а начинается с того,
    // что было на начало периода, иначе остаток выглядит как ошибка расчёта.
    expect(markup).not.toContain('data-testid="ff-reports-metrics-net"')
    expect(markup).toContain('data-testid="ff-reports-metrics-opening"')
    expect(markup).not.toContain('ff-reports-comparison')
    expect(markup).not.toContain('ff-reports-chart')
  })
})


describe('report data guards after seller drill-down', () => {
  it('allows CSV when the seller table loaded, without requiring an expanded product', () => {
    expect(reportCsvDisabledReason({
      periodError: '', csvLoading: false, tableError: false,
      loading: false, loadedRowCount: 1,
    })).toBeUndefined()
    expect(reportCsvDisabledReason({
      periodError: '', csvLoading: false, tableError: false,
      loading: false, loadedRowCount: 0,
    })).toContain('нечего выгружать')
    expect(reportCsvDisabledReason({
      periodError: '', csvLoading: false, tableError: true,
      loading: false, loadedRowCount: 1,
    })).toContain('не загружены')
  })

  it('renders stale-source and legacy warnings alongside integrity errors in loaded details', () => {
    const markup = renderToStaticMarkup(<ReportNotices warnings={[
      { code: 'wildberries_stale', source: 'wildberries', last_updated_at: null },
      { code: 'reporting_dimensions_legacy', count: 3 },
    ]} detailRows={[{ integrity_error: false }, { integrity_error: true }]} />)
    expect(markup).toContain('ff-reports-warning-wildberries_stale')
    expect(markup).toContain('Данные Wildberries могут быть неполными')
    expect(markup).toContain('ff-reports-warning-reporting_dimensions_legacy')
    expect(markup).toContain('ff-reports-integrity-error')
    expect(markup).toContain('неполное перемещение')
  })
})
