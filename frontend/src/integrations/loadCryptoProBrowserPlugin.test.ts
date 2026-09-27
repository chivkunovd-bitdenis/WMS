import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  CRYPTO_PRO_SCRIPT_SRC,
  loadCryptoProBrowserPlugin,
} from './loadCryptoProBrowserPlugin'

type Listener = () => void

const installDocument = () => {
  const listeners = new Map<string, Listener>()
  const script = {
    id: '',
    src: '',
    async: false,
    dataset: {} as Record<string, string>,
    addEventListener: vi.fn((type: string, listener: Listener) => listeners.set(type, listener)),
    remove: vi.fn(),
  }
  let mounted: typeof script | null = null
  vi.stubGlobal('document', {
    getElementById: vi.fn(() => mounted),
    createElement: vi.fn(() => script),
    head: { appendChild: vi.fn((value: typeof script) => { mounted = value }) },
  })
  return { listeners, script }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('CryptoPro browser runtime loader', () => {
  it('loads the pinned same-origin asset and waits for the runtime promise, not only script.onload', async () => {
    const { listeners, script } = installDocument()
    let runtimeReady: (() => void) | undefined
    const browserWindow: { cadesplugin?: unknown } = {}
    vi.stubGlobal('window', browserWindow)

    let settled = false
    const loading = loadCryptoProBrowserPlugin(1_000).then(() => { settled = true })
    browserWindow.cadesplugin = {
      then: (resolve: () => void) => { runtimeReady = resolve },
    }
    listeners.get('load')?.()
    await Promise.resolve()

    expect(script.src).toBe(CRYPTO_PRO_SCRIPT_SRC)
    expect(settled).toBe(false)
    runtimeReady?.()
    await loading
    expect(settled).toBe(true)
  })

  it('reports a bounded timeout when the native runtime never becomes ready', async () => {
    vi.useFakeTimers()
    installDocument()
    vi.stubGlobal('window', {
      cadesplugin: { then: vi.fn() },
    })

    const loading = loadCryptoProBrowserPlugin(25)
    const assertion = expect(loading).rejects.toMatchObject({
      code: 'plugin_load_timeout',
    })
    await vi.advanceTimersByTimeAsync(25)
    await assertion
  })

  it('does not accept a loaded script that failed to publish window.cadesplugin', async () => {
    const { listeners } = installDocument()
    vi.stubGlobal('window', {})

    const loading = loadCryptoProBrowserPlugin(1_000)
    listeners.get('load')?.()
    await expect(loading).rejects.toMatchObject({ code: 'plugin_unavailable' })
  })
})
