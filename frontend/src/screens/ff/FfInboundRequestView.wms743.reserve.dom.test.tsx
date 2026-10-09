// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Harness = typeof import('../../test-contracts/inbound684586Harness')

// WMS-743, review of PR 432. localStorage is REALLY full here (jsdom enforces its 5 000 000
// character quota), so every record of the label print attempt is refused. The press that follows
// a lost mark response or an unknown outcome must still recognise the earlier attempt: no second
// tape, with or without a reload of the page (a reload drops the page memory but keeps
// sessionStorage and localStorage).
const printer = vi.hoisted(() => ({
  replace: undefined as undefined | ((handoff: { beforeTransfer: (html: string) => void }) => Promise<void>),
  transfers: 0,
}))
vi.mock('../../utils/printBarcodeLabel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/printBarcodeLabel')>()
  return {
    ...actual,
    // The real utility prints unless a test replaces it to model an outcome the page cannot see.
    printBarcodeLabels: (...args: unknown[]) => {
      if (printer.replace) {
        printer.transfers += 1
        return printer.replace(args[1] as { beforeTransfer: (html: string) => void })
      }
      return (actual.printBarcodeLabels as (...all: unknown[]) => unknown)(...args)
    },
  }
})

const errorText = () => document.querySelector('[data-testid="ff-inbound-doc-error"]')?.textContent ?? ''
const reserveKeys = () => Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index)!)
  .filter((key) => key.startsWith('wms440:'))
/** The browser storage of an operator who already has about 5 MB of other data. */
function fillLocalStorage() {
  localStorage.setItem('wms.print.labelSizeId', '58x40')
  let used = 0
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index)!
    used += key.length + localStorage.getItem(key)!.length
  }
  localStorage.setItem('foreign', 'x'.repeat(5_000_000 - used - 'foreign'.length - 100))
  expect(() => localStorage.setItem('probe', 'y'.repeat(400)), 'localStorage really refuses new records').toThrow()
}

let h: ReturnType<Harness['harness']>
/** Loads the screen with an empty page memory, as a freshly opened tab does. */
async function openPage() {
  vi.resetModules()
  const fresh = await import('../../test-contracts/inbound684586Harness')
  h = fresh.harness()
  // The shared helper expects some print source to exist.
  window.__WMS_LAST_PRINT_HTML__ = '<html></html>'
}
/** A reload of the tab: the screen and the page memory are gone, both storages stay. */
async function reloadPage() {
  await h.dispose() // also clears localStorage, so the full storage is rebuilt below
  fillLocalStorage()
  await openPage()
}
beforeEach(async () => {
  printer.replace = undefined
  printer.transfers = 0
  sessionStorage.clear()
  await openPage()
})
afterEach(async () => {
  await h.dispose()
  sessionStorage.clear()
})

describe('WMS-743 a refused attempt record must not allow a second tape', () => {
  for (const reload of [false, true]) {
    it(`WMS-743 C14: full storage and a lost mark response: the repeat repairs the marks and sends no second tape${reload ? ' after a reload' : ''}`, async () => {
      fillLocalStorage()
      await h.render()
      h.markMode = 'http'
      await h.print(true)
      expect(errorText()).toContain('label mark failed')
      expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
      expect(h.markCalls).toHaveLength(1)
      if (reload) {
        await reloadPage()
        await h.render()
      }
      h.markMode = 'ok'
      await h.print(true)
      expect(window.__WMS_PRINT_JOB_COUNT__, 'no second tape').toBe(reload ? 0 : 1)
      expect(h.markCalls, 'the marks are repaired from the remembered attempt').toHaveLength(reload ? 3 : 4)
      expect(errorText()).toBe('')
    }, 60_000)

    it(`WMS-743 C15: full storage and an unknown outcome: the repeat asks the operator and sends no second tape${reload ? ' after a reload' : ''}`, async () => {
      fillLocalStorage()
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
      printer.replace = async (handoff) => {
        handoff.beforeTransfer('<html></html>')
        throw new Error('the page died while the browser was printing')
      }
      await h.render()
      await h.print(true)
      expect(errorText()).toContain('the page died')
      expect(printer.transfers).toBe(1)
      if (reload) {
        await reloadPage()
        vi.spyOn(window, 'confirm').mockReturnValue(false)
        await h.render()
      }
      await h.print(true)
      expect(errorText()).toContain('не отправлена повторно')
      expect(printer.transfers, 'no second tape without the operator').toBe(1)
      expect(h.markCalls).toHaveLength(0)
      if (!reload) expect(confirm).toHaveBeenCalledTimes(1)
    }, 60_000)
  }

  it('WMS-743 C16: after the operator answers, the next press is an explicit reprint and the reserve is cleared', async () => {
    fillLocalStorage()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    printer.replace = async (handoff) => {
      handoff.beforeTransfer('<html></html>')
      throw new Error('the page died while the browser was printing')
    }
    await h.render()
    await h.print(true)
    expect(printer.transfers).toBe(1)
    await h.print(true) // the operator confirms that the printer queue was checked
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(printer.transfers).toBe(1)
    printer.replace = async (handoff) => { handoff.beforeTransfer('<html></html>') }
    await h.print(true)
    expect(printer.transfers, 'the explicit reprint').toBe(2)
    expect(h.markCalls).toHaveLength(3)
    expect(errorText()).toBe('')
    expect(reserveKeys(), 'a finished attempt leaves no reserve behind').toEqual([])
  }, 60_000)

  it('WMS-743 C16: with a working localStorage nothing is kept in sessionStorage', async () => {
    await h.render()
    await h.print(true)
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(3)
    expect(reserveKeys()).toEqual([])
  }, 60_000)
})
