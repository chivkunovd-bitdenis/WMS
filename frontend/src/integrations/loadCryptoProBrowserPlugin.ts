import { CryptoProError } from './cryptoProCades'

const SCRIPT_ID = 'wms-cryptopro-cades-api'
export const CRYPTO_PRO_SCRIPT_SRC = '/vendor/cryptopro/cadesplugin_api.js'
const DEFAULT_TIMEOUT_MS = 15_000

type CryptoProWindow = Window & { cadesplugin?: unknown }

let pendingLoad: Promise<void> | null = null

const awaitRuntimePromise = async (runtime: unknown): Promise<void> => {
  if ((typeof runtime !== 'object' && typeof runtime !== 'function') || runtime === null) {
    throw new CryptoProError('plugin_unavailable')
  }
  const then = (runtime as { then?: unknown }).then
  if (typeof then === 'function') {
    await new Promise<void>((resolve, reject) => {
      Reflect.apply(then, runtime, [resolve, reject])
    })
  }
}

const withTimeout = async (promise: Promise<void>, timeoutMs: number): Promise<void> => {
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  try {
    await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timeoutId = setTimeout(() => reject(new CryptoProError('plugin_load_timeout')), timeoutMs)
      }),
    ])
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId)
  }
}

const loadScriptAndRuntime = async (): Promise<void> => {
  const browserWindow = window as CryptoProWindow
  if (browserWindow.cadesplugin !== undefined) {
    await awaitRuntimePromise(browserWindow.cadesplugin)
    return
  }

  await new Promise<void>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null
    const script = existing ?? document.createElement('script')
    const onLoad = () => {
      script.dataset.wmsLoaded = 'true'
      const runtime = browserWindow.cadesplugin
      if (runtime === undefined) {
        reject(new CryptoProError('plugin_unavailable'))
        return
      }
      void awaitRuntimePromise(runtime).then(resolve, reject)
    }
    const onError = () => {
      if (!existing) script.remove()
      reject(new CryptoProError('plugin_script_missing'))
    }

    if (existing?.dataset.wmsLoaded === 'true') {
      reject(new CryptoProError('plugin_unavailable'))
      return
    }
    script.addEventListener('load', onLoad, { once: true })
    script.addEventListener('error', onError, { once: true })
    if (!existing) {
      script.id = SCRIPT_ID
      script.src = CRYPTO_PRO_SCRIPT_SRC
      script.async = true
      document.head.appendChild(script)
    }
  })
}

export const loadCryptoProBrowserPlugin = async (
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<void> => {
  if (typeof window === 'undefined') throw new CryptoProError('plugin_script_missing')
  if (pendingLoad) return pendingLoad

  pendingLoad = withTimeout(loadScriptAndRuntime(), timeoutMs).finally(() => {
    pendingLoad = null
  })

  return pendingLoad
}
