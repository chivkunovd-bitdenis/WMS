// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { printInventorySheet } from './printInventorySheet'
import type { ApiPrintSheet } from './inventoryCountApi'

// WMS-497, ревью Astra №1 (F1): printInventorySheet должна отдавать сигнал
// о том, что попытка печати действительно СОСТОЯЛАСЬ (frameWindow.print()
// вызван, каким бы ни был исход), а не сразу после синхронного возврата —
// та часть работы (загрузка iframe, 100-миллисекундный таймер) идёт позже.
// Раньше страница снимала защиту от повторного нажатия сразу после этого
// синхронного возврата, то есть до print(); сценарий на уровне экрана —
// в FfInventoryPage.printGuard.dom.test.tsx.

function sheet(): ApiPrintSheet {
  return {
    number: 'ИНВ-1111',
    created_at: '2026-09-27T10:00:00+00:00',
    created_by: 'Тест',
    filters: { object: true, warehouse_name: null, seller_name: null, category: null, product_articles: [] },
    rows: [],
  }
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('printInventorySheet: промис завершается не раньше фактической попытки печати', () => {
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
    const frameWindow = iframe!.contentWindow
    expect(frameWindow).toBeTruthy()
    const printSpy = vi.spyOn(frameWindow as Window, 'print').mockImplementation(() => {})
    // jsdom не реализует window.focus и шумит в stderr при вызове — печати это
    // не мешает (код и так ловит исключение), но глушим ради чистого лога теста.
    vi.spyOn(frameWindow as Window, 'focus').mockImplementation(() => {})

    // jsdom не грузит содержимое srcdoc-iframe сам (проверено отдельно) —
    // вызываем обработчик так же, как это сделал бы браузер.
    ;(iframe as unknown as { onload: () => void }).onload()

    // До истечения таймера — print() ещё не вызван, промис не разрешён.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(printSpy).not.toHaveBeenCalled()
    expect(settled).toBe(false)

    await new Promise((resolve) => setTimeout(resolve, 120))
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
})
