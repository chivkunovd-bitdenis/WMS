// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../hooks/useAuth'
import { PublicAuthScreen } from './PublicAuthScreen'

// WMS-753 R1, C3 (догон): одно поле «Email или ФИО» на странице входа.
// Монтируются настоящие PublicAuthScreen и useAuth; сеть перехватывается только
// на уровне fetch, поэтому видно, на какой эндпоинт и с каким телом уходит вход.

const PASSWORD = 'test-password'

function AuthEntry() {
  const auth = useAuth('fulfillment')
  return (
    <PublicAuthScreen
      variant="fulfillment"
      error={auth.error}
      notice={auth.notice}
      authBusy={auth.authBusy}
      onLogin={auth.onLogin}
      onSetPasswordByLink={auth.onSetPasswordByLink}
      onRequestPasswordReset={auth.onRequestPasswordReset}
      clearNotice={auth.clearNotice}
    />
  )
}

let root: Root
let host: HTMLDivElement
let requests: Array<{ url: string; body: unknown }>

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ url: String(input), body: JSON.parse(String(init?.body ?? 'null')) })
    return new Response(JSON.stringify({ detail: 'invalid_credentials' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
  }))
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

async function mountEntry() {
  await act(async () => { root.render(<AuthEntry />) })
}

function loginForm(): HTMLFormElement {
  const form = document.querySelector<HTMLFormElement>('[data-testid="login-form"]')
  expect(form, 'форма входа').toBeTruthy()
  return form!
}

/** Значение поля задаём так же, как браузер: нативный сеттер и событие input. */
function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

/** Логин-поле — первое непарольное поле формы входа, какой бы у него ни был тип. */
async function submitLogin(login: string) {
  const form = loginForm()
  const loginInput = form.querySelector<HTMLInputElement>('input:not([type="password"])')
  const passwordInput = form.querySelector<HTMLInputElement>('input[type="password"]')
  expect(loginInput, 'поле логина').toBeTruthy()
  expect(passwordInput, 'поле пароля').toBeTruthy()
  await act(async () => {
    typeInto(loginInput!, login)
    typeInto(passwordInput!, PASSWORD)
  })
  await act(async () => { form.requestSubmit() })
  await waitFor(() => expect(requests.length, 'запрос входа ушёл').toBeGreaterThan(0))
}

async function waitFor(check: () => void) {
  let last: unknown
  for (let attempt = 0; attempt < 200; attempt++) {
    try {
      check()
      return
    } catch (error) {
      last = error
    }
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  }
  throw last
}

describe('WMS-753 вход на сайт по почте или ФИО', () => {
  it('R1: поле входа подписано «Email или ФИО»', async () => {
    await mountEntry()
    const labels = [...loginForm().querySelectorAll('label')].map((node) => node.textContent ?? '')
    expect(labels.some((text) => text.startsWith('Email или ФИО')), `подписи полей: ${labels.join(' | ')}`).toBe(true)
  })

  it('C3: без «@» вход идёт по ФИО и паролю на /auth/login-by-name, как на ТСД', async () => {
    await mountEntry()
    await submitLogin('Иванов Иван')
    expect(requests).toHaveLength(1)
    expect(requests[0]!.url).toMatch(/\/auth\/login-by-name$/)
    expect(requests[0]!.body).toEqual({ full_name: 'Иванов Иван', password: PASSWORD })
  })

  it('R1: с «@» вход по почте остаётся на /auth/login с ролью портала', async () => {
    await mountEntry()
    await submitLogin('ivan@example.com')
    expect(requests).toHaveLength(1)
    expect(requests[0]!.url).toMatch(/\/auth\/login$/)
    expect(requests[0]!.body).toEqual({ email: 'ivan@example.com', password: PASSWORD, portal: 'fulfillment' })
  })
})
