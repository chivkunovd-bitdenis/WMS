/** Browser printing; Chrome must have silent printing configured on the workstation. */
export type PreparedQrInput = {
  imageDataUrl: string
  idempotencyKey: string
  widthMm: number
  heightMm: number
}

type Dispatch = { fingerprint: string; state: 'dispatched' | 'browser-ended' | 'operator-confirmed' }
const storagePrefix = 'wms:qr-print:'
let queue: Promise<void> = Promise.resolve()

async function fingerprint(input: PreparedQrInput): Promise<string> {
  const bytes = new TextEncoder().encode(`${input.widthMm}:${input.heightMm}:${input.imageDataUrl}`)
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

async function dispatch(input: PreparedQrInput, checkOnly: boolean, kiosk: boolean): Promise<void> {
  if (!input.idempotencyKey || !/^data:image\/(?:png|jpeg|webp);base64,[a-zA-Z0-9+/=]+$/.test(input.imageDataUrl)
    || ![input.widthMm, input.heightMm].every((size) => Number.isFinite(size) && size > 0 && size <= 300)) {
    throw new Error('Некорректная этикетка для печати')
  }
  // Chrome's silent path uses portrait media. Rotate the complete landscape
  // label onto that sheet, preserving the existing label box and zero padding.
  const pageWidth = Math.min(input.widthMm, input.heightMm)
  const pageHeight = Math.max(input.widthMm, input.heightMm)
  const imageLayout = input.widthMm > input.heightMm
    ? `left: 0; top: 0; width: ${input.widthMm}mm; height: ${input.heightMm}mm; transform-origin: top left; transform: translateX(${input.heightMm}mm) rotate(90deg);`
    : 'inset: 0; width: 100%; height: 100%;'
  const key = `${storagePrefix}${checkOnly ? 'check:' : ''}${input.idempotencyKey}`
  const hash = await fingerprint(input)
  const existingRaw = localStorage.getItem(key)
  if (existingRaw) {
    const existing = JSON.parse(existingRaw) as Dispatch
    if (existing.fingerprint !== hash) throw new Error('Этикетка этого задания изменилась. Повторная печать остановлена.')
    if (existing.state === 'operator-confirmed' || ((checkOnly || kiosk) && existing.state === 'browser-ended')) return
    if (checkOnly) throw new Error('Пробное задание уже передано браузеру. Проверьте очередь принтера.')
    // Only recovery of an uncertain previous dispatch asks the operator.
    // Confirmation continues packing without sending another printer job.
    if (window.confirm('Проверьте принтер. Этикетка этого товара уже напечатана? ОК — продолжить упаковку без повторной печати; Отмена — ничего не менять.')) {
      localStorage.setItem(key, JSON.stringify({ fingerprint: hash, state: 'operator-confirmed' } satisfies Dispatch))
      return
    }
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
          if (settled) {
            frame.remove()
            restoreFocus()
            return
          }
          try {
            localStorage.setItem(key, JSON.stringify({ fingerprint: hash, state: 'browser-ended' } satisfies Dispatch))
            frame.remove()
            restoreFocus()
            settle(checkOnly || kiosk ? undefined : new Error('Браузер закрыл окно печати, но не подтверждает выход этикетки. Заказ не упакован. Проверьте принтер; повторный скан этого товара позволит подтвердить уже напечатанную этикетку без перепечати.'))
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
      img { position: fixed; display: block; box-sizing: border-box; margin: 0; padding: 0; object-fit: contain; ${imageLayout} }
      </style></head><body><img src="${input.imageDataUrl}" alt=""></body></html>`
    document.body.appendChild(frame)
  })
}

function enqueue(input: PreparedQrInput, checkOnly: boolean, kiosk = false): Promise<void> {
  const run = () => navigator.locks
    ? navigator.locks.request('wms-qr-print', () => dispatch(input, checkOnly, kiosk))
    : dispatch(input, checkOnly, kiosk)
  const result = queue.then(run, run)
  queue = result.catch(() => undefined)
  return result
}

/** Packing may continue only after explicit reconciliation of the physical label.
 * afterprint also fires on Cancel and must never be used as a print receipt. */
export function printPreparedQr(input: PreparedQrInput): Promise<void> {
  return enqueue(input, false)
}

/** Isolated printer check only: resolves when Chrome's print flow ends (including
 * Cancel). This is NOT a receipt and must never authorize packing an order. */
export function dispatchPreparedQrForCheck(input: PreparedQrInput): Promise<void> {
  return enqueue(input, true)
}

/** Workstation contract: Chrome is launched with --kiosk-printing (or the
 * equivalent managed policy). Resolve on browser dispatch completion, NOT a
 * physical receipt. Ordinary Chrome's Cancel is indistinguishable and is not
 * supported as a success signal for this workstation workflow. */
export function dispatchPreparedQrInKiosk(input: PreparedQrInput): Promise<void> {
  return enqueue(input, false, true)
}
