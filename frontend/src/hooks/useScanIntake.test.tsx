// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { useScanIntake } from './useScanIntake'

// WMS-575: приём скана всей вкладкой. Проверяется настоящий хук в настоящем
// рендере: клавиши идут событиями keydown в документ, как от «клавиатурного»
// сканера, а не вызовом обработчика напрямую.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
})

/** Сканер: символы подряд и Enter — в тот элемент, где сейчас фокус. */
function scan(code: string) {
  const target = document.activeElement ?? document.body
  const enter = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })
  act(() => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', { key, code: `Key${key.toUpperCase()}`, bubbles: true, cancelable: true }))
    }
    target.dispatchEvent(enter)
  })
  return enter
}

async function flush(ms = 0) {
  // Короткими шагами: act откладывает перерисовку до своего конца, а очередь
  // передаёт следующий код только после перерисовки.
  const steps = Math.max(1, Math.ceil(ms / 10))
  for (let step = 0; step < steps; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, Math.min(ms, 10)))
    })
  }
}

function Probe({ onScan, enabled = true }: { onScan: (code: string) => unknown; enabled?: boolean }) {
  const { bindRoot, listening } = useScanIntake({ enabled, onScan })
  return (
    <div ref={bindRoot} data-listening={listening ? 'true' : 'false'}>
      <button type="button" data-testid="some-button">Раскрыть</button>
    </div>
  )
}

describe('WMS-575 useScanIntake', () => {
  it('R1: принимает скан при фокусе на кнопке и гасит Enter, чтобы кнопка не нажалась', async () => {
    const seen: string[] = []
    await act(async () => root.render(<Probe onScan={(code) => { seen.push(code) }} />))
    const button = host.querySelector<HTMLButtonElement>('[data-testid="some-button"]')!
    let enterReachedButton = 0
    button.addEventListener('keydown', (event) => { if (event.key === 'Enter') enterReachedButton += 1 })
    act(() => button.focus())

    const enter = scan('4680123456789')
    await flush()

    expect(seen).toEqual(['4680123456789'])
    // Enter сканера не доходит до кнопки и не выполняет её действие.
    expect(enter.defaultPrevented).toBe(true)
    expect(enterReachedButton).toBe(0)
  })

  it('R3: пять кодов подряд обрабатываются по одному, в порядке прихода', async () => {
    const started: string[] = []
    const finished: string[] = []
    let inFlight = 0
    let maxInFlight = 0
    const onScan = async (code: string) => {
      started.push(code)
      inFlight += 1
      maxInFlight = Math.max(maxInFlight, inFlight)
      await new Promise((resolve) => setTimeout(resolve, 30))
      inFlight -= 1
      finished.push(code)
    }
    await act(async () => root.render(<Probe onScan={onScan} />))
    const codes = ['2000000000011', '2000000000028', '2000000000035', '2000000000042', '2000000000059']
    // Все пять приходят раньше, чем закончился первый.
    for (const code of codes) scan(code)
    await flush(400)

    expect(started).toEqual(codes)
    expect(finished).toEqual(codes)
    expect(maxInFlight).toBe(1)
  })

  it('Д3: пока поверх открыто окно, вкладка не слушает; окно закрыли — слушает без кликов', async () => {
    const seen: string[] = []
    await act(async () => root.render(<Probe onScan={(code) => { seen.push(code) }} />))
    const probe = host.querySelector<HTMLElement>('[data-listening]')!
    expect(probe.dataset.listening).toBe('true')

    // Так MUI помечает всё, что оказалось под открытым окном.
    await act(async () => { host.setAttribute('aria-hidden', 'true') })
    expect(probe.dataset.listening).toBe('false')
    scan('4680123456789')
    await flush()
    expect(seen).toEqual([])

    await act(async () => { host.removeAttribute('aria-hidden') })
    expect(probe.dataset.listening).toBe('true')
    scan('4680123456789')
    await flush()
    expect(seen).toEqual(['4680123456789'])
  })

  it('выключенный экран не слушает и Enter не трогает', async () => {
    const seen: string[] = []
    await act(async () => root.render(<Probe enabled={false} onScan={(code) => { seen.push(code) }} />))
    const enter = scan('4680123456789')
    await flush()
    expect(seen).toEqual([])
    expect(enter.defaultPrevented).toBe(false)
  })
})
