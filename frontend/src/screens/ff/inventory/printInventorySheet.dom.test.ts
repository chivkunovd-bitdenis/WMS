// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { printInventorySheet } from './printInventorySheet'
import type { ApiPrintSheet } from './inventoryCountApi'

// WMS-497, ревью Astra №1–№3: одна попытка печати — явный конечный автомат
// loading → scheduled → printed | failed (см. комментарий у самой функции
// в printInventorySheet.ts). Этот файл проверяет таблицу исходов автомата
// напрямую на функции; сценарий на уровне экрана (кнопка, повторный запрос
// к серверу) — в FfInventoryPage.printGuard.dom.test.tsx.
//
// Тайминги ниже используют ограничение ожидания загрузки (сейчас 20000 мс —
// см. обоснование и реальный замер в комментарии у LOAD_TIMEOUT_MS) и паузу
// перед печатью (100 мс, PRINT_DELAY_MS). Значения продублированы здесь как
// литералы: это тест поведения по контракту функции, а не импорт внутренних
// констант, которые модуль намеренно не экспортирует.
const LOAD_TIMEOUT_MS = 20000
const PRINT_DELAY_MS = 100

function sheet(): ApiPrintSheet {
  return {
    number: 'ИНВ-1111',
    created_at: '2026-09-27T10:00:00+00:00',
    created_by: 'Тест',
    filters: { object: true, warehouse_name: null, seller_name: null, category: null, product_articles: [] },
    rows: [],
  }
}

