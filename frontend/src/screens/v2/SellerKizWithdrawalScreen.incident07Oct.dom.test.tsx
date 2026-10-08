// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { SellerKizWithdrawalScreen, type WithdrawalSigningAdapter } from './SellerKizWithdrawalScreen'
import type { SellerWithdrawalApi, WithdrawalPage, WithdrawalProductOption, WithdrawalRow } from './sellerKizWithdrawalApi'
import { loadCryptoProBrowserPlugin } from '../../integrations/loadCryptoProBrowserPlugin'

// Import the five real icons individually instead of loading the entire icon catalog.
vi.mock('@mui/icons-material', async () => ({
  CloseOutlined: (await import('@mui/icons-material/CloseOutlined')).default,
  KeyOutlined: (await import('@mui/icons-material/KeyOutlined')).default,
  OpenInNewOutlined: (await import('@mui/icons-material/OpenInNewOutlined')).default,
  RefreshOutlined: (await import('@mui/icons-material/RefreshOutlined')).default,
  SearchOutlined: (await import('@mui/icons-material/SearchOutlined')).default,
}))

beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const row = (id: string): WithdrawalRow => ({
  row_id: id, product_id: 'product', delivered_at: '2026-10-07T12:00:00Z', wb_order_id: `WB-${id}`,
  sku: `SKU-${id}`, product_name: `Товар ${id}`, cis: `010123456789012321${id}`, status: 'not_withdrawn', error: null, operation_id: null,
})
const page = (id: string): WithdrawalPage => ({ rows: [row(id)], total: 1 })
const product = (id: string): WithdrawalProductOption => ({ id, sku: id, name: `B ${id}` })
const makeApi = () => ({
  list: vi.fn< SellerWithdrawalApi['list'] >().mockResolvedValue({ rows: [], total: 0 }),
  listProducts: vi.fn< SellerWithdrawalApi['listProducts'] >().mockResolvedValue([]),
  createOperation: vi.fn(), getOperation: vi.fn(), retryOperation: vi.fn(), requestReauthChallenge: vi.fn(),
  submitAuthSignature: vi.fn(), submitDocumentSignatures: vi.fn(),
}) satisfies SellerWithdrawalApi
const signer = {
  checkReadiness: vi.fn().mockResolvedValue({}), listCertificates: vi.fn(), signAttachedAuthChallenge: vi.fn(), signDetachedDocument: vi.fn(),
} satisfies WithdrawalSigningAdapter
let host: HTMLDivElement
let root: Root
let usedApis: ReturnType<typeof makeApi>[]
beforeEach(() => {
  window.localStorage.clear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  usedApis = []
  vi.clearAllMocks()
})
afterEach(async () => {
  // IC7: read/recovery never performs a write, certificate lookup, or a signature.
  for (const api of usedApis) {
    expect(api.createOperation).not.toHaveBeenCalled(); expect(api.getOperation).not.toHaveBeenCalled()
    expect(api.retryOperation).not.toHaveBeenCalled(); expect(api.requestReauthChallenge).not.toHaveBeenCalled()
    expect(api.submitAuthSignature).not.toHaveBeenCalled(); expect(api.submitDocumentSignatures).not.toHaveBeenCalled()
  }
  expect(signer.listCertificates).not.toHaveBeenCalled()
  expect(signer.signAttachedAuthChallenge).not.toHaveBeenCalled(); expect(signer.signDetachedDocument).not.toHaveBeenCalled()
  await act(async () => root.unmount()); host.remove()
  delete (window as Window & { cadesplugin?: unknown }).cadesplugin
})
async function flush() { await act(async () => { await Promise.resolve() }) }
async function mount(api: ReturnType<typeof makeApi>, sellerId = 'seller-a', pluginLoader?: () => Promise<void>) {
  if (!usedApis.includes(api)) usedApis.push(api)
  await act(async () => root.render(<MemoryRouter><SellerKizWithdrawalScreen token="session" sellerId={sellerId} api={api} signingAdapter={signer} pluginLoader={pluginLoader} /></MemoryRouter>))
  await flush()
}
async function change(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await flush()
}
const refresh = () => [...host.querySelectorAll('button')].find((node) => node.textContent?.trim() === 'Обновить')!
async function clickRefresh() { await act(async () => refresh().click()); await flush() }
async function settle<T>(pending: ReturnType<typeof deferred<T>>, result: T) { await act(async () => pending.resolve(result)); await flush() }
async function fail<T>(pending: ReturnType<typeof deferred<T>>, error: unknown) { await act(async () => pending.reject(error)); await flush() }
const expectFresh = (id: string) => {
  expect(host.textContent).toContain(`Товар ${id}`); expect(host.textContent).toContain('Найдено: 1')
  expect(refresh().disabled).toBe(false); expect(host.querySelector('[role="progressbar"]')).toBeNull()
}
async function openProducts() {
  const input = host.querySelector('input[role="combobox"]') as HTMLInputElement
  await act(async () => { input.focus(); input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })) })
  await flush()
}
const optionText = () => [...document.querySelectorAll('[role="option"]')].map((option) => option.textContent).join('|')

