import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { WarningNotice } from './States'

describe('WarningNotice', () => {
  it('renders an accessible MUI warning alert with its text and test id', () => {
    const markup = renderToStaticMarkup(
      <WarningNotice testId="report-warning">Данные могут быть неполными</WarningNotice>,
    )

    expect(markup).toContain('data-testid="report-warning"')
    expect(markup).toContain('role="alert"')
    expect(markup).toContain('MuiAlert-colorWarning')
    expect(markup).toContain('Данные могут быть неполными')
  })
})
