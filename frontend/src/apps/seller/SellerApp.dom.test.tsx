// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { sellerCatalogScopeKey } from './SellerApp'
import { FfBillingInvoicesPanel } from '../../screens/ff/FfBillingInvoicesPanel'

// WMS-549 (ревью Astra №1 F1 — блокер; ревью №2 F6 — побочный эффект F1):
// пересоздание разделов кабинета селлера должно отличать смену ОБЛАСТИ сессии
// (магазин/селлер/tenant — applyToken() при /auth/switch-seller) от простого
// перевыпуска токена той же области (та же цель, другая подпись/iat). Ключ
// строится из claims токена (tenant_id/sub/seller_id), а не из его полной
// строки: они меняются в том же рендере, что и сам token (раньше /auth/me —
// F1 остаётся исправленным), но не меняются при перевыпуске той же области
// (F6). Оба сценария проверены тестами «от обратного»: ниже показано, что
// со старым выражением ключа падает ровно тот тест, который должен падать.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let root: Root | null = null
let host: HTMLDivElement | null = null
async function mount(element: React.ReactElement) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(element) })
}
async function rerender(element: React.ReactElement) {
  await act(async () => { root!.render(element) })
}
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const tick = () => act(async () => { await Promise.resolve() })

/** Настоящий JWT по форме (header.payload.signature) — decodeJwtClaims должен его прочитать. */
function fakeJwt(payload: Record<string, unknown>, signatureSalt = ''): string {
  const b64url = (value: string) =>
    btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = b64url(JSON.stringify(payload))
  return `${header}.${body}.sig${signatureSalt}`
}

function invoiceRow(id: string, number: string) {
  return {
    id,
    origin: 'v2' as const,
    number,
    seller_id: 'irrelevant-in-seller-scope',
    seller_name: '',
    issued_at: '2026-09-01T00:00:00Z',
    period_start: null,
    period_end: null,
    creation_mode: 'selected_operations' as const,
    status: 'issued' as const,
    total_amount_kopecks: 1000,
  }
}

/** Обёртка — то же самое, что делает маршрут SellerApp: ключ, токен и sellerScope. */
function Harness({ token, me }: { token: string; me: { active_seller_id?: string | null; seller_id?: string | null } }) {
  return <FfBillingInvoicesPanel key={sellerCatalogScopeKey(token, me)} token={token} sellerScope />
}

async function clickLoadMore() {
  const loadMore = Array.from(document.querySelectorAll('button')).find(
    (b) => b.textContent?.trim() === 'Загрузить ещё',
  )
  expect(loadMore).toBeTruthy()
  await act(async () => { loadMore!.click() })
  await tick()
}

describe('WMS-549 F1: смена магазина не смешивает страницы истории счетов', () => {
  it('новый токен другого магазина (другой seller_id в claims) со старым me (профиль ещё не пришёл) пересоздаёт панель — S2 без строк S1 и без курсора S1', async () => {
    const tokenS1 = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' })
    const tokenS2 = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's2' })
    const headerCalls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization ?? ''
      headerCalls.push(`${auth} ${url.pathname}${url.search}`)
      if (auth === `Bearer ${tokenS1}`) {
        if (url.searchParams.get('cursor') === 'S1-CURSOR') {
          return new Response(
            JSON.stringify({ invoices: [invoiceRow('s1-second', 'S1-СЧЁТ-2')], next_cursor: null }),
            { status: 200 },
          )
        }
        return new Response(
          JSON.stringify({ invoices: [invoiceRow('s1-first', 'S1-СЧЁТ-1')], next_cursor: 'S1-CURSOR' }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({ invoices: [invoiceRow('s2-bill', 'S2-СЧЁТ-1')], next_cursor: null }),
        { status: 200 },
      )
    }))

    // 1. Сессия S1: первая страница, затем «Загрузить ещё».
    await mount(<Harness token={tokenS1} me={{ active_seller_id: 's1' }} />)
    await tick()
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    await clickLoadMore()
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).not.toBeNull()

    // 2. Переключение магазина: applyToken() уже дал новый токен с seller_id=s2
    // в claims, но me — тот же самый объект, каким он был до ответа /auth/me
    // (он ещё не пришёл, активный селлер там всё ещё 's1').
    await rerender(<Harness token={tokenS2} me={{ active_seller_id: 's1' }} />)
    await tick()

    // Новый ключ (он зависит от seller_id в claims токена, а не только от me)
    // пересоздал панель: в DOM нет ни одной строки S1, есть только строка S2.
    expect(document.querySelector('[data-row-key="s1-first"]')).toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).toBeNull()
    expect(document.querySelector('[data-row-key="s2-bill"]')).not.toBeNull()

    // Запрос новой сессии ушёл без курсора прежней страницы S1.
    const s2Calls = headerCalls.filter((c) => c.startsWith(`Bearer ${tokenS2}`))
    expect(s2Calls.length).toBeGreaterThan(0)
    expect(s2Calls.some((c) => c.includes('cursor=S1-CURSOR'))).toBe(false)
  })

  it('от обратного: со старой формулой ключа (по всей строке me, без claims токена) строка S1 остаётся в DOM после смены магазина', async () => {
    // Тот же сценарий, что и выше, но ключ здесь — старая формула ДО исправления
    // F1 (по me.active_seller_id, без токена вовсе). Тест должен упасть — это
    // подтверждает, что предыдущий тест проверяет настоящую причину, а не
    // побочный эффект окружения.
    const tokenS1 = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' })
    const tokenS2 = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's2' })
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ invoices: [invoiceRow('s1-first', 'S1-СЧЁТ-1')], next_cursor: null }), { status: 200 }),
    ))
    const OldBuggyHarness = ({ token, me }: { token: string; me: { active_seller_id?: string | null } }) => (
      <FfBillingInvoicesPanel key={me.active_seller_id ?? 'none'} token={token} sellerScope />
    )
    await mount(<OldBuggyHarness token={tokenS1} me={{ active_seller_id: 's1' }} />)
    await tick()
    await rerender(<OldBuggyHarness token={tokenS2} me={{ active_seller_id: 's1' }} />)
    await tick()
    // Со старой формулой ключ не меняется (me тот же) — компонент не
    // пересоздаётся, строка S1 остаётся видна вместо пересоздания на S2.
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
  })
})

