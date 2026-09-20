import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'
import { reloadChunkOnce, reportClientError } from '../../utils/clientErrorReport'

vi.mock('../../utils/clientErrorReport', () => ({
  reportClientError: vi.fn(), reloadChunkOnce: vi.fn(() => false),
}))

// Exercise lifecycle/timer wiring without a DOM emulation dependency.
function boundary() {
  const instance = new ErrorBoundary({ component: 'test', resetKey: '/first', children: <span>content</span> })
  vi.spyOn(instance, 'setState').mockImplementation((update) => {
    const next = typeof update === 'function' ? update(instance.state, instance.props) : update
    instance.state = { ...instance.state, ...next }
  })
  return instance
}
function fail(instance: ErrorBoundary) {
  instance.state = { ...instance.state, ...ErrorBoundary.getDerivedStateFromError() }
  instance.componentDidCatch(new Error('technical details'), { componentStack: 'test stack' })
}

beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks() })
afterEach(() => { vi.useRealTimers() })

describe('WMS-484 boundary lifecycle', () => {
  it('reports every catch, changes the subtree key and stays silent until the third failure', () => {
    const instance = boundary()
    fail(instance)
    expect(instance.state).toEqual({ failed: false, fallback: false, generation: 1 })
    fail(instance)
    expect(instance.render()).toBeNull()
    vi.advanceTimersByTime(1499)
    expect(instance.state.failed).toBe(true)
    vi.advanceTimersByTime(1)
    expect(instance.state.generation).toBe(2)
    fail(instance)
    expect(instance.state.fallback).toBe(true)
    expect(reportClientError).toHaveBeenCalledTimes(3)
    const html = renderToStaticMarkup(instance.render())
    expect(html).toContain('Не удалось показать этот раздел. Обновите страницу.')
    expect(html).toContain('Обновить')
    expect(html).not.toContain('technical details')
    expect(html).not.toContain('test stack')
  })
  it('cancels delayed recovery on unmount', () => {
    const instance = boundary()
    fail(instance)
    fail(instance)
    instance.componentWillUnmount()
    vi.advanceTimersByTime(2000)
    expect(instance.state.generation).toBe(1)
  })
  it('preserves healthy subtree on navigation but resets a failed boundary', () => {
    const instance = boundary()
    const previous = { ...instance.props, resetKey: '/previous' }
    instance.componentDidUpdate(previous)
    expect(instance.state.generation).toBe(0)
    fail(instance)
    fail(instance)
    instance.componentDidUpdate(previous)
    expect(instance.state).toEqual({ failed: false, fallback: false, generation: 2 })
    vi.advanceTimersByTime(2000)
    expect(instance.state.generation).toBe(2)
    fail(instance)
    expect(instance.state).toEqual({ failed: false, fallback: false, generation: 3 })
  })
  it('renders only the branded Russian fallback for a root failure', () => {
    const instance = new ErrorBoundary({ root: true, portal: 'seller', component: 'root', children: null })
    instance.state = { failed: true, fallback: true, generation: 2 }
    const html = renderToStaticMarkup(instance.render())
    expect(html).toContain('portal-logo-seller.png')
    expect(html).toContain('Короб ВМС')
    expect(html).not.toContain('Unexpected Application Error')
  })
  it('stays silent while automatic chunk reload is in progress', () => {
    vi.mocked(reloadChunkOnce).mockReturnValueOnce(true)
    const instance = boundary()
    fail(instance)
    expect(instance.render()).toBeNull()
    expect(instance.state.generation).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
  })
})
