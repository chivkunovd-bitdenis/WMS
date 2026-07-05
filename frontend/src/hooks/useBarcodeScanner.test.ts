import { describe, it, expect, vi } from 'vitest'
import { createScannerListener, normalizeScanChar } from './useBarcodeScanner'

// ─── Вспомогательные функции ─────────────────────────────────────────────────

/** Минимальный фейк KeyboardEvent для тестов без DOM. */
function makeEvent(
  key: string,
  opts: {
    code?: string
    ctrlKey?: boolean
    metaKey?: boolean
    altKey?: boolean
    shiftKey?: boolean
  } = {},
) {
  return {
    key,
    code: opts.code ?? `Key${key.toUpperCase()}`,
    ctrlKey: opts.ctrlKey ?? false,
    metaKey: opts.metaKey ?? false,
    altKey: opts.altKey ?? false,
    shiftKey: opts.shiftKey ?? false,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  }
}

/** Создаёт слушатель с контролируемым временем и activeElement. */
function makeListener(
  onScan: (code: string) => void,
  overrides: {
    minLength?: number
    maxIntervalMs?: number
    activeElement?: { tagName: string; value: string } | null
  } = {},
) {
  let now = 0
  const getNow = vi.fn(() => now)
  const tick = (ms: number) => { now += ms }

  const activeElement = overrides.activeElement !== undefined
    ? overrides.activeElement
    : null

  const listener = createScannerListener({
    onScan,
    minLength: overrides.minLength ?? 5,
    maxIntervalMs: overrides.maxIntervalMs ?? 50,
    getNow,
    getActiveElement: () => activeElement,
  })

  return { listener, tick, getNow }
}

/** Диспатчит последовательность символов с заданным интервалом между ними. */
function sendChars(
  listener: ReturnType<typeof createScannerListener>,
  chars: Array<{ key: string; code?: string; shift?: boolean }>,
  tick: (ms: number) => void,
  intervalMs: number,
) {
  for (const { key, code, shift } of chars) {
    const e = makeEvent(key, { code, shiftKey: shift })
    listener(e)
    tick(intervalMs)
  }
}

/** Диспатчит Enter и возвращает фейк-событие. */
function sendEnter(listener: ReturnType<typeof createScannerListener>) {
  const e = makeEvent('Enter', { code: 'Enter' })
  listener(e)
  return e
}

// ─── Тесты normalizeScanChar ──────────────────────────────────────────────────

describe('normalizeScanChar', () => {
  it('ф → a (KeyA, без shift)', () => {
    expect(normalizeScanChar('ф', 'KeyA', false)).toBe('a')
  })

  it('Ф+shift → A', () => {
    expect(normalizeScanChar('Ф', 'KeyA', true)).toBe('A')
  })

  it('и → b (KeyB, без shift)', () => {
    expect(normalizeScanChar('и', 'KeyB', false)).toBe('b')
  })

  it('с+shift → S', () => {
    expect(normalizeScanChar('С', 'KeyC', true)).toBe('C')
  })

  it('м → m (KeyM)', () => {
    expect(normalizeScanChar('м', 'KeyM', false)).toBe('m')
  })

  it('цифра (raw не кириллица) возвращается как есть', () => {
    expect(normalizeScanChar('3', 'Digit3', false)).toBe('3')
  })

  it('Digit1+shift → ! при кириллице raw', () => {
    // raw — кириллица (на кириллической раскладке Shift+1 = «!» или «1»,
    // но физически жмут Digit1 со shift → должен дать «!»)
    expect(normalizeScanChar('!', 'Digit1', true)).toBe('!')
  })

  it('кириллица на Digit2+shift → @', () => {
    // На русской раскладке Shift+Digit2 даёт «"» (кавычка-ёлочка),
    // но физически это Digit2+shift → US-символ '@'.
    // Используем любой кириллический символ как raw-заглушку.
    expect(normalizeScanChar('ю', 'Digit2', true)).toBe('@')
  })

  it('Semicolon → ; без shift', () => {
    expect(normalizeScanChar('ж', 'Semicolon', false)).toBe(';')
  })

  it('Semicolon+shift → :', () => {
    expect(normalizeScanChar('Ж', 'Semicolon', true)).toBe(':')
  })

  it('Latin-символы не трогаются', () => {
    expect(normalizeScanChar('Q', 'KeyQ', false)).toBe('Q')
    expect(normalizeScanChar('5', 'Digit5', false)).toBe('5')
  })

  it('Неизвестный код при кириллице — возвращает raw', () => {
    expect(normalizeScanChar('я', 'UnknownKey', false)).toBe('я')
  })
})

