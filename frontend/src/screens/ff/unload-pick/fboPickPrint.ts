import { cellPickRowsOf, chainOf, isInside, type PickPlace, type PickRow } from './pickRows'
import { KIND_TITLE, type Cell, type WarehouseObject } from './pickStub'
import type { FboPickView } from './fboPickState'

export type FboPrintSelection = {
  selected: Set<string>
  onToggle: (keys: string[], checked: boolean) => void
}

/** Real identities, never the visible cell/box names. Moving a source invalidates its old address. */
export function printSourceKey(row: PickRow, place: PickPlace, objects: WarehouseObject[], cells: Cell[]): string {
  const { cell } = chainOf(place.holder, objects, cells)
  return JSON.stringify([row.product.id, cell?.id ?? null, place.key])
}

export function printBranchKeys(rows: PickRow[], branch: string, objects: WarehouseObject[], cells: Cell[]): string[] {
  return rows.flatMap((row) => row.places
    .filter((place) => branch === 'no-cell'
      ? !chainOf(place.holder, objects, cells).cell
      : isInside(place.holder, branch, objects))
    .map((place) => printSourceKey(row, place, objects, cells)))
}

const STORAGE_KEY = 'wms.fbo-pick.print.v1.'

export function loadPrintSelection(documentId: string | null): Set<string> {
  try {
    const value: unknown = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY + documentId) ?? '[]')
    return new Set(documentId && Array.isArray(value) ? value.filter((one): one is string => typeof one === 'string') : [])
  } catch {
    return new Set()
  }
}

export function savePrintSelection(documentId: string, selected: Set<string>): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY + documentId, JSON.stringify([...selected]))
  } catch {
    // As with WMS-686 UI state, unavailable storage does not prevent working.
  }
}

function escapeHtml(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;')
}

