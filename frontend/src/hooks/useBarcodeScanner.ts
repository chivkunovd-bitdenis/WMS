import { useEffect, useRef } from 'react'

// ─── Типы ────────────────────────────────────────────────────────────────────

export type BarcodeScannerOptions = {
  /** Обработчик распознанного скана. */
  onScan: (code: string) => void
  /** Слушать ли сейчас (например, открыта ли панель). Дефолт true. */
  enabled?: boolean
  /** Минимальная длина кода, чтобы считать burst сканом. Дефолт 5. */
  minLength?: number
  /** Макс. межсимвольный интервал сканера, мс. Дефолт 50. */
  maxIntervalMs?: number
  /**
   * WMS-566: поле, куда руками вводят только короткое число (например «В коробе»).
   * В нём темп не меряем: пачка от minLength символов с Enter — всегда скан.
   */
  isScanOnlyField?: (el: ActiveElementLike) => boolean
  /** Мин. длина скана в таком поле: короче — это ручное число. Дефолт minLength. */
  scanOnlyFieldMinLength?: number
  /**
   * WMS-575: отдать пачку так, как её напечатала клавиатура, — те же символы,
   * что легли бы в текстовое поле, плюс разделитель GS, — без перевода раскладки.
   * Нужно там, где раскладку чинит сервер своей полной таблицей (упаковка FBS:
   * normalize_scanned_cis и поиск стикера). Перевод здесь знает только буквы,
   * и знаки «/», «?», «&» русской раскладки остались бы искажёнными уже без
   * кириллицы, по которой сервер включает ремонт. Дефолт false — как было.
   */
  emitRaw?: boolean
  /** Recover US punctuation from physical keys in a RU scanner burst. */
  normalizeLayoutPunctuation?: boolean
}

// Внутреннее представление символа в буфере
type BufferChar = {
  raw: string
  code: string
  shift: boolean
  prevented?: boolean
}

// ─── Маппинг физических клавиш → латиница (US-раскладка) ────────────────────

// Только буквенные клавиши — цифры и символы обрабатываются отдельно
const CODE_TO_LATIN: Record<string, string> = {
  KeyA: 'a', KeyB: 'b', KeyC: 'c', KeyD: 'd', KeyE: 'e',
  KeyF: 'f', KeyG: 'g', KeyH: 'h', KeyI: 'i', KeyJ: 'j',
  KeyK: 'k', KeyL: 'l', KeyM: 'm', KeyN: 'n', KeyO: 'o',
  KeyP: 'p', KeyQ: 'q', KeyR: 'r', KeyS: 's', KeyT: 't',
  KeyU: 'u', KeyV: 'v', KeyW: 'w', KeyX: 'x', KeyY: 'y',
  KeyZ: 'z',
}

// Символьные клавиши: [без shift, с shift]
const CODE_TO_SYMBOL: Record<string, [string, string]> = {
  Digit1: ['1', '!'],
  Digit2: ['2', '@'],
  Digit3: ['3', '#'],
  Digit4: ['4', '$'],
  Digit5: ['5', '%'],
  Digit6: ['6', '^'],
  Digit7: ['7', '&'],
  Digit8: ['8', '*'],
  Digit9: ['9', '('],
  Digit0: ['0', ')'],
  Minus:        ['-', '_'],
  Equal:        ['=', '+'],
  BracketLeft:  ['[', '{'],
  BracketRight: [']', '}'],
  Semicolon:    [';', ':'],
  Quote:        ["'", '"'],
  Backquote:    ['`', '~'],
  Comma:        [',', '<'],
  Period:       ['.', '>'],
  Slash:        ['/', '?'],
}

const CYRILLIC_RE = /[а-яёА-ЯЁ]/

/**
 * Нормализует один символ сканера: если кириллица — переводит по физическому
 * коду клавиши в латиницу US-раскладки. Остальное возвращает как есть.
 *
 * @param raw   - символ с клавиатуры (e.key)
 * @param code  - физический код клавиши (e.code)
 * @param shift - был ли зажат Shift
 */
export function normalizeScanChar(raw: string, code: string, shift: boolean, russianLayout = false): string {
  if (!CYRILLIC_RE.test(raw) && !russianLayout) {
    // Раскладка уже латинская — берём как есть
    return raw
  }

  // Буква
  const base = CODE_TO_LATIN[code]
  if (base !== undefined) {
    return shift ? base.toUpperCase() : base
  }

  // Символьная клавиша
  const pair = CODE_TO_SYMBOL[code]
  if (pair !== undefined) {
    return pair[shift ? 1 : 0]
  }

  // Неизвестный код — отдаём raw без изменений
  return raw
}

// ─── Фабрика слушателя (без React, легко тестируется) ────────────────────────

