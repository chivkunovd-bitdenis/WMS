// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { sellerCatalogScopeKey } from './SellerApp'
import { FfBillingInvoicesPanel } from '../../screens/ff/FfBillingInvoicesPanel'

// WMS-549 (ревью Astra, проход 1, F1 — блокер): при переключении магазина
// applyToken() меняет токен раньше, чем приходит обновлённый /auth/me. Раньше
// ключ пересоздания раздела считался только по me.active_seller_id, поэтому в
// этом окне экран уже держал новый токен со старым ключом — панель истории
// счетов не пересоздавалась и дочитывала следующую страницу токеном новой
// сессии, но курсором прежней; строки чужого магазина дописывались к своим.
// Тест воспроизводит ровно это окно (me ещё старый, токен уже новый) с
// настоящим React-рендером FfBillingInvoicesPanel в jsdom и проверяет, что
// пересоздание по новому ключу не даёт двум сессиям встретиться в DOM.

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

describe('WMS-549 F1: переключение магазина не смешивает страницы истории счетов', () => {
  it('новый токен со старым me (профиль ещё не пришёл) пересоздаёт панель — S2 без строк S1 и без курсора S1', async () => {
    const headerCalls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization ?? ''
      headerCalls.push(`${auth} ${url.pathname}${url.search}`)
      if (auth === 'Bearer S1-TOKEN') {
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
    await mount(<Harness token="S1-TOKEN" me={{ active_seller_id: 's1' }} />)
    await tick()
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    const loadMore = Array.from(document.querySelectorAll('button')).find(
      (b) => b.textContent?.trim() === 'Загрузить ещё',
    )
    expect(loadMore).toBeTruthy()
    await act(async () => { loadMore!.click() })
    await tick()
    expect(document.querySelector('[data-row-key="s1-first"]')).not.toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).not.toBeNull()

    // 2. Переключение магазина: applyToken() уже дал новый токен S2, но me —
    // тот же самый объект, каким он был до ответа /auth/me (он ещё не пришёл).
    await rerender(<Harness token="S2-TOKEN" me={{ active_seller_id: 's1' }} />)
    await tick()

    // Новый ключ (он зависит от токена, а не только от me) пересоздал панель:
    // в DOM нет ни одной строки S1, есть только строка S2.
    expect(document.querySelector('[data-row-key="s1-first"]')).toBeNull()
    expect(document.querySelector('[data-row-key="s1-second"]')).toBeNull()
    expect(document.querySelector('[data-row-key="s2-bill"]')).not.toBeNull()

    // Запрос новой сессии ушёл без курсора прежней страницы S1.
    const s2Calls = headerCalls.filter((c) => c.startsWith('Bearer S2-TOKEN'))
    expect(s2Calls.length).toBeGreaterThan(0)
    expect(s2Calls.some((c) => c.includes('cursor=S1-CURSOR'))).toBe(false)
  })
})