export function buildFboPickPrintHtml({ rows, objects, cells, view, selected, document, seller, marketplace, pickedByProduct }: {
  rows: PickRow[]
  objects: WarehouseObject[]
  cells: Cell[]
  view: FboPickView
  selected: Set<string>
  document: string
  seller: string
  marketplace?: 'wb' | 'ozon'
  /** Server pick facts remain valid even when address storage returns no locations. */
  pickedByProduct?: ReadonlyMap<string, number>
}): string {
  const printRows = rows.map((row) => {
    const picked = pickedByProduct?.get(row.product.id)
    return picked === undefined ? row : { ...row, picked, left: Math.max(0, row.plan - picked) }
  })
  const tree = cellPickRowsOf(printRows, objects, cells)
  const goods = tree.filter((item) => item.kind === 'goods')
  const current = new Set(goods.flatMap((item) => item.place ? [printSourceKey(item.row, item.place, objects, cells)] : []))
  const chosen = new Set([...selected].filter((key) => current.has(key)))
  const included = goods.filter((item) => !chosen.size || (item.place && chosen.has(printSourceKey(item.row, item.place, objects, cells))))
  const ordered = view === 'cells' ? included : printRows.flatMap((row) => included.filter((item) => item.row.key === row.key))
  const headers = view === 'products'
    ? ['Товар', 'Ячейка', 'Короб / тара', 'Количество, шт', 'План', 'Осталось']
    : ['Ячейка', 'Короб / тара', 'Товар', 'Количество, шт', 'План', 'Осталось']
  const renderRows = (alreadyPicked: boolean) => {
    let previousGroup: string | null = null
    return ordered.filter((item) => Boolean(item.alreadyPicked) === alreadyPicked).map(({ row, place }) => {
      const { cell, chain } = place ? chainOf(place.holder, objects, cells) : { cell: null, chain: [] }
      const product = `${row.product.name} · ${row.product.sellerArticle ? `${row.product.sellerArticle} · ` : ''}${row.product.sku}${row.product.size ? ` · ${row.product.size}` : ''}${!place ? ' · Нет на складе' : ''}`
      const address = cell?.code ?? 'Без ячейки'
      const container = chain.length ? chain.map((one) => `${KIND_TITLE[one.kind]} ${one.code}`).join(' → ') : place ? 'Россыпью' : '—'
      const columns = view === 'products' ? [product, address, container] : [address, container, product]
      const group = view === 'products' ? row.key : cell?.id ?? 'no-cell'
      const startsGroup = previousGroup !== group
      previousGroup = group
      return `<tr${startsGroup ? ' class="group-start"' : ''}>${columns.map((value) => `<td>${escapeHtml(value)}</td>`).join('')}<td class="number">${place?.qty ?? '—'}</td><td class="number">${row.plan}</td><td class="number">${row.left}</td></tr>`
    }).join('')
  }
  const pickedRows = renderRows(true)
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Лист подбора — ${escapeHtml(document)}</title>
<style>
@page { size: A4 landscape; margin: 10mm; }
body { font: 11px/1.35 Arial, sans-serif; color: #111; margin: 0; }
h1 { font-size: 18px; margin: 0 0 8px; } p { margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; table-layout: auto; }
thead { display: table-header-group; } th, td { border: 1px solid #555; padding: 5px; vertical-align: top; }
td { overflow-wrap: anywhere; }
th { text-align: left; background: #eee; white-space: nowrap; overflow-wrap: normal; word-break: normal; }
.number { text-align: right; white-space: nowrap; }
tr.group-start td { border-top-width: 2px; }
tr { break-inside: avoid; } .section { font-weight: bold; background: #eee; }
</style></head><body><h1>Лист подбора</h1><p>${escapeHtml(document)}<br>Селлер: ${escapeHtml(seller)}${marketplace ? `<br>Маркетплейс: ${marketplace === 'ozon' ? 'Ozon' : 'WB'}` : ''}</p>
<table><thead><tr>${headers.map((header) => `<th>${header}</th>`).join('')}</tr></thead><tbody>${renderRows(false)}${pickedRows ? `<tr><td colspan="6" class="section">Уже подобрано</td></tr>${pickedRows}` : ''}</tbody></table></body></html>`
}

/** A separate print document; no warehouse requests or changes to scanning state. */
export function printFboPickHtml(html: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const frame = window.document.createElement('iframe')
    frame.setAttribute('aria-hidden', 'true')
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:297mm;height:210mm;border:0'
    let scheduled = false
    let settled = false
    let printTimer: number | undefined
    let cleanupTimer: number | undefined
    const cleanup = () => {
      window.clearTimeout(printTimer)
      window.clearTimeout(cleanupTimer)
      frame.onload = null
      frame.onerror = null
      frame.remove()
    }
    const fail = () => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      cleanup()
      reject(new Error('Не удалось открыть печать листа подбора'))
    }
    const timeout = window.setTimeout(fail, 20000)
    frame.onload = () => {
      if (scheduled || settled) return
      scheduled = true
      const target = frame.contentWindow
      if (!target) { fail(); return }
      try { target.focus() } catch { /* Focus may be denied by the browser. */ }
      // A print dialog may return before it finishes (for example in Safari).
      // Keep its document until afterprint, with a fallback for a lost browser event.
      target.addEventListener('afterprint', () => {
        window.clearTimeout(cleanupTimer)
        cleanupTimer = window.setTimeout(cleanup, 500)
      }, { once: true })
      printTimer = window.setTimeout(() => {
        if (settled) return
        try {
          target.print()
          if (settled) return
          settled = true
          window.clearTimeout(timeout)
          if (cleanupTimer === undefined) cleanupTimer = window.setTimeout(cleanup, 60000)
          resolve()
        } catch {
          fail()
        }
      }, 100)
    }
    frame.onerror = fail
    try {
      frame.srcdoc = html
      window.document.body.appendChild(frame)
    } catch {
      fail()
    }
  })
}
