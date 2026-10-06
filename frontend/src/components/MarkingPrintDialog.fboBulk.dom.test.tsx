// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setSeparateMarkingPrintEnabled } from '../utils/separateMarkingPrint'
import {
  MarkingPrintDialog,
  type FboBulkContext,
  type FboBulkPrintResponse,
  type MarkingPrintContext,
} from './MarkingPrintDialog'

vi.mock('./MarkingLabelPreview', () => ({ MarkingLabelPreview: () => null }))
vi.mock('../utils/printMarkingCodeLabel', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  beginPrintUserGesture: vi.fn(),
  cancelPendingPrintWindow: vi.fn(),
  // The dialog's print spool is the piece we don't want this suite to actually
  // execute (no browser; no bwip-js). Everything else — the server contract,
  // double-click guard, mode toggles, snapshot-driven tape input — is real.
  printTapeSections: vi.fn().mockResolvedValue(undefined),
}))

const makeLabel = (barcode = '4600000000024') => ({
  product_name: 'Product',
  sku_code: 'SKU-X',
  barcode,
})

let root: Root
let host: HTMLDivElement
let busy = false
const setBusy = (next: boolean) => {
  busy = next
  // Re-render so the dialog receives the updated busy prop.
  if (lastCtx) renderNow(lastCtx)
}
let lastCtx: MarkingPrintContext | null = null
function renderNow(ctx: MarkingPrintContext | null) {
  lastCtx = ctx
  root.render(
    <MarkingPrintDialog
      open
      reprint={false}
      ctx={ctx}
      busy={busy}
      onBusyChange={setBusy}
      onClose={() => {}}
    />,
  )
}

function render(ctx: MarkingPrintContext | null) {
  return act(async () => {
    renderNow(ctx)
  })
}

async function setQuantity(testId: string, value: string) {
  const input = document.querySelector<HTMLInputElement>(`[data-testid="${testId}"] input`)!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

const toggleBox = () =>
  document.querySelector<HTMLInputElement>('[data-testid="marking-print-fbo-split-articles"] input')
const confirmBtn = () => document.querySelector<HTMLButtonElement>('[data-testid="marking-print-confirm"]')
const modeToggle = () => document.querySelector<HTMLElement>('[data-testid="marking-print-mode-toggle"]')
const allowPartialBox = () =>
  document.querySelector<HTMLInputElement>('[data-testid="marking-print-allow-partial"] input')
const sepWbBtn = () => document.querySelector<HTMLButtonElement>('[data-testid="marking-print-sep-wb-print"]')
const dialogRoot = () => document.querySelectorAll('[data-testid="marking-print-dialog"]')

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  window.localStorage.clear()
  setSeparateMarkingPrintEnabled(false)
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: 404 })))
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  busy = false
  lastCtx = null
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

type MakeOpts = {
  print?: FboBulkContext['print']
  lines?: FboBulkContext['lines']
  mixed?: boolean
  qtyNeedPack?: number
}

const defaultCzLines: FboBulkContext['lines'] = [
  {
    lineId: 'line-A',
    productId: 'product-A',
    productName: 'A',
    skuCode: 'A',
    requiresHonestSign: true,
    qtyNeedPack: 2,
    productLabel: makeLabel('A1'),
  },
  {
    lineId: 'line-B',
    productId: 'product-B',
    productName: 'B',
    skuCode: 'B',
    requiresHonestSign: true,
    qtyNeedPack: 1,
    productLabel: makeLabel('B1'),
  },
]

const defaultMixedLines: FboBulkContext['lines'] = [
  {
    lineId: 'line-A',
    productId: 'product-A',
    productName: 'A',
    skuCode: 'A',
    requiresHonestSign: true,
    qtyNeedPack: 2,
    productLabel: makeLabel('A1'),
  },
  {
    lineId: 'line-B',
    productId: 'product-B',
    productName: 'B',
    skuCode: 'B',
    requiresHonestSign: false,
    qtyNeedPack: 1,
    productLabel: makeLabel('B1'),
  },
]

