import { useSyncExternalStore } from 'react'

/**
 * WMS-649 · защита от настоящей печати и журнал «что ушло бы на принтер».
 *
 * Макет не должен открывать окна печати и посылать задания принтеру. Все печатные
 * функции продукта работают через скрытый iframe и вызывают у его окна `print()`.
 * Здесь `print()` подменяется: вместо печати берём HTML, который был бы
 * напечатан, и кладём в журнал. По журналу видно, ЧЕЙ штрихкод ушёл бы на ленту.
 *
 * Продуктовый код при этом не меняется: подмена живёт только на странице макета.
 */

export type PrintedBarcode = { code: string; count: number }

export type PrintJob = {
  id: number
  at: number
  /** Подпись формы, из которой печатали (ставит макет). */
  formLabel: string
  barcodes: PrintedBarcode[]
  /** Лист подбора: строки «товар: идентификаторы» (ШК стоит среди идентификаторов). */
  rows: string[]
  /** Заголовок документа печати — по нему видно, этикетка это или лист. */
  title: string
  html: string
}

let jobs: PrintJob[] = []
let nextId = 1
let currentFormLabel = ''
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

export function setCurrentFormLabel(label: string): void {
  currentFormLabel = label
}

export function clearPrintJobs(): void {
  jobs = []
  emit()
}

export function usePrintJobs(): PrintJob[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => jobs,
  )
}

function extractBarcodes(html: string): PrintedBarcode[] {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const counts = new Map<string, number>()
  // Этикетка товара: <p class="digits">ШК</p>. Лист/накладная: ячейка ШК.
  const selectors = [
    '.digits',
    '[data-testid="receiving-sheet-barcode"]',
    '[data-testid="shipment-sheet-barcode"]',
    '[data-barcode]',
  ]
  for (const selector of selectors) {
    doc.querySelectorAll(selector).forEach((node) => {
      const raw = node.getAttribute('data-barcode') ?? node.textContent ?? ''
      for (const part of raw.split(/[\n,]+/)) {
        const code = part.replace(/\s+/g, ' ').trim()
        if (code && code !== '—') counts.set(code, (counts.get(code) ?? 0) + 1)
      }
    })
  }
  return [...counts].map(([code, count]) => ({ code, count }))
}

function extractRows(html: string): string[] {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return [...doc.querySelectorAll('tr')]
    .map((row) => {
      const name = row.querySelector('strong')?.textContent?.trim()
      const muted = row.querySelector('.muted')?.textContent?.trim()
      return name && muted ? `${name}: ${muted}` : null
    })
    .filter((item): item is string => Boolean(item))
}

function record(html: string): void {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const job: PrintJob = {
    id: nextId++,
    at: Date.now(),
    formLabel: currentFormLabel,
    barcodes: extractBarcodes(html),
    rows: extractRows(html),
    title: doc.title || 'Печатная форма',
    html,
  }
  jobs = [job, ...jobs].slice(0, 30)
  emit()
}

let installed = false

export function installPrintGuard(): void {
  if (installed) return
  installed = true

  // Флаг «захвата» продукта не включаем: часть печатных функций при нём вообще не
  // доходит до iframe. Без флага они идут обычным путём, а print() перехвачен ниже.
  window.print = () => {}
  // Часть форм (лист подбора, резерв окна под печать ленты) открывает для печати
  // отдельное окно. В макете вместо настоящего окна отдаём скрытый iframe: код
  // продукта пишет в него документ так же, как в окно, а print() перехвачен ниже.
  const ownedFrames = new WeakMap<Window, HTMLIFrameElement>()
  window.open = () => {
    const frame = document.createElement('iframe')
    frame.setAttribute('aria-hidden', 'true')
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:210mm;height:297mm;border:0'
    document.body.appendChild(frame)
    const frameWindow = frame.contentWindow
    if (frameWindow) ownedFrames.set(frameWindow, frame)
    return frameWindow
  }

  const descriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow')
  if (!descriptor?.get) return
  const getter = descriptor.get
  const patched = new WeakSet<object>()
  Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    configurable: true,
    get(this: HTMLIFrameElement) {
      const w = getter.call(this) as Window | null
      if (w && !patched.has(w)) {
        patched.add(w)
        try {
          w.print = () => {
            try {
              record(w.document.documentElement.outerHTML)
            } catch {
              // Документ уже убран — журнал просто не пополнится.
            }
            // Продукт чистит iframe по событию «печать закончена» — подаём его сами.
            window.setTimeout(() => {
              try {
                w.dispatchEvent(new Event('afterprint'))
              } catch {
                // окно уже закрыто
              }
            }, 50)
            const owned = ownedFrames.get(w)
            if (owned) window.setTimeout(() => owned.remove(), 2000)
          }
        } catch {
          // Чужое окно (PDF viewer) — подменить нельзя, но и напечатать оно не успеет.
        }
      }
      return w
    },
  })

  // Лента с нативным PDF селлера уходит в печать через blob-iframe; макет такой
  // путь не обслуживает, поэтому подставной сервер не отдаёт артефактов ЧЗ.
}