describe('WMS-517 incident registry recovery on the real screen', () => {
  it.each(['Error', 'string', 'undefined', 'success'] as const)('IC3 ignores cancelled registry %s after filter B completes', async (outcome) => {
    const api = makeApi(); const old = deferred<WithdrawalPage>(); const fresh = deferred<WithdrawalPage>()
    api.list.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    await mount(api)
    await change(host.querySelector('input[type="date"]')!, '2026-09-01')
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(api.list.mock.calls[0][1]?.aborted).toBe(true)
    await settle(fresh, page('fresh'))
    if (outcome !== 'success') await fail(old, outcome === 'Error' ? new Error('stale registry error') : outcome === 'string' ? 'stale registry error' : undefined)
    else await settle(old, page('stale'))
    expectFresh('fresh'); expect(host.textContent).not.toContain('stale'); expect(host.querySelector('[role="alert"]')).toBeNull()
  })
  it.each(['Error', 'string', 'undefined', 'success'] as const)('IC4 ignores old product %s across API/seller context', async (outcome) => {
    const oldApi = makeApi(); const freshApi = makeApi(); const old = deferred<WithdrawalProductOption[]>(); const fresh = deferred<WithdrawalProductOption[]>()
    oldApi.listProducts.mockReturnValueOnce(old.promise); freshApi.listProducts.mockReturnValueOnce(fresh.promise)
    await mount(oldApi); await mount(freshApi, 'seller-b')
    expect(oldApi.listProducts.mock.calls[0][1]?.aborted).toBe(true)
    await settle(fresh, [product('fresh')])
    if (outcome !== 'success') await fail(old, outcome === 'Error' ? new Error('stale product error') : outcome === 'string' ? 'stale product error' : undefined)
    else await settle(old, [product('stale')])
    await openProducts()
    expect(optionText()).toContain('B fresh'); expect(optionText()).not.toContain('stale')
    expect(host.textContent).not.toContain('stale product error'); expect(host.querySelector('[role="alert"]')).toBeNull()
  })
  it.each(['Error', 'string', 'undefined', 'success'] as const)('IC4 ignores old product %s after a debounced search', async (outcome) => {
    const api = makeApi(); const old = deferred<WithdrawalProductOption[]>(); const fresh = deferred<WithdrawalProductOption[]>()
    api.listProducts.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    await mount(api); await change(host.querySelector('input[role="combobox"]')!, 'B')
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 330)) })
    expect(api.listProducts).toHaveBeenCalledTimes(2)
    expect(api.listProducts.mock.calls[0][1]?.aborted).toBe(true)
    await settle(fresh, [product('fresh')])
    if (outcome !== 'success') await fail(old, outcome === 'Error' ? new Error('stale product search error') : outcome === 'string' ? 'stale product search error' : undefined)
    else await settle(old, [product('stale')])
    await openProducts()
    expect(optionText()).toContain('B fresh'); expect(optionText()).not.toContain('stale')
    expect(host.textContent).not.toContain('stale product search error'); expect(host.querySelector('[role="alert"]')).toBeNull()
  })
  it('IC5 ignores a replaced manual refresh rejection after newer filter data succeeds', async () => {
    const api = makeApi(); const old = deferred<WithdrawalPage>(); const fresh = deferred<WithdrawalPage>()
    api.list.mockResolvedValueOnce(page('initial')).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    await mount(api); await clickRefresh()
    await change(host.querySelector('input[type="date"]')!, '2026-09-01')
    await settle(fresh, page('fresh')); await fail(old, new Error('stale manual error'))
    expectFresh('fresh'); expect(host.textContent).not.toContain('stale manual error')
  })
  it.each(['filter', 'refresh'] as const)('IC6 shows the current registry failure and recovers via %s', async (action) => {
    const api = makeApi(); const fresh = deferred<WithdrawalPage>()
    api.list.mockRejectedValueOnce(new Error('current registry failure')).mockReturnValueOnce(fresh.promise)
    await mount(api); expect(host.textContent).toContain('current registry failure')
    if (action === 'filter') await change(host.querySelector('input[type="date"]')!, '2026-09-01')
    else await clickRefresh()
    await settle(fresh, page('recovered'))
    expectFresh('recovered'); expect(host.textContent).not.toContain('current registry failure')
  })
  it('IC6 registry success does not hide the current product failure', async () => {
    const api = makeApi(); const initial = deferred<WithdrawalPage>(); const fresh = deferred<WithdrawalPage>()
    api.list.mockReturnValueOnce(initial.promise).mockReturnValueOnce(fresh.promise)
    api.listProducts.mockRejectedValueOnce(new Error('current products failure'))
    await mount(api); expect(host.textContent).toContain('current products failure')
    await settle(initial, page('initial')); await clickRefresh(); await settle(fresh, page('fresh'))
    expectFresh('fresh'); expect(host.textContent).toContain('current products failure')
  })
  it('IC9/IC10 native plugin rejection has a specific warning while the registry stays readable', async () => {
    const api = makeApi(); const delayed = deferred<WithdrawalPage>(); api.list.mockReturnValueOnce(delayed.promise)
    ;(window as Window & { cadesplugin?: unknown }).cadesplugin = { then: (_resolve: unknown, reject: (reason: unknown) => void) => reject(undefined) }
    await mount(api, 'seller-a', () => loadCryptoProBrowserPlugin(100))
    expect(host.querySelector('[role="progressbar"]')).not.toBeNull()
    await settle(delayed, page('readable'))
    expectFresh('readable')
    expect(host.textContent).toContain('КриптоПро недоступен. Проверьте расширение и локальный сервис.')
    expect(host.textContent).not.toContain('Не удалось выполнить операцию. Обновите данные и повторите.')
  })
})

