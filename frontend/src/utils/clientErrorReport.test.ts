import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CHUNK_RELOAD_KEY } from './errorRecovery'

const makeStorage = () => {
  const data = new Map<string, string>()
  return {
    getItem: vi.fn((key: string) => data.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => { data.set(key, value) }),
    removeItem: vi.fn((key: string) => { data.delete(key) }),
  }
}
let storage: ReturnType<typeof makeStorage>
let session: ReturnType<typeof makeStorage>
let fetchMock: ReturnType<typeof vi.fn>
let reload: ReturnType<typeof vi.fn>
let listeners: Map<string, (event: unknown) => void>

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  storage = makeStorage()
  storage.setItem('wms_token_ff', 'ff-token')
  storage.setItem('wms_token_seller', 'seller-token')
  session = makeStorage()
  fetchMock = vi.fn().mockResolvedValue({ status: 204 })
  reload = vi.fn()
  listeners = new Map()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', storage)
  vi.stubGlobal('sessionStorage', session)
  vi.stubGlobal('navigator', { userAgent: 'test-browser' })
  vi.stubGlobal('window', {
    location: { origin: 'https://wms.test', pathname: '/app/ff/fbs', search: '?token=private', reload },
    addEventListener: vi.fn((type, callback) => listeners.set(type, callback)),
    removeEventListener: vi.fn((type) => listeners.delete(type)),
  })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

function payload() {
  return JSON.parse(fetchMock.mock.calls.at(-1)![1].body)
}

describe('WMS-484 client reporting', () => {
  it('sends context, stack and current portal token, without query secrets', async () => {
    const { reportClientError, installClientErrorHandlers } = await import('./clientErrorReport')
    installClientErrorHandlers('seller')
    const error = new Error('Ошибка узла')
    reportClientError(error, { screen: 'orders', component: 'workspace', action: 'react' })
    expect(fetchMock).toHaveBeenCalledWith('/api/client-errors', expect.objectContaining({
      method: 'POST', keepalive: true,
      headers: { Authorization: 'Bearer seller-token', 'Content-Type': 'application/json' },
    }))
    expect(payload()).toMatchObject({ message: error.message, stack: error.stack, screen: 'orders', component: 'workspace', action: 'react', url: 'https://wms.test/app/ff/fbs', user_agent: 'test-browser' })
    storage.setItem('wms_token_seller', 'new-token')
    reportClientError('another')
    expect(fetchMock.mock.calls.at(-1)![1].headers.Authorization).toBe('Bearer new-token')
  })
  it('deduplicates the same message for one minute, including restored errors', async () => {
    const { reportClientError } = await import('./clientErrorReport')
    reportClientError(new Error('same'), { component: 'first' })
    reportClientError(new Error('same'), { component: 'second' })
    vi.advanceTimersByTime(59_999)
    reportClientError('same')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1)
    reportClientError('same')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('caps UTF-8 JSON bytes and stack lines, including escaped characters', async () => {
    const { reportClientError } = await import('./clientErrorReport')
    const error = new Error('😀\u0000"\\'.repeat(20_000))
    error.stack = Array.from({ length: 100 }, (_, i) => `frame ${i}`).join('\n')
    reportClientError(error, { screen: 'я'.repeat(5000), component: 'x'.repeat(5000), action: '\n'.repeat(5000) })
    expect(new TextEncoder().encode(fetchMock.mock.calls[0][1].body).length).toBeLessThan(16 * 1024)
    expect(new TextEncoder().encode(JSON.stringify(payload().message)).length).toBeLessThanOrEqual(2002)
    expect(payload().stack.split('\n')).toHaveLength(40)
    expect(payload().screen).toHaveLength(150)
    expect(payload().component).toHaveLength(500)
    expect(payload().action).toHaveLength(150)
  })
  it('never throws for fetch rejection, synchronous failure, storage or hostile errors', async () => {
    const { reportClientError } = await import('./clientErrorReport')
    fetchMock.mockRejectedValueOnce(new Error('offline'))
    expect(() => reportClientError('offline')).not.toThrow()
    await Promise.resolve()
    fetchMock.mockImplementationOnce(() => { throw new Error('fetch failed') })
    expect(() => reportClientError('sync')).not.toThrow()
    expect(() => reportClientError({ toString() { throw new Error('bad') } })).not.toThrow()
    storage.getItem.mockImplementation(() => { throw new Error('storage blocked') })
    expect(() => reportClientError('storage')).not.toThrow()
  })
  it('skips anonymous reports', async () => {
    const { reportClientError } = await import('./clientErrorReport')
    storage.removeItem('wms_token_ff')
    reportClientError('anonymous')
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it.each(['fulfillment', 'seller'] as const)('registers both global handlers for %s', async (portal) => {
    const { installClientErrorHandlers } = await import('./clientErrorReport')
    const cleanup = installClientErrorHandlers(portal)
    listeners.get('error')!({ error: new Error('render') })
    listeners.get('unhandledrejection')!({ reason: new Error('promise') })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(payload()).toMatchObject({ component: 'window', action: 'unhandledrejection', message: 'promise' })
    cleanup()
    expect(listeners.size).toBe(0)
  })
  it('reloads a chunk failure once across module reloads and never clears the guard', async () => {
    const error = new Error('Failed to fetch dynamically imported module')
    const { reloadChunkOnce } = await import('./clientErrorReport')
    expect(reloadChunkOnce(error)).toBe(true)
    expect(session.getItem(CHUNK_RELOAD_KEY)).toBe('1')
    vi.resetModules()
    const afterNavigation = await import('./clientErrorReport')
    expect(afterNavigation.reloadChunkOnce(error)).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
  })
  it('does not reload without a persistent guard or for unrelated errors', async () => {
    const { reloadChunkOnce } = await import('./clientErrorReport')
    expect(reloadChunkOnce(new Error('Failed to fetch'))).toBe(false)
    session.setItem.mockImplementation(() => { throw new Error('blocked') })
    expect(reloadChunkOnce(new Error('Loading chunk 2 failed'))).toBe(false)
    expect(reload).not.toHaveBeenCalled()
  })
})