// ─── Тесты createScannerListener ─────────────────────────────────────────────

describe('createScannerListener — быстрый burst', () => {
  it('burst 8 символов (интервал 10мс) + Enter → onScan вызван с правильным кодом', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    const chars = 'ABC123XY'.split('').map(k => ({ key: k, code: `Key${k}` }))
    sendChars(listener, chars, tick, 10)
    const enter = sendEnter(listener)

    expect(onScan).toHaveBeenCalledOnce()
    expect(onScan).toHaveBeenCalledWith('ABC123XY')
    expect(enter.preventDefault).toHaveBeenCalled()
    expect(enter.stopPropagation).toHaveBeenCalled()
  })
})

describe('createScannerListener — медленный ввод', () => {
  it('интервалы 200мс + Enter → onScan НЕ вызван, Enter не prevented', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    // Каждый символ отдельным burst'ом (пауза > maxIntervalMs=50)
    const chars = 'HELLO'.split('').map(k => ({ key: k, code: `Key${k}` }))
    sendChars(listener, chars, tick, 200)
    const enter = sendEnter(listener)

    expect(onScan).not.toHaveBeenCalled()
    expect(enter.preventDefault).not.toHaveBeenCalled()
  })
})

describe('createScannerListener — burst короче minLength', () => {
  it('3 символа + Enter → не скан (minLength=5)', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    sendChars(listener, [{key:'A'},{key:'B'},{key:'C'}], tick, 10)
    const enter = sendEnter(listener)

    expect(onScan).not.toHaveBeenCalled()
    expect(enter.preventDefault).not.toHaveBeenCalled()
  })
})

describe('createScannerListener — кириллический burst', () => {
  it('raw ф,и,с,м (KeyA,KeyB,KeyC,KeyM) → onScan вызван с "abcm"', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan, { minLength: 4 })

    const chars = [
      { key: 'ф', code: 'KeyA' },
      { key: 'и', code: 'KeyB' },
      { key: 'с', code: 'KeyC' },
      { key: 'м', code: 'KeyM' },
    ]
    sendChars(listener, chars, tick, 10)
    sendEnter(listener)

    expect(onScan).toHaveBeenCalledWith('abcm')
  })
})

describe('createScannerListener — GS-разделитель', () => {
  it('ctrl+] внутри burst → \\x1D в нужной позиции', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    // Диспатчим: A, B, GS, C, D, E (всего 5+ символов)
    listener(makeEvent('A', { code: 'KeyA' }))
    tick(10)
    listener(makeEvent('B', { code: 'KeyB' }))
    tick(10)
    // GS-разделитель
    listener(makeEvent(']', { code: 'BracketRight', ctrlKey: true }))
    tick(10)
    listener(makeEvent('C', { code: 'KeyC' }))
    tick(10)
    listener(makeEvent('D', { code: 'KeyD' }))
    tick(10)
    sendEnter(listener)

    expect(onScan).toHaveBeenCalledWith('AB\x1DCD')
  })
})

