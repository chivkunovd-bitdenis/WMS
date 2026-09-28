// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { AuthedAppLayout } from './AuthedAppLayout'
import { SellerLayout } from '../apps/seller/SellerLayout'
import { emptySellerPermissions, type SellerPermissions } from '../utils/sellerPermissions'

// WMS-567: логотип и надпись «Короб ВМС» в шапке — ссылка роутера на главную
// портала. ФФ — «Календарь отгрузок» (/app/ff/dashboard); селлер — та же
// страница, что открывает корень портала (firstAllowedSellerPath).

vi.setConfig({ testTimeout: 30000 })

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let root: Root | null = null
let host: HTMLDivElement | null = null

async function mount(element: React.ReactElement) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(element)
  })
}

afterEach(async () => {
  await act(async () => {
    root?.unmount()
  })
  host?.remove()
  root = null
  host = null
})

function PathProbe() {
  const location = useLocation()
  return <div data-testid="path-probe">{location.pathname}</div>
}

function currentPath() {
  return document.querySelector('[data-testid="path-probe"]')?.textContent
}

function homeLink() {
  const link = document.querySelector('[data-testid="app-topbar"] [data-testid="topbar-home-link"]')
  expect(link).not.toBeNull()
  return link as HTMLAnchorElement
}

async function click(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }))
  })
}

describe('WMS-567 портал ФФ: логотип ведёт на «Календарь отгрузок»', () => {
  async function mountFf(entry: string) {
    await mount(
      <MemoryRouter initialEntries={[entry]}>
        <AuthedAppLayout portal="ff" onLogout={() => {}} meRole="fulfillment_admin">
          <PathProbe />
        </AuthedAppLayout>
      </MemoryRouter>,
    )
  }

  it('клик по логотипу со «Приёмки» открывает /app/ff/dashboard', async () => {
    await mountFf('/app/ff/reception')
    const link = homeLink()
    expect(link.tagName).toBe('A')
    expect(link.getAttribute('href')).toBe('/app/ff/dashboard')

    await click(link.querySelector('img')!)
    expect(currentPath()).toBe('/app/ff/dashboard')
  })

  it('клик по надписи «Короб ВМС» тоже ведёт на календарь', async () => {
    await mountFf('/app/ff/settings')
    const title = [...homeLink().querySelectorAll('h5')].find((el) => el.textContent === 'Короб ВМС')
    expect(title).toBeDefined()

    await click(title!)
    expect(currentPath()).toBe('/app/ff/dashboard')
  })
})

describe('WMS-567 портал селлера: логотип ведёт на стартовую страницу', () => {
  async function mountSeller(entry: string, permissions: SellerPermissions) {
    await mount(
      <MemoryRouter initialEntries={[entry]}>
        <SellerLayout onLogout={() => {}} permissions={permissions}>
          <Routes>
            <Route path="*" element={<PathProbe />} />
          </Routes>
        </SellerLayout>
      </MemoryRouter>,
    )
  }

  it('владелец со всеми правами попадает на «Документы»', async () => {
    const all: SellerPermissions = {
      ...emptySellerPermissions(),
      documents: true,
      products: true,
      honest_sign: true,
      settings: true,
      staff: true,
    }
    await mountSeller('/products', all)
    expect(homeLink().getAttribute('href')).toBe('/documents')

    await click(homeLink().querySelector('img')!)
    expect(currentPath()).toBe('/documents')
  })

  it('сотрудник только с правом на товары попадает на «Товары»', async () => {
    await mountSeller('/reports', { ...emptySellerPermissions(), products: true })

    await click(homeLink())
    expect(currentPath()).toBe('/products')
  })

  it('«бургер» и подпись «Портал селлера» в ссылку не входят', async () => {
    await mountSeller('/products', { ...emptySellerPermissions(), products: true })
    const link = homeLink()
    const burger = document.querySelector('[data-testid="app-topbar"] button[aria-label="Открыть меню"]')
    expect(burger).not.toBeNull()
    expect(link.contains(burger)).toBe(false)
    expect(link.textContent).toBe('Короб ВМС')

    await click(burger!)
    expect(currentPath()).toBe('/products')
  })
})