function makeServerResponse(lines: FboBulkContext['lines']): FboBulkPrintResponse {
  return {
    lines: lines.map((line) => ({
      lineId: line.lineId,
      productId: line.productId,
      productName: line.productName,
      skuCode: line.skuCode,
      requiresHonestSign: line.requiresHonestSign,
      quantity: line.qtyNeedPack,
      shortage: 0,
      productLabel: line.productLabel!,
      printedCodes: line.requiresHonestSign
        ? Array.from({ length: line.qtyNeedPack }, (_, i) => ({
            id: `${line.lineId}-code-${i}`,
            cisCode: `01GTIN${line.lineId}21SER${i}`,
            hasLabelArtifact: false,
          }))
        : [],
    })),
    shortage: 0,
  }
}

function makeFboBulkCtx(opts: MakeOpts = {}): MarkingPrintContext {
  const localLines = opts.lines ?? (opts.mixed ? defaultMixedLines : defaultCzLines)
  const print =
    opts.print
    ?? vi.fn<FboBulkContext['print']>(async () => makeServerResponse(localLines))
  return {
    token: 'test',
    productId: 'product-A',
    documentNumber: 'FBO 01.10.2026',
    qtyNeedPack: opts.qtyNeedPack ?? 3,
    markingAvailable: 0,
    qtyMarkingPrinted: 0,
    requiresHonestSign: true,
    skuCode: 'FBO',
    productName: 'Отгрузка',
    productLabel: makeLabel('A1'),
    fboBulk: { taskId: 'task-1', lines: localLines, print },
    onPrinted: vi.fn(),
  }
}