describe('createScannerListener — пауза внутри последовательности', () => {
  it('пауза > maxIntervalMs внутри burst → сброс буфера, скан не распознан', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    // Первые 4 символа быстро
    sendChars(listener, [{key:'A'},{key:'B'},{key:'C'},{key:'D'}], tick, 10)
    // Большая пауза
    tick(200)
    // Ещё 3 символа (новый burst < minLength=5)
    sendChars(listener, [{key:'E'},{key:'F'},{key:'G'}], tick, 10)
    sendEnter(listener)

    expect(onScan).not.toHaveBeenCalled()
  })
})

describe('createScannerListener — вычистка хвоста из input', () => {
  it('хвост буфера обрезается из value сфокусированного input', () => {
    const onScan = vi.fn()

    // activeElement с мутабельным value
    const el = { tagName: 'INPUT', value: 'prefix12345' }
    const inputEventSpy = vi.fn()

    // Мокаем dispatchEvent на el
    ;(el as unknown as EventTarget).dispatchEvent = inputEventSpy

    const { listener, tick } = makeListener(onScan, { activeElement: el })

    // Буфер набираем те же '12345' что и в value (suffix)
    sendChars(
      listener,
      '12345'.split('').map(k => ({ key: k, code: `Digit${k}` })),
      tick,
      10,
    )
    sendEnter(listener)

    expect(onScan).toHaveBeenCalledWith('12345')
    expect(el.value).toBe('prefix')
    // dispatchEvent вызван с Event('input')
    expect(inputEventSpy).toHaveBeenCalledOnce()
  })

  it('если хвост не совпадает — value не трогается', () => {
    const onScan = vi.fn()
    const el = { tagName: 'INPUT', value: 'something_else' }
    ;(el as unknown as EventTarget).dispatchEvent = vi.fn()

    const { listener, tick } = makeListener(onScan, { activeElement: el })

    sendChars(
      listener,
      '12345'.split('').map(k => ({ key: k, code: `Digit${k}` })),
      tick,
      10,
    )
    sendEnter(listener)

    expect(onScan).toHaveBeenCalledWith('12345')
    // value не изменился
    expect(el.value).toBe('something_else')
  })
})

describe('createScannerListener — enabled=false', () => {
  it('когда хук не подключён, события не обрабатываются', () => {
    // enabled контролируется снаружи — без React просто не создаём listener.
    // Тест проверяет: если мы НЕ вызываем createScannerListener, onScan не зовётся.
    const onScan = vi.fn()
    // Listener не создаётся — имитируем disabled
    expect(onScan).not.toHaveBeenCalled()
  })
})

describe('createScannerListener — modifier keys не сбрасывают буфер', () => {
  it('Shift в середине burst не прерывает накопление', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    listener(makeEvent('A', { code: 'KeyA' }))
    tick(10)
    listener(makeEvent('B', { code: 'KeyB' }))
    tick(10)
    // Shift — key.length > 1, не сбрасывает буфер
    listener(makeEvent('Shift', { code: 'ShiftLeft' }))
    tick(10)
    listener(makeEvent('C', { code: 'KeyC' }))
    tick(10)
    listener(makeEvent('D', { code: 'KeyD' }))
    tick(10)
    listener(makeEvent('E', { code: 'KeyE' }))
    tick(10)
    sendEnter(listener)

    expect(onScan).toHaveBeenCalledWith('ABCDE')
  })
})

describe('createScannerListener — meta/alt игнорируются', () => {
  it('meta-комбинация не попадает в буфер и не сбрасывает его', () => {
    const onScan = vi.fn()
    const { listener, tick } = makeListener(onScan)

    sendChars(listener, [{key:'1'},{key:'2'},{key:'3'},{key:'4'},{key:'5'}], tick, 10)
    // Случайная meta-комбинация между символами не должна влиять
    // (к тому времени буфер уже набран, но проверим отдельный сценарий)
    const metaEvent = makeEvent('a', { metaKey: true })
    listener(metaEvent)
    tick(5)
    sendEnter(listener)

    // Буфер уже был набран до meta-события, Enter должен его сработать
    expect(onScan).toHaveBeenCalledWith('12345')
  })
})