type EventLike = {
  key: string
  code: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  shiftKey: boolean
  preventDefault(): void
  stopPropagation(): void
}

export type ActiveElementLike = {
  tagName?: string
  value?: string
  isContentEditable?: boolean
  dataset?: Record<string, string | undefined>
} | null

/** Место, куда человек может печатать руками. */
function isTextEntry(el: ActiveElementLike): boolean {
  if (el === null || el === undefined || typeof el.tagName !== 'string') return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true
}

type ScannerListenerOptions = {
  onScan: (code: string) => void
  minLength: number
  maxIntervalMs: number
  /** Инъекция времени — в реальном коде performance.now(), в тестах — mock. */
  getNow: () => number
  /** Инъекция activeElement — в реальном коде document.activeElement. */
  getActiveElement: () => ActiveElementLike
  isScanOnlyField?: (el: ActiveElementLike) => boolean
  scanOnlyFieldMinLength?: number
  emitRaw?: boolean
  /** Recover US punctuation from physical keys in a RU scanner burst. */
  normalizeLayoutPunctuation?: boolean
}

/**
 * Ставит value через нативный сеттер прототипа: React у контролируемых полей
 * сравнивает значение через внутренний value tracker, и прямое присваивание
 * el.value не породит onChange — «хвост» остался бы в React-состоянии.
 * Вне браузера (тесты без DOM) — обычное присваивание.
 */
function setNativeInputValue(el: { tagName?: string; value?: string }, next: string): void {
  const proto =
    typeof HTMLInputElement !== 'undefined' && el instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : typeof HTMLTextAreaElement !== 'undefined' && el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : null
  const setter = proto ? Object.getOwnPropertyDescriptor(proto, 'value')?.set : undefined
  if (setter) {
    setter.call(el, next)
  } else {
    ;(el as { value: string }).value = next
  }
}

/**
 * Создаёт обработчик keydown для keyboard-wedge сканера.
 * Возвращает функцию-handler, готовую к addEventListener.
 * Выделена отдельно, чтобы тестировать без React/DOM.
 */
