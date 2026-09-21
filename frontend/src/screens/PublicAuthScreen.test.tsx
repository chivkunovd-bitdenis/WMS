import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PublicAuthScreen } from './PublicAuthScreen'

const handlers = {
  onRegister: vi.fn(),
  onLogin: vi.fn(),
  onSetPasswordByLink: vi.fn(),
  onRequestPasswordReset: vi.fn(),
  clearNotice: vi.fn(),
}

afterEach(() => vi.unstubAllGlobals())

describe('public registration entry point', () => {
  it('offers organization registration alongside login and password recovery for FF', () => {
    const html = renderToStaticMarkup(<PublicAuthScreen
      variant="fulfillment" error={null} notice={null} authBusy={false} {...handlers}
    />)
    expect(html).toContain('Регистрация организации (первый админ)')
    expect(html).toContain('data-testid="go-to-register"')
    expect(html).toContain('data-testid="login-form"')
    expect(html).toContain('data-testid="go-to-forgot-password"')
    expect(html).toContain('data-testid="go-to-seller-portal"')
  })

  it('never offers organization registration on the seller portal', () => {
    const html = renderToStaticMarkup(<PublicAuthScreen
      variant="seller" error={null} notice={null} authBusy={false} {...handlers}
    />)
    expect(html).not.toContain('go-to-register')
    expect(html).not.toContain('register-form')
    expect(html).toContain('data-testid="login-form"')
    expect(html).toContain('data-testid="go-to-forgot-password"')
  })

  it.each(['fulfillment', 'seller'] as const)('preserves password-link priority for %s', (variant) => {
    vi.stubGlobal('window', {
      location: { pathname: '/set-password', search: '?token=test-link-token' },
    })
    const html = renderToStaticMarkup(<PublicAuthScreen
      variant={variant} error={null} notice={null} authBusy={false} {...handlers}
    />)
    expect(html).toContain('data-testid="set-password-form"')
    expect(html).not.toContain('go-to-register')
    expect(html).not.toContain('data-testid="login-form"')
  })
})
