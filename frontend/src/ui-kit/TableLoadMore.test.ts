import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { TableLoadMore } from './TableLoadMore'

describe('TableLoadMore', () => {
  it('is hidden when there is no next cursor', () => {
    expect(TableLoadMore({ hasNext: false, onLoadMore: vi.fn() })).toBeNull()
  })

  it('renders one available load-more action', () => {
    const markup = renderToStaticMarkup(createElement(TableLoadMore, { hasNext: true, onLoadMore: vi.fn() }))

    expect(markup).toContain('Показать ещё')
    expect(markup.match(/<button/g)).toHaveLength(1)
    expect(markup).not.toContain('disabled=""')
  })

  it('shows progress and blocks the action while loading', () => {
    const markup = renderToStaticMarkup(
      createElement(TableLoadMore, { hasNext: true, loading: true, onLoadMore: vi.fn() }),
    )

    expect(markup).toContain('Загружаем…')
    expect(markup).toContain('role="progressbar"')
    expect(markup).toContain('disabled=""')
  })

  it('keeps the action available below an error notice', () => {
    const markup = renderToStaticMarkup(
      createElement(TableLoadMore, {
        hasNext: true,
        error: 'Не удалось загрузить следующие заказы',
        onLoadMore: vi.fn(),
      }),
    )

    const errorPosition = markup.indexOf('Не удалось загрузить следующие заказы')
    const actionPosition = markup.indexOf('Показать ещё')
    expect(errorPosition).toBeGreaterThanOrEqual(0)
    expect(actionPosition).toBeGreaterThan(errorPosition)
    expect(markup).not.toContain('disabled=""')
  })
})