describe('WMS-618 FBO bulk uses the same MarkingPrintDialog', () => {
  it('C1/R2: renders exactly one dialog instance (no second parallel bulk dialog)', async () => {
    await render(makeFboBulkCtx())
    expect(dialogRoot().length).toBe(1)
  })

  it('C1/C4: shows the "Разделять артикулами" toggle in bulk, off by default', async () => {
    await render(makeFboBulkCtx())
    const toggle = toggleBox()
    expect(toggle).not.toBeNull()
    expect(toggle!.checked).toBe(false)
  })

  it('C7: does NOT show the toggle in a non-bulk (per-line) print (R4)', async () => {
    const perLineCtx: MarkingPrintContext = {
      token: 'test',
      productId: 'product-X',
      documentNumber: 'FBS',
      qtyNeedPack: 1,
      markingAvailable: 10,
      qtyMarkingPrinted: 0,
      requiresHonestSign: true,
      skuCode: 'SKU-X',
      productName: 'Товар X',
      productLabel: makeLabel('X'),
      lineId: 'line-x',
      onPrinted: vi.fn(),
    }
    await render(perLineCtx)
    expect(toggleBox()).toBeNull()
  })

  it('R10: keeps the joint/separate toggle in bulk (not hidden)', async () => {
    await render(makeFboBulkCtx())
    expect(modeToggle()).not.toBeNull()
  })

  it('WMS-618 P2 R9: double-click fires exactly one bulk request (real guard, no manual busy)', async () => {
    // Resolve the server call only after both clicks fire — simulates a slow
    // network. The dialog's own in-flight ref must gate the second click.
    let resolveFirst!: (value: FboBulkPrintResponse) => void
    const serverPromise = new Promise<FboBulkPrintResponse>((resolve) => {
      resolveFirst = resolve
    })
    const print = vi.fn<FboBulkContext['print']>(() => serverPromise)
    await render(makeFboBulkCtx({ print }))

    const btn = confirmBtn()
    expect(btn).not.toBeNull()
    // Both clicks dispatched synchronously (same microtask) BEFORE busy
    // propagates through React state. If the guard were state-only, both
    // would fire; the ref guard turns the second into a no-op.
    await act(async () => {
      btn!.click()
      btn!.click()
    })
    expect(print).toHaveBeenCalledTimes(1)

    // Finish the inflight call; a third click after resolution still only
    // fires because the second was dropped by the ref, not queued.
    await act(async () => {
      resolveFirst(makeServerResponse(defaultCzLines))
    })
    expect(print).toHaveBeenCalledTimes(1)
  })

  it('C8/R9: surfaces a server-reported shortage without silently claiming success', async () => {
    const print = vi.fn<FboBulkContext['print']>(async () => ({ lines: [], shortage: 2 }))
    await render(makeFboBulkCtx({ print }))
    await act(async () => {
      confirmBtn()!.click()
    })
    expect(print).toHaveBeenCalledTimes(1)
    expect(
      document.querySelector('[data-testid="marking-print-error"]')?.textContent,
    ).toContain('Не хватает 2')
  })

  it('C3: shows plan summary with current totals from the local snapshot', async () => {
    await render(makeFboBulkCtx())
    const summary = document.querySelector<HTMLElement>('[data-testid="marking-print-qty"]')
    expect(summary?.textContent).toContain('В отгрузке: 3')
  })

  it('R7: shows the allowPartial checkbox in bulk when any CZ line is present', async () => {
    await render(makeFboBulkCtx())
    expect(allowPartialBox()).not.toBeNull()
  })

  it('R3: mixed shipment (CZ + non-CZ) opens bulk dialog in CZ constructor mode', async () => {
    await render(makeFboBulkCtx({ mixed: true }))
    expect(modeToggle()).not.toBeNull()
    expect(toggleBox()).not.toBeNull()
  })

  it('R3/C2: separate CZ quantity replaces the joint summary (28 × 3, not 28 × 2)', async () => {
    const lines = [{ ...defaultCzLines[0]!, qtyNeedPack: 28 }]
    await render(makeFboBulkCtx({ lines, qtyNeedPack: 28 }))
    await setQuantity('marking-print-cz-qty', '2')
    await setQuantity('marking-print-wb-qty', '0')
    expect(document.querySelector('[data-testid="marking-print-will-print"]')?.textContent)
      .toContain('ЧЗ: 56')

    await act(async () => {
      document.querySelector<HTMLButtonElement>('[data-testid="marking-print-mode-separate"]')!.click()
    })
    await setQuantity('marking-print-sep-cz-qty', '3')

    expect(document.querySelector('[data-testid="marking-print-sep-cz-total"]')?.textContent)
      .toBe('К печати: 84 ЧЗ (28 ед. × 3)')
    expect(document.querySelector('[data-testid="marking-print-will-print"]')).toBeNull()
  })

  it('R3/C2: separate CZ explanation counts only eligible units in a mixed shipment', async () => {
    const lines = defaultMixedLines.map((line) => ({ ...line, qtyNeedPack: 1 }))
    await render(makeFboBulkCtx({ lines, qtyNeedPack: 2 }))
    await act(async () => {
      document.querySelector<HTMLButtonElement>('[data-testid="marking-print-mode-separate"]')!.click()
    })
    await setQuantity('marking-print-sep-cz-qty', '1')

    expect(document.querySelector('[data-testid="marking-print-sep-cz-total"]')?.textContent)
      .toBe('К печати: 1 ЧЗ (1 ед. × 1)')
  })

  it('R3/C2: no-CZ bulk summary counts two WB labels for each of three units', async () => {
    const lines = [{ ...defaultMixedLines[1]!, qtyNeedPack: 3 }]
    const ctx = makeFboBulkCtx({ lines, qtyNeedPack: 3 })
    ctx.requiresHonestSign = false
    await render(ctx)
    await setQuantity('marking-print-wb-qty', '2')
    expect(document.querySelector('[data-testid="marking-print-will-print"]')?.textContent)
      .toContain('6 блок(ов) в ленте')
  })

  it('WMS-618 P2 R9: joint confirm asks the server to issue CZ codes', async () => {
    const print = vi.fn<FboBulkContext['print']>(async () => makeServerResponse(defaultCzLines))
    await render(makeFboBulkCtx({ print }))
    await act(async () => {
      confirmBtn()!.click()
    })
    expect(print).toHaveBeenCalledTimes(1)
    expect(print.mock.calls[0]![0].issueMarkingCodes).toBe(true)
  })

  it('WMS-618 P2 R9: separate ШК confirm pulls a fresh server snapshot WITHOUT issuing CZ', async () => {
    // Switch to separate mode first.
    const print = vi.fn<FboBulkContext['print']>(async () => makeServerResponse(defaultMixedLines))
    await render(makeFboBulkCtx({ mixed: true, print }))
    // Click the "Separate" button in the mode toggle.
    const separate = document.querySelector<HTMLButtonElement>('[data-testid="marking-print-mode-separate"]')
    expect(separate).not.toBeNull()
    await act(async () => {
      separate!.click()
    })
    const wbBtn = sepWbBtn()
    expect(wbBtn).not.toBeNull()
    await act(async () => {
      wbBtn!.click()
    })
    expect(print).toHaveBeenCalledTimes(1)
    expect(print.mock.calls[0]![0].issueMarkingCodes).toBe(false)
  })
})
