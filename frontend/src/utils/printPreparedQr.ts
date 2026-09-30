/** Browser printing; Chrome must have silent printing configured on the workstation. */
export type PreparedQrInput = {
  imageDataUrl: string
  idempotencyKey: string
  widthMm: number
  heightMm: number
}

type Dispatch = { fingerprint: string; state: 'dispatched' | 'browser-ended' }
const storagePrefix = 'wms:qr-print:'
let queue: Promise<void> = Promise.resolve()

async function fingerprint(input: PreparedQrInput): Promise<string> {
  const bytes = new TextEncoder().encode(`${input.widthMm}:${input.heightMm}:${input.imageDataUrl}`)
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

async function dispatch(input: PreparedQrInput): Promise<void> {
  if (!input.idempotencyKey || !/^data:image\/(?:png|jpeg|webp);base64,[a-zA-Z0-9+/=]+$/.test(input.imageDataUrl)
    || ![input.widthMm, input.heightMm].every((size) => Number.isFinite(size) && size > 0 && size <= 300)) {
    throw new Error('Некорректная этикетка для печати')
  }
  // Chrome silent printing uses the printer's portrait media orientation.
  // Normalize the same physical sheet to avoid clipping landscape CSS pages.
  const pageWidth = Math.min(input.widthMm, input.heightMm)
  const pageHeight = Math.max(input.widthMm, input.heightMm)
  const key = `${storagePrefix}${input.idempotencyKey}`
  const hash = await fingerprint(input)
  const existingRaw = localStorage.getItem(key)
  if (existingRaw) {
    const existing = JSON.parse(existingRaw) as Dispatch
    if (existing.fingerprint !== hash) throw new Error('Этикетка этого задания изменилась. Повторная печать остановлена.')
    if (existing.state === 'browser-ended') return
    throw new Error('Это задание уже передано браузеру. Проверьте этикетку и очередь принтера перед повторной печатью.')
  }

  await new Promise<void>((resolve, reject) => {
    const frame = document.createElement('iframe')
    frame.setAttribute('aria-hidden', 'true')
    frame.tabIndex = -1
    Object.assign(frame.style, { position: 'fixed', left: '-10000px', top: '0', width: `${pageWidth}mm`, height: `${pageHeight}mm`, border: '0' })
    let settled = false
    let crossedPrintBoundary = false
    const active = document.activeElement
    const restoreFocus = () => {
      if ((document.activeElement === frame || document.activeElement === document.body) && active instanceof HTMLElement && active.isConnected) active.focus({ preventScroll: true })
    }
    const settle = (error?: unknown) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      if (error) reject(error)
      else resolve()
    }
    const timeout = window.setTimeout(() => {
      if (!crossedPrintBoundary) frame.remove()
      settle(new Error(crossedPrintBoundary
        ? 'Браузер не подтвердил завершение печати. Проверьте этикетку и очередь принтера.'
        : 'Не удалось подготовить этикетку для печати.'))
    }, 60_000)
    frame.onload = async () => {
      frame.onload = null
      try {
        const target = frame.contentWindow
        const image = frame.contentDocument?.querySelector('img')
        if (!target || !image) throw new Error('Не удалось открыть этикетку для печати.')
        await image.decode()
        if (settled) return
        target.addEventListener('afterprint', () => {
          // afterprint means the browser flow ended. It cannot prove paper output
          // or distinguish cancellation in a Chrome without silent-print settings.
          try {
            localStorage.setItem(key, JSON.stringify({ fingerprint: hash, state: 'browser-ended' } satisfies Dispatch))
            frame.remove()
            restoreFocus()
            settle()
          } catch (error) { settle(error) }
        }, { once: true })
        // Persist before the irreversible call: a reload/lost event must never
        // automatically submit the same label again.
        localStorage.setItem(key, JSON.stringify({ fingerprint: hash, state: 'dispatched' } satisfies Dispatch))
        crossedPrintBoundary = true
        target.print()
        restoreFocus()
      } catch (error) {
        frame.remove()
        restoreFocus()
        settle(error)
      }
    }
    frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><title>WMS label</title><style>
      @page { size: ${pageWidth}mm ${pageHeight}mm; margin: 0; }
      html, body { margin: 0; padding: 0; }
      img { position: fixed; inset: 0; display: block; box-sizing: border-box; width: 100%; height: 100%; padding: 2mm; object-fit: contain; image-rendering: pixelated; }
      </style></head><body><img src="${input.imageDataUrl}" alt=""></body></html>`
    document.body.appendChild(frame)
  })
}

/** Resolves after browser print flow ends, not after a physical printer receipt. */
export function printPreparedQr(input: PreparedQrInput): Promise<void> {
  const run = () => navigator.locks
    ? navigator.locks.request('wms-qr-print', () => dispatch(input))
    : dispatch(input)
  const result = queue.then(run, run)
  queue = result.catch(() => undefined)
  return result
}