/** Подменяет print/focus на iframe и глушит фоновый шум jsdom (window.focus). */
function stubFrameWindow(iframe: HTMLIFrameElement) {
  const frameWindow = iframe.contentWindow as Window
  const printSpy = vi.spyOn(frameWindow, 'print').mockImplementation(() => {})
  vi.spyOn(frameWindow, 'focus').mockImplementation(() => {})
  return printSpy
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('printInventorySheet: успешная печать и её тайминг (F1)', () => {
  it('висит до iframe.onload и 100-миллисекундного таймера; print() вызывается один раз', async () => {
    let settled = false
    const promise = printInventorySheet(sheet())
    void promise.then(() => {
      settled = true
    })

    // Синхронный возврат уже случился (иначе этот код не выполнился бы), но
    // сама попытка печати ещё не состоялась — до вызова iframe.onload.
    await Promise.resolve()
    await Promise.resolve()
    expect(settled).toBe(false)

    const iframe = document.body.querySelector('iframe')
    expect(iframe).toBeTruthy()
    const printSpy = stubFrameWindow(iframe!)

    // jsdom не грузит содержимое srcdoc-iframe сам (проверено отдельно) —
    // вызываем обработчик так же, как это сделал бы браузер.
    ;(iframe as unknown as { onload: () => void }).onload()

    // До истечения таймера — print() ещё не вызван, промис не разрешён.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(printSpy).not.toHaveBeenCalled()
    expect(settled).toBe(false)

    await new Promise((resolve) => setTimeout(resolve, PRINT_DELAY_MS + 20))
    expect(printSpy).toHaveBeenCalledTimes(1)
    expect(settled).toBe(true)
  })

  it('печать недоступна (contentWindow отсутствует) — промис всё равно разрешается, а не висит вечно', async () => {
    const promise = printInventorySheet(sheet())
    const iframe = document.body.querySelector('iframe')
    expect(iframe).toBeTruthy()
    // Имитируем окружение, где iframe не выдаёт contentWindow.
    Object.defineProperty(iframe, 'contentWindow', { value: null, configurable: true })

    ;(iframe as unknown as { onload: () => void }).onload()
    await expect(promise).resolves.toBeUndefined()
  })

  it('повторная печать после завершения — новый вызов работает независимо и тоже печатает один раз', async () => {
    // Первая попытка — от начала до конца.
    const first = printInventorySheet(sheet())
    const firstIframe = document.body.querySelector('iframe')!
    const firstPrintSpy = stubFrameWindow(firstIframe)
    ;(firstIframe as unknown as { onload: () => void }).onload()
    await new Promise((resolve) => setTimeout(resolve, PRINT_DELAY_MS + 20))
    await first
    expect(firstPrintSpy).toHaveBeenCalledTimes(1)

    // Вторая, отдельная попытка — свой iframe, свой автомат состояний. Первый
    // iframe печатью не убирается (это делает `afterprint`, которого jsdom
    // не шлёт) — он остаётся в DOM, поэтому ищем именно НОВЫЙ элемент.
    const second = printInventorySheet(sheet())
    const iframesAfterSecondCall = Array.from(document.body.querySelectorAll('iframe'))
    expect(iframesAfterSecondCall).toHaveLength(2)
    const secondIframe = iframesAfterSecondCall.find((el) => el !== firstIframe)!
    expect(secondIframe).toBeTruthy()
    const secondPrintSpy = stubFrameWindow(secondIframe)
    ;(secondIframe as unknown as { onload: () => void }).onload()
    await new Promise((resolve) => setTimeout(resolve, PRINT_DELAY_MS + 20))
    await second
    expect(secondPrintSpy).toHaveBeenCalledTimes(1)
    // Первая попытка не печатала повторно из-за второй.
    expect(firstPrintSpy).toHaveBeenCalledTimes(1)
  })
})

describe('printInventorySheet: F3 — повторный onload не ставит второй таймер печати', () => {
  it('два события onload подряд (до таймера печати) — print() вызывается ровно один раз', async () => {
    const promise = printInventorySheet(sheet())
    const iframe = document.body.querySelector('iframe')!
    const printSpy = stubFrameWindow(iframe)

    const onload = (iframe as unknown as { onload: () => void }).onload
    onload()
    onload() // повторный onload того же iframe — до истечения PRINT_DELAY_MS

    await new Promise((resolve) => setTimeout(resolve, PRINT_DELAY_MS + 20))
    expect(printSpy).toHaveBeenCalledTimes(1)
    await expect(promise).resolves.toBeUndefined()
  })
})

describe('printInventorySheet: F2 — отказ после onload отменяет уже поставленную печать', () => {
  it('onload, затем error до истечения таймера печати — print() не вызывается вообще', async () => {
    let settled = false
    const promise = printInventorySheet(sheet())
    void promise.then(() => {
      settled = true
    })
    const iframe = document.body.querySelector('iframe')!
    const printSpy = stubFrameWindow(iframe)

    ;(iframe as unknown as { onload: () => void }).onload()
    // Отказ приходит ПОСЛЕ onload (таймер печати уже поставлен), но раньше
    // его срабатывания.
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(settled).toBe(false)
    ;(iframe as unknown as { onerror: () => void }).onerror()
    // resolve() внутри fail() — синхронный вызов, но .then() коллбэк всегда
    // приходит следующим микротаском, а не сразу.
    await Promise.resolve()
    expect(settled).toBe(true)
    expect(document.body.contains(iframe)).toBe(false)

    // Ждём дольше, чем был бы таймер печати, — print() всё равно не случился.
    await new Promise((resolve) => setTimeout(resolve, PRINT_DELAY_MS + 50))
    expect(printSpy).not.toHaveBeenCalled()
    await expect(promise).resolves.toBeUndefined()
  })

  it('явный error без предшествующего onload тоже освобождает попытку', async () => {
    let settled = false
    const promise = printInventorySheet(sheet())
    void promise.then(() => {
      settled = true
    })
    const iframe = document.body.querySelector('iframe')!

    ;(iframe as unknown as { onerror: () => void }).onerror()
    await Promise.resolve()
    expect(settled).toBe(true)
    expect(document.body.contains(iframe)).toBe(false)
  })
})

describe('printInventorySheet: обрыв загрузки (ни onload, ни error) не вешает попытку навсегда', () => {
  it('ограничение ожидания истекает — промис разрешается, iframe убирается, оба обработчика сняты', async () => {
    vi.useFakeTimers()
    let settled = false
    const promise = printInventorySheet(sheet())
    void promise.then(() => {
      settled = true
    })

    const iframe = document.body.querySelector('iframe')
    expect(iframe).toBeTruthy()

    // Задолго до предела — попытка ещё «готовится», iframe на месте.
    await vi.advanceTimersByTimeAsync(LOAD_TIMEOUT_MS - 1000)
    expect(settled).toBe(false)
    expect(document.body.contains(iframe)).toBe(true)

    // Предел истёк — попытка брошена.
    await vi.advanceTimersByTimeAsync(1500)
    expect(settled).toBe(true)
    expect(document.body.contains(iframe)).toBe(false)
    expect((iframe as unknown as { onload: unknown }).onload).toBeNull()
    expect((iframe as unknown as { onerror: unknown }).onerror).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('поздний onload брошенной попытки не печатает (state уже не loading)', async () => {
    vi.useFakeTimers()
    const promise = printInventorySheet(sheet())
    const iframe = document.body.querySelector('iframe')!
    const frameWindow = iframe.contentWindow as Window
    const printSpy = vi.spyOn(frameWindow, 'print').mockImplementation(() => {})

    await vi.advanceTimersByTimeAsync(LOAD_TIMEOUT_MS)
    await promise

    // «Поздний» onload: пробуем вызвать то, что было обработчиком, — его уже нет.
    const stillOnload = (iframe as unknown as { onload: (() => void) | null }).onload
    expect(stillOnload).toBeNull()
    // На случай, если бы браузер всё же прислал реальное DOM-событие load —
    // без зарегистрированного обработчика оно тоже ничего не вызовет.
    iframe.dispatchEvent(new Event('load'))
    await vi.advanceTimersByTimeAsync(PRINT_DELAY_MS + 100)
    expect(printSpy).not.toHaveBeenCalled()
  })
})

describe('printInventorySheet: ограничение ожидания на реальном листе 1200 строк', () => {
  it('загрузка на 4999 мс (в пределах лимита) — печатает один раз; загрузка на 20100 мс (за пределом) — не печатает', async () => {
    // Настоящий лист такого размера строится в printInventorySheet.test.ts
    // (buildInventorySheetHtml) и реально замерен в headless Chromium
    // (162–232 мс, см. комментарий у LOAD_TIMEOUT_MS) — здесь важна только
    // сама граница алгоритма по виртуальному времени, не построение HTML.
    vi.useFakeTimers()

    // В пределах — печать состоится.
    const within = printInventorySheet(sheet())
    const withinIframe = document.body.querySelector('iframe')!
    const withinPrintSpy = vi.spyOn(withinIframe.contentWindow as Window, 'print').mockImplementation(() => {})
    vi.spyOn(withinIframe.contentWindow as Window, 'focus').mockImplementation(() => {})
    await vi.advanceTimersByTimeAsync(4999)
    ;(withinIframe as unknown as { onload: () => void }).onload()
    await vi.advanceTimersByTimeAsync(PRINT_DELAY_MS + 20)
    await within
    expect(withinPrintSpy).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)

    document.body.innerHTML = ''

    // За пределом — ограничение уже отменило попытку, onload опоздал.
    const beyond = printInventorySheet(sheet())
    const beyondIframe = document.body.querySelector('iframe')!
    const beyondPrintSpy = vi.spyOn(beyondIframe.contentWindow as Window, 'print').mockImplementation(() => {})
    await vi.advanceTimersByTimeAsync(LOAD_TIMEOUT_MS + 100)
    ;(beyondIframe as unknown as { onload: (() => void) | null }).onload?.()
    await vi.advanceTimersByTimeAsync(PRINT_DELAY_MS + 20)
    await beyond
    expect(beyondPrintSpy).not.toHaveBeenCalled()
  })
})