export function createScannerListener(opts: ScannerListenerOptions) {
  let buffer: BufferChar[] = []
  let lastTime = -Infinity
  // Сколько раз внутри пачки интервал превысил maxIntervalMs.
  let slowGaps = 0

  // Пачку начинаем заново только после долгого затишья. Раньше буфер очищался
  // на ЛЮБОЙ заминке сканера, и на Enter уходил хвост: реальный `4630452635503`
  // приезжал на сервер как `0452635503`, товар не находился, работа вставала.
  const NEW_BURST_MS = 1000

  const resetBurst = (): void => {
    buffer = []
    slowGaps = 0
  }

  const handler = (e: EventLike): void => {
    // Meta/Alt-комбинации полностью игнорируем
    if (e.metaKey || e.altKey) return

    const now = opts.getNow()

    // GS-разделитель КМ Честного знака (Ctrl+])
    if (e.ctrlKey && (e.code === 'BracketRight' || e.key === ']')) {
      e.preventDefault()
      const gsGap = now - lastTime
      if (gsGap > NEW_BURST_MS) {
        resetBurst()
      } else if (gsGap > opts.maxIntervalMs) {
        slowGaps += 1
      }
      buffer.push({ raw: '\x1D', code: e.code, shift: false, prevented: true })
      lastTime = now
      return
    }

    // Прочие ctrl-комбинации — не трогаем
    if (e.ctrlKey) return

    // Enter и Tab — два ходовых суффикса «клавиатурных» сканеров. Какой из них
    // выставлен, зависит от настройки самого устройства, и полагаться только на
    // Enter нельзя: с Tab-суффиксом код молча уходил в никуда.
    if (e.key === 'Enter' || e.key === 'Tab') {
      const el = opts.getActiveElement()
      // Темп меряем только там, где печатает человек.
      //
      // В текстовом поле темп — единственное, чем скан отличается от ручного
      // ввода: человек тоже набирает символы и жмёт Enter, и отбирать у него
      // ввод нельзя. А вне текстового поля печатать попросту некуда: пачка
      // печатных символов, законченная Enter, приходит там только со сканера.
      // Мерить ей темп — значит выбросить законный скан за то, что у сканера
      // выставлена большая задержка между символами.
      //
      // Ровно на этом встала инвентаризация 02.09.2026: стоило фокусу уйти из
      // поля, код улетал в никуда, а оператор видел «пикнул — и ничего».
      const scanOnlyField = isTextEntry(el) && (opts.isScanOnlyField?.(el) ?? false)
      const typingHere = isTextEntry(el) && !scanOnlyField
      const minLength = scanOnlyField
        ? Math.max(opts.minLength, opts.scanOnlyFieldMinLength ?? opts.minLength)
        : opts.minLength
      // Сканер это или человек, решаем по всей пачке, а не по одной заминке:
      // у сканера почти все интервалы короткие, у ручного ввода — все длинные.
      const allowedSlowGaps = Math.max(1, Math.floor(buffer.length * 0.2))
      const looksLikeScan =
        buffer.length >= minLength && (!typingHere || slowGaps <= allowedSlowGaps)

      if (looksLikeScan) {
        e.preventDefault()
        e.stopPropagation()

        // Translate punctuation only for a recognized burst with RU letters.
        // Literal ASCII/manual input and raw packing codes keep their symbols.
        const russianLayout = opts.normalizeLayoutPunctuation && buffer.some(({ raw }) => CYRILLIC_RE.test(raw))
        const normalized = opts.emitRaw
          ? buffer.map(({ raw }) => raw).join('')
          : buffer
            .map(({ raw, code, shift }) => normalizeScanChar(raw, code, shift, Boolean(russianLayout)))
            .join('')

        // Вычищаем просочившиеся символы из сфокусированного поля
        if (
          el !== null &&
          el !== undefined &&
          typeof el.tagName === 'string' &&
          (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') &&
          typeof el.value === 'string'
        ) {
          // Ctrl+] was prevented: GS belongs to the payload, not the input value.
          const rawTail = buffer.filter(c => !c.prevented).map(c => c.raw).join('')
          if (rawTail.length > 0 && el.value.endsWith(rawTail)) {
            setNativeInputValue(el, el.value.slice(0, -rawTail.length))
            const inputEl = el as unknown as EventTarget
            inputEl.dispatchEvent(new Event('input', { bubbles: true }))
          }
        }

        opts.onScan(normalized)
        resetBurst()
        lastTime = -Infinity
        return
      }

      // Не скан: Enter не трогаем — сработает обычный сабмит поля с его
      // полным значением. Состояние обнуляем, чтобы остаток не приклеился
      // к следующей пачке.
      resetBurst()
      lastTime = -Infinity
      return
    }

    // Backspace/Delete сканер никогда не шлёт — это оператор правит руками уже
    // введённое число. Пачку сбрасываем, иначе цифры до и после правки склеятся
    // в буфере и уйдут на Enter как один «скан» (WMS-566 P3-2).
    if (e.key === 'Backspace' || e.key === 'Delete') {
      resetBurst()
      lastTime = -Infinity
      return
    }

    // Прочие модификаторные клавиши (Shift, Ctrl, Alt, CapsLock…) не записываем,
    // но и не сбрасываем буфер
    if (e.key.length > 1) return

    // Печатный символ: копим и считаем заминки, но пачку не рвём.
    const gap = now - lastTime
    if (gap > NEW_BURST_MS) {
      resetBurst()
    } else if (gap > opts.maxIntervalMs) {
      slowGaps += 1
    }

    buffer.push({ raw: e.key, code: e.code, shift: e.shiftKey })
    lastTime = now
  }

  return handler
}

// ─── React-хук ───────────────────────────────────────────────────────────────

export function useBarcodeScanner({
  onScan,
  enabled = true,
  minLength = 5,
  maxIntervalMs = 50,
  isScanOnlyField,
  scanOnlyFieldMinLength,
  emitRaw = false,
  normalizeLayoutPunctuation = false,
}: BarcodeScannerOptions): void {
  // Храним onScan в ref, чтобы не переподписываться на каждый рендер.
  // Обновляем ref внутри useEffect (не во время рендера) — совместимо с react-hooks/refs.
  const onScanRef = useRef(onScan)
  const isScanOnlyFieldRef = useRef(isScanOnlyField)

  useEffect(() => {
    onScanRef.current = onScan
    isScanOnlyFieldRef.current = isScanOnlyField
  })

  useEffect(() => {
    if (!enabled) return

    const handler = createScannerListener({
      onScan: (code) => onScanRef.current(code),
      minLength,
      maxIntervalMs,
      getNow: () => performance.now(),
      getActiveElement: () => document.activeElement as ActiveElementLike,
      isScanOnlyField: (el) => isScanOnlyFieldRef.current?.(el) ?? false,
      scanOnlyFieldMinLength,
      emitRaw,
      normalizeLayoutPunctuation,
    })

    // Capture-фаза: перехватываем до обработчиков полей
    document.addEventListener('keydown', handler as unknown as (e: Event) => void, true)
    return () => {
      document.removeEventListener('keydown', handler as unknown as (e: Event) => void, true)
    }
  }, [enabled, minLength, maxIntervalMs, scanOnlyFieldMinLength, emitRaw, normalizeLayoutPunctuation])
}
