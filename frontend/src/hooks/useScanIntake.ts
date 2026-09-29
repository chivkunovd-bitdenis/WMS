import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useBarcodeScanner, type BarcodeScannerOptions } from './useBarcodeScanner'

// WMS-575: приём скана вкладкой целиком, а не одним полем.
//
// Подбор и «Упаковка и маркировка» FBS теряли сканы: код ловило только поле
// скана и только пока в нём стоял курсор. Любой клик — по стрелке строки, по
// вкладке, по кнопке — и «клавиатурный» сканер печатал код в эту кнопку, а
// Enter нажимал её. Здесь код ловит существующий слушатель документа
// useBarcodeScanner, где бы ни стоял фокус, а коды, пришедшие подряд, ждут
// своей очереди и обрабатываются по одному в порядке прихода.
//
// Хук один на экран: подбор, карточка поставки и окно групповой сборки
// (WMS-574) вызывают его со своим обработчиком. Что делать с кодом, знает
// обработчик; хук только принимает код, не теряет его и говорит, слушает ли
// экран прямо сейчас.

export type ScanIntakeOptions = {
  /**
   * Экран готов принимать сканы: вкладка открыта, работа не закрыта. Окна
   * поверх экрана хук учитывает сам (см. bindRoot).
   */
  enabled: boolean
  /**
   * Обработчик одного кода. Вернул промис — следующий код ждёт его и
   * передаётся уже после перерисовки, то есть обработчик видит состояние,
   * которое оставил предыдущий скан. Звук и отметку обработчик даёт сам в тот
   * момент, когда результат появился на экране.
   */
  onScan: (code: string) => unknown
  /**
   * Зовётся сразу, как только код принят, — ещё до очереди. Нужен, чтобы
   * убрать следы скана там, где стоял курсор, пока они никуда не ушли.
   */
  onReceived?: (code: string) => void
  isScanOnlyField?: BarcodeScannerOptions['isScanOnlyField']
  scanOnlyFieldMinLength?: number
  /** Отдавать обработчику сырую пачку клавиатуры (см. useBarcodeScanner). Дефолт false. */
  emitRaw?: boolean
}

export type ScanIntake = {
  /**
   * Корневой узел экрана. По нему видно, не открыто ли поверх окно: MUI при
   * открытии окна помечает всё остальное на странице aria-hidden, и пока окно
   * открыто, экран сканы не принимает — работает окно (если у него свой
   * сканер), как у всех экранов со сканером.
   */
  bindRoot: (node: HTMLElement | null) => void
  /** Экран слушает прямо сейчас: включён и поверх него нет окна. Для плашки. */
  listening: boolean
  /** Отдать код в ту же очередь — например, введённый руками в поле скана. */
  submit: (code: string) => void
}

/** Прямой ребёнок body, внутри которого стоит узел: окно карточки или корень приложения. */
function topLevelElement(node: HTMLElement): HTMLElement | null {
  const body = node.ownerDocument.body
  let current: HTMLElement = node
  while (current.parentElement && current.parentElement !== body) current = current.parentElement
  return current.parentElement === body ? current : null
}

/** Поверх узла открыто окно: MUI скрыл его ветку от программы чтения на время окна. */
export function scanTargetCovered(node: HTMLElement | null): boolean {
  if (!node) return false
  return topLevelElement(node)?.getAttribute('aria-hidden') === 'true'
}

export function useScanIntake({
  enabled,
  onScan,
  onReceived,
  isScanOnlyField,
  scanOnlyFieldMinLength,
  emitRaw = false,
}: ScanIntakeOptions): ScanIntake {
  const [node, setNode] = useState<HTMLElement | null>(null)
  const bindRoot = useCallback((next: HTMLElement | null) => setNode(next), [])

  const subscribe = useCallback(
    (notify: () => void) => {
      const top = node ? topLevelElement(node) : null
      if (!top) return () => undefined
      const observer = new MutationObserver(notify)
      observer.observe(top, { attributes: true, attributeFilter: ['aria-hidden'] })
      return () => observer.disconnect()
    },
    [node],
  )
  const covered = useSyncExternalStore(
    subscribe,
    () => scanTargetCovered(node),
    () => false,
  )
  const listening = enabled && !covered

  // Последний обработчик экрана. Обновляется до эффектов этого же рендера,
  // поэтому очередь всегда зовёт обработчик со свежим состоянием.
  const onScanRef = useRef(onScan)
  const onReceivedRef = useRef(onReceived)
  useLayoutEffect(() => {
    onScanRef.current = onScan
    onReceivedRef.current = onReceived
  })

  const queueRef = useRef<string[]>([])
  const runningRef = useRef(false)
  const [queueTick, setQueueTick] = useState(0)

  const submit = useCallback((code: string) => {
    try {
      onReceivedRef.current?.(code)
    } catch {
      // Уборка следов — не повод потерять сам код.
    }
    queueRef.current.push(code)
    setQueueTick((tick) => tick + 1)
  }, [])

  // Один код за раз. Следующий уходит только после того, как предыдущий
  // обработан и экран перерисован: иначе второй код прочитал бы состояние до
  // первого (например, ЧЗ ушёл бы как поиск стикера, а не как код заказа).
  useEffect(() => {
    if (runningRef.current) return
    const code = queueRef.current.shift()
    if (code === undefined) return
    runningRef.current = true
    let pending: unknown
    try {
      pending = onScanRef.current(code)
    } catch {
      // Обработчик сам показывает свои ошибки; очередь не должна вставать.
      pending = undefined
    }
    void Promise.resolve(pending)
      .catch(() => undefined)
      .then(() => {
        runningRef.current = false
        setQueueTick((tick) => tick + 1)
      })
  }, [queueTick])

  useBarcodeScanner({
    enabled: listening,
    onScan: submit,
    isScanOnlyField,
    scanOnlyFieldMinLength,
    emitRaw,
  })

  return { bindRoot, listening, submit }
}
