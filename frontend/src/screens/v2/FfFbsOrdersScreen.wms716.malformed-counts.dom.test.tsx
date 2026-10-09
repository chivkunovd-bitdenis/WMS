// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flush, installNetwork, json, mount, order, page, SERVER_NOW } from './test-support/fbsOrdersDom'

// Companion to FfFbsOrdersScreen.wms716.dom.test.tsx. A counts reply that lacks
// the fields the screen reads (tabs, sellers) is treated like a failed read:
// the screen and the order list keep working, and no count circles are shown.
let dispose: (() => Promise<void>) | undefined
afterEach(async () => { await dispose?.(); dispose = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks() })

function network(countsBody: unknown) {
  return installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/counts')) return json(countsBody)
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page([order('one'), order('two'), order('three')]))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: SERVER_NOW })
    throw new Error(`Unexpected request: ${url}`)
  })
}

function tabs() {
  return Array.from(document.querySelectorAll('[role="tab"]'))
}

describe('WMS-716 malformed counts reply', () => {
  for (const [name, body] of [['an empty object', {}], ['a list-only reply', { items: [] }]] as const) {
    it(`keeps the screen, order list and seller filter working for ${name} and shows no count circles`, async () => {
      dispose = await mount(network(body))

      expect(document.querySelector('[data-testid="fbs-order-one"]')).toBeTruthy()
      expect(tabs().length).toBeGreaterThan(0)
      for (const node of tabs()) expect(node.textContent, node.textContent ?? '').not.toMatch(/\d/)
      // Same contract as a failed counts read: the existing alert is shown.
      expect(document.querySelector('[role="alert"]')).toBeTruthy()

      const control = document.querySelector('[aria-labelledby~="fbs-worklist-seller-label"][role="combobox"]')!
      expect(control).toBeTruthy()
      await act(async () => control.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
      await flush()
      const options = Array.from(document.querySelectorAll('[role="option"]'))
      expect(options.map((node) => node.textContent)).toEqual(expect.arrayContaining(['Селлер А', 'Селлер Б']))
      for (const node of options) expect(node.textContent, node.textContent ?? '').not.toMatch(/\d/)
      expect(document.querySelector('[data-testid="fbs-order-one"]')).toBeTruthy()
    })
  }
})
