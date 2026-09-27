// Кликабельный макет пакета PSP-2 (WMS-490, WMS-491, WMS-497, WMS-547, WMS-548, WMS-549).
//
// Это настоящие приложения фулфилмента и селлера — те же App и SellerApp, та же
// тема и то же меню, — только без сервера: глобальный fetch подменён на
// src/mockups/psp2/server.ts, который отвечает выдуманными согласованными
// данными и меняет их в памяти. Сверху полоса макета переключает кабинет;
// в продукт она не входит.

import { StrictMode, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import '../index.css'
import '../ui/ui.css'
import './psp2/mockup.css'
import App from '../App'
import { SellerApp } from '../apps/seller/SellerApp'
import { ErrorBoundary, RootRouteError } from '../components/errors/ErrorBoundary'
import { muiTheme } from '../mui/theme'
import { WmsDatePickersProvider } from '../mui/WmsDatePickersProvider'
import { FF_TOKEN, SELLER_TOKEN, handleRequest, unmocked } from './psp2/server'

// ── Хранилище: в изолированном окне localStorage может быть недоступен ──────
function ensureStorage() {
  try {
    const probe = '__psp2_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
  } catch {
    const memory = new Map<string, string>()
    const storage: Storage = {
      get length() {
        return memory.size
      },
      clear: () => memory.clear(),
      getItem: (key) => (memory.has(key) ? memory.get(key)! : null),
      key: (index) => [...memory.keys()][index] ?? null,
      removeItem: (key) => {
        memory.delete(key)
      },
      setItem: (key, value) => {
        memory.set(key, String(value))
      },
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
  }
  window.localStorage.setItem('wms_token_ff', FF_TOKEN)
  window.localStorage.setItem('wms_token_seller', SELLER_TOKEN)
}

// ── Подставной fetch ────────────────────────────────────────────────────────
function headerValue(headers: HeadersInit | undefined, name: string): string | null {
  if (!headers) return null
  if (headers instanceof Headers) return headers.get(name)
  if (Array.isArray(headers)) return headers.find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? null
  const record = headers as Record<string, string>
  const key = Object.keys(record).find((k) => k.toLowerCase() === name.toLowerCase())
  return key ? record[key] ?? null : null
}

function installStubFetch() {
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const path = raw.replace(/^https?:\/\/[^/]+/, '')
    if (!path.startsWith('/api/')) return original(input, init)
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined)
    const abortError = () => new DOMException('The operation was aborted.', 'AbortError')
    if (signal?.aborted) throw abortError()
    // Небольшая задержка — как у настоящего сервера: видно состояние загрузки.
    await new Promise((resolve) => window.setTimeout(resolve, 90))
    if (signal?.aborted) throw abortError()
    let body: unknown = null
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body)
      } catch {
        body = init.body
      }
    }
    const authorization = headerValue(init?.headers, 'Authorization') ?? (input instanceof Request ? input.headers.get('Authorization') : null)
    const result = handleRequest(method, path.replace(/^\/api/, ''), body, authorization)
    return new Response(JSON.stringify(result.body ?? null), {
      status: result.status,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}

// ── Печать: вместо системного окна — предпросмотр листа поверх страницы ──────
type PrintListener = (html: string) => void
let printListener: PrintListener | null = null

function showPrintPreview(html: string) {
  printListener?.(html)
}

function installPrintPreview() {
  // Скрытый iframe (лист инвентаризации, опись тары): подменяем его print().
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      record.addedNodes.forEach((node) => {
        if (!(node instanceof HTMLIFrameElement)) return
        node.addEventListener('load', () => {
          const frameWindow = node.contentWindow
          if (!frameWindow) return
          try {
            frameWindow.print = () => {
              showPrintPreview(node.srcdoc || frameWindow.document.documentElement.outerHTML)
              window.setTimeout(() => frameWindow.dispatchEvent(new Event('afterprint')), 0)
            }
          } catch {
            // чужой источник — не наш случай
          }
        })
      })
    }
  })
  observer.observe(document.body, { childList: true })
  // Печать через новое окно (счёт): собираем то, что туда пишут, и показываем.
  const originalOpen = window.open.bind(window)
  window.open = ((url?: string | URL, target?: string, features?: string) => {
    if (url && String(url) !== '' && String(url) !== 'about:blank') return originalOpen(url, target, features)
    let html = ''
    const fakeDocument = {
      write: (chunk: string) => {
        html += chunk
      },
      close: () => undefined,
      open: () => undefined,
    }
    return {
      document: fakeDocument,
      focus: () => undefined,
      close: () => undefined,
      print: () => showPrintPreview(html),
      addEventListener: () => undefined,
    } as unknown as Window
  }) as typeof window.open
}