describe('WMS-549 F6 (ревью Astra №2): перевыпуск токена той же области не сбрасывает раздел', () => {
  it('тот же tenant_id/sub/seller_id в claims (другая подпись токена) — дочитанные страницы остаются в DOM', async () => {
    const tokenA = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' }, '-a')
    const tokenB = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' }, '-b-reissued')
    expect(tokenA).not.toBe(tokenB) // разные строки токена — разные iat/подпись
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.searchParams.get('cursor') === 'S1-CURSOR') {
        return new Response(
          JSON.stringify({ invoices: [invoiceRow('s1-second', 'S1-СЧЁТ-2')], next_cursor: null }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({ invoices: [invoiceRow('s1-first', 'S1-СЧЁТ-1')], next_cursor: 'S1-CURSOR' }),
        { status: 200 },
      )
    }))

    await mount(<Harness token={tokenA} me={{ active_seller_id: 's1' }} />)
    await tick()
    await clickLoadMore()
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).not.toBeNull()

    // Перевыпуск токена той же области (например, будущий silent-refresh или
    // повторный /auth/switch-seller на тот же магазин): claims не изменились,
    // ключ должен остаться прежним — компонент не пересоздаётся.
    await rerender(<Harness token={tokenB} me={{ active_seller_id: 's1' }} />)
    await tick()

    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).not.toBeNull()
  })

  it('от обратного: если бы ключ по-прежнему включал всю строку токена, дочитанная страница терялась бы', async () => {
    const tokenA = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' }, '-a')
    const tokenB = fakeJwt({ tenant_id: 't1', sub: 'manager', seller_id: 's1' }, '-b-reissued')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.searchParams.get('cursor') === 'S1-CURSOR') {
        return new Response(
          JSON.stringify({ invoices: [invoiceRow('s1-second', 'S1-СЧЁТ-2')], next_cursor: null }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({ invoices: [invoiceRow('s1-first', 'S1-СЧЁТ-1')], next_cursor: 'S1-CURSOR' }),
        { status: 200 },
      )
    }))
    // Ключ первого («блокерного») исправления F1 — вся строка токена.
    const RawTokenKeyHarness = ({ token }: { token: string }) => (
      <FfBillingInvoicesPanel key={token} token={token} sellerScope />
    )
    await mount(<RawTokenKeyHarness token={tokenA} />)
    await tick()
    await clickLoadMore()
    expect(document.querySelector('[data-row-key="s1-second"]')).not.toBeNull()

    await rerender(<RawTokenKeyHarness token={tokenB} />)
    await tick()

    // С ключом по всей строке токена перевыпуск (другая подпись) пересоздал
    // панель заново — вторая страница потеряна, ровно дефект F6.
    expect(document.querySelector('[data-row-key="s1-second"]')).toBeNull()
  })
})