describe('WMS-517 IC15: initial report count is truthful while reading', () => {
  it.each(['rows', 'empty'] as const)('IC15 pending initial read shows loading until complete %s response', async (kind) => {
    const api = makeApi(); const delayed = deferred<WithdrawalPage>()
    api.list.mockReturnValueOnce(delayed.promise)
    await mount(api, 'seller-a', async () => { throw new Error('fixture signing readiness warning') })
    expect(host.querySelector('[role="progressbar"]')).not.toBeNull()
    expect(host.textContent).toContain('fixture signing readiness warning')
    expect(host.textContent).not.toContain('Найдено: 0')
    expect(host.textContent).toMatch(/загруз/i)
    await settle(delayed, kind === 'rows' ? page('loaded') : { rows: [], total: 0 })
    expect(host.querySelector('[role="progressbar"]')).toBeNull()
    expect(refresh().disabled).toBe(false)
    if (kind === 'rows') expectFresh('loaded')
    else expect(host.textContent).toContain('Найдено: 0')
    expect(host.textContent).toContain('fixture signing readiness warning')
  })
})

describe('WMS-517 R30/R35: an unsuccessful poll cannot hide a manual refresh', () => {
  it('keeps pending manual refresh visible and reports its failure after a silent poll fails', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const api = makeApi()
      const manual = deferred<WithdrawalPage>()
      const poll = deferred<WithdrawalPage>()
      const processing: WithdrawalPage = {
        rows: [{ ...row('processing'), status: 'transferring', operation_id: 'existing-operation' }],
        total: 1,
      }
      api.list.mockResolvedValueOnce(processing)
        .mockReturnValueOnce(manual.promise)
        .mockReturnValueOnce(poll.promise)
      await mount(api)
      expectFresh('processing')
      await clickRefresh()
      expect(host.querySelector('[role="progressbar"]')).not.toBeNull()
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
      // Pausing background polling during an explicit refresh is also valid.
      if (api.list.mock.calls.length === 3) {
        await fail(poll, new Error('fixture background poll failure'))
      }
      expect(host.querySelector('[role="progressbar"]')).not.toBeNull()
      expect(refresh().disabled).toBe(true)
      await fail(manual, new Error('fixture manual refresh failure'))
      expect(host.querySelector('[role="progressbar"]')).toBeNull()
      expect(refresh().disabled).toBe(false)
      expect(host.textContent).toContain('fixture manual refresh failure')
      expect(host.textContent).toContain('Товар processing')
    } finally {
      vi.useRealTimers()
    }
  })
})