function PrintPreview() {
  const [html, setHtml] = useState<string | null>(null)
  useEffect(() => {
    printListener = setHtml
    return () => {
      printListener = null
    }
  }, [])
  useEffect(() => {
    if (!html) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHtml(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [html])
  if (!html) return null
  return (
    <div className="psp2-print" role="dialog" aria-label="Предпросмотр печати" data-testid="psp2-print-preview" onClick={() => setHtml(null)}>
      <div className="psp2-print__panel" onClick={(event) => event.stopPropagation()}>
        <div className="psp2-print__head">
          <span>Печать</span>
          <button type="button" onClick={() => setHtml(null)} data-testid="psp2-print-close">
            Закрыть
          </button>
        </div>
        <iframe className="psp2-print__frame" title="Лист для печати" srcDoc={html} data-testid="psp2-print-frame" />
      </div>
    </div>
  )
}

// ── Кабинеты ────────────────────────────────────────────────────────────────
type Cabinet = 'ff' | 'seller'
const FF_START = '#/app/ff/products'
const SELLER_START = '#/seller/products'

function cabinetFromHash(): Cabinet {
  return window.location.hash.startsWith('#/seller') ? 'seller' : 'ff'
}

function buildRouter(cabinet: Cabinet) {
  if (cabinet === 'seller') {
    return createHashRouter(
      [
        {
          path: '*',
          element: (
            <ErrorBoundary component="SellerApp" root portal="seller">
              <SellerApp />
            </ErrorBoundary>
          ),
          errorElement: <RootRouteError portal="seller" />,
        },
      ],
      { basename: '/seller' },
    )
  }
  return createHashRouter([
    {
      path: '*',
      element: (
        <ErrorBoundary component="App" root>
          <App />
        </ErrorBoundary>
      ),
      errorElement: <RootRouteError portal="fulfillment" />,
    },
  ])
}

function Mockup() {
  const [cabinet, setCabinet] = useState<Cabinet>(cabinetFromHash)
  const router = useMemo(() => buildRouter(cabinet), [cabinet])
  useEffect(() => () => router.dispose(), [router])
  useEffect(() => {
    const onHash = () => {
      const next = cabinetFromHash()
      setCabinet((current) => (current === next ? current : next))
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const switchTo = (next: Cabinet) => {
    if (next === cabinet) return
    // Адрес меняем без события навигации: роутер уходящего кабинета не должен
    // принимать чужой адрес за свой переход (у кабинета ФФ на переходах стоит
    // защита несохранённого ввода). Новый роутер прочитает адрес при создании.
    window.history.replaceState(null, '', next === 'seller' ? SELLER_START : FF_START)
    setCabinet(next)
    window.scrollTo(0, 0)
  }

  return (
    <>
      <div className="psp2-bar" data-testid="psp2-bar">
        <span className="psp2-bar__label">Макет PSP-2</span>
        <div className="psp2-bar__switch" role="group" aria-label="Кабинет">
          <button type="button" aria-pressed={cabinet === 'ff'} onClick={() => switchTo('ff')} data-testid="psp2-cabinet-ff">
            Фулфилмент
          </button>
          <button type="button" aria-pressed={cabinet === 'seller'} onClick={() => switchTo('seller')} data-testid="psp2-cabinet-seller">
            Селлер
          </button>
        </div>
      </div>
      <RouterProvider key={cabinet} router={router} />
      <PrintPreview />
    </>
  )
}

ensureStorage()
installStubFetch()
installPrintPreview()
document.body.classList.add('psp2')
if (!window.location.hash || window.location.hash === '#' || window.location.hash === '#/') {
  window.history.replaceState(null, '', FF_START)
}
;(window as unknown as { __psp2: { unmocked: string[] } }).__psp2 = { unmocked }

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <ErrorBoundary component="portal" root portal="fulfillment">
        <WmsDatePickersProvider>
          <Mockup />
        </WmsDatePickersProvider>
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
)
