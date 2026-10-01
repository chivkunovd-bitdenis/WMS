import { apiUrl } from '../../api'
import { dispatchPreparedQrInKiosk } from '../../utils/printPreparedQr'
import { renderCzLabelPng } from '../../utils/czLabelPng'
import { loadLabelSizeId, resolveLabelSize } from '../../utils/labelSize'
import { startClaimedAutomaticPrint } from './fbsKizAutoReprint'
import {
  claimFbsPendingProductScan, completeFbsPendingProductScan, peekFbsPendingProductScan,
  updateFbsPendingProductScan, type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'
import {
  assignFbsPackingBoxOrders, cancelFbsScanAutoPrintSelection, rollbackFbsOrderScanKiz, undoFbsPackingScan, claimFbsDirectKizPrint,
  claimFbsScanAutoPrintReprint, claimFbsScanAutoPrintTarget, commitFbsKiz, createFbsIdempotencyKey,
  lookupFbsOrderBySticker, markFbsDirectKizPrintStarted, markFbsScanAutoPrintTargetStarted,
  releaseFbsDirectKizPrintClaim, releaseFbsScanAutoPrintTargetClaim,
  resolveFbsAssetUrl, saveFbsDirectKizReprint, scanFbsProductForAutoPrint, startFbsSupplyWork, validateFbsKiz,
  FbsApiError, type FbsKizLookup, type FbsScanAutoPrintReprintClaim, type FbsScanAutoPrintResult, type FbsWorkspace,
} from './fbsApi'
import type { PackagingTask } from '../ff/FfPackagingPage'

export type PackingScanView = { orderId: string; name: string; needsKiz: boolean; target?: FbsKizLookup | null } | null
/**
 * One operator scan and everything it saved (WMS-631 R19, Д14): a selection by
 * product barcode or sticker, a KIZ scan, or a KIZ scanned into the row field.
 */
export type PackingScanStep = {
  seq: number
  kind: 'select' | 'kiz' | 'row'
  result: FbsScanAutoPrintResult
  barcode: string
  explicit: boolean
  preferences: FbsScanPrintPreferences
  /** The KIZ this scan wrote to the order (scanned and newly bound, or from the pool). */
  kiz: string | null
  /** Set when this scan packed the unit. */
  packKey: string | null
  /** The box this scan put the order in. */
  boxId: string | null
}
export type PackingPackOutcome = { packed: boolean; boxId: string | null }
let packingStepSeq = 0

export function packingScanPackKey(result: FbsScanAutoPrintResult): string {
  return `${result.scan_id}:packed`
}
export type PackingScanController = {
  hasSelectedRow?: () => boolean
  scan: (raw: string) => Promise<void>
  scanOrder?: (orderId: string, raw: string, target?: FbsKizLookup) => Promise<void>
  /** R20: drop a selection that still waits for its KIZ; true when one was dropped. */
  cancel?: () => Promise<boolean>
  /** Synchronous: Escape has something to drop (a selection waiting for KIZ or in flight). */
  canCancel?: () => boolean
  /** R19: order number of the newest step that can be undone, or null. */
  lastStep?: () => number | null
  /** R19: undo the newest step; on failure it stays in the history. */
  undo?: () => Promise<void>
  hasPending: () => boolean
  hasSavedAttempt: (raw: string) => boolean
  view: () => PackingScanView
}
export type PackingScanDeps = {
  active?: () => boolean
  /** Current checkbox state; a selection keeps the snapshot it was made with. */
  preferences: () => FbsScanPrintPreferences
  select: (barcode: string, key: string, preferences: FbsScanPrintPreferences, orderId?: string) => Promise<FbsScanAutoPrintResult>
  lookupSticker: (raw: string) => Promise<FbsKizLookup>
  /** Exact copy of a full KIZ without selecting an order (M16/M18). */
  directReprint: (raw: string) => Promise<void>
  release: (result: FbsScanAutoPrintResult) => Promise<void>
  preload: (result: FbsScanAutoPrintResult) => Promise<string>
  /** Resolves true when the scanned code was newly bound (not already the order's KIZ). */
  bind: (result: FbsScanAutoPrintResult, raw: string, replace?: boolean) => Promise<boolean | void>
  print: (result: FbsScanAutoPrintResult, image: string) => Promise<void>
  printChz: (result: FbsScanAutoPrintResult) => Promise<void>
  printCopy: (result: FbsScanAutoPrintResult) => Promise<void>
  pack: (result: FbsScanAutoPrintResult, explicit: boolean, barcode: string) => Promise<PackingPackOutcome | void>
  /** R19: server undo of one step (unpack, box, selection, KIZ). */
  undo: (step: PackingScanStep) => Promise<void>
  claim: (raw: string, preferences: FbsScanPrintPreferences) => { key: string; preferences: FbsScanPrintPreferences }
  saved: (raw: string) => boolean
  remember: (raw: string, result: FbsScanAutoPrintResult) => void
  complete: (raw: string) => void
  changed: () => void
}

const NOT_FOUND_CODES = ['scan_product_not_found', 'scan_product_exhausted', 'sticker_not_found']
const LOCAL_SCAN_PREFIX = 'local:'

/** A selection made without scan-auto-print (all checkboxes off, Д4/R9). */
export function isLocalPackingSelection(result: FbsScanAutoPrintResult): boolean {
  return result.scan_id.startsWith(LOCAL_SCAN_PREFIX)
}

function localSelection(key: string, target: FbsKizLookup): FbsScanAutoPrintResult {
  return {
    scan_id: `${LOCAL_SCAN_PREFIX}${key}`, order_id: target.order_id, wb_order_id: target.wb_order_id,
    replayed: false, binding_target: target, reprint_recovery: null,
    requires_honest_sign: target.requires_honest_sign === true,
    qr_asset: null, codes: [], printed_codes: [], shortage: 0, order_errors: [],
  }
}

function requiresKiz(result: FbsScanAutoPrintResult): boolean {
  return result.binding_target?.requires_honest_sign ?? result.requires_honest_sign
}

/** Sticker and row selections never take a pool KIZ (Д5, Д6). */
function explicitServerModes(preferences: FbsScanPrintPreferences): boolean {
  return preferences.printQr || preferences.reprintChz
}

/** Resume an uncertain selection first, then continue through the remaining supplies. */
export async function routePackingScan(controllers: PackingScanController[], raw: string): Promise<void> {
  const selectedRow = controllers.find((one) => one.hasSelectedRow?.())
  let remaining = controllers
  if (selectedRow) {
    try { await selectedRow.scan(raw); return }
    catch (cause) {
      if (selectedRow.hasSelectedRow?.() || selectedRow.hasPending()
        || !(cause instanceof FbsApiError)
        || !NOT_FOUND_CODES.includes(cause.code)) throw cause
      // Замена завершилась, и следующий товар оказался из другой поставки.
      // Уже проверенную поставку не вызываем второй раз.
      remaining = controllers.filter((one) => one !== selectedRow)
    }
  }
  const pending = remaining.find((one) => one.hasPending())
  if (pending) return pending.scan(raw)
  const saved = remaining.find((one) => one.hasSavedAttempt(raw))
  const ordered = saved ? [saved, ...remaining.filter((one) => one !== saved)] : remaining
  let stickerNotFound: FbsApiError | null = null
  for (const controller of ordered) {
    try { await controller.scan(raw); return }
    catch (cause) {
      if (cause instanceof FbsApiError && NOT_FOUND_CODES.includes(cause.code)) {
        if (cause.code === 'sticker_not_found') stickerNotFound = cause
        continue
      }
      throw cause
    }
  }
  // All checkboxes off: the same error as the ordinary supply showed (R9).
  if (stickerNotFound) throw stickerNotFound
  throw new Error('В этой сборке не осталось заказов с таким штрихкодом.')
}

type Pending = {
  barcode: string
  result: FbsScanAutoPrintResult
  preferences: FbsScanPrintPreferences
  explicit: boolean
  image: Promise<string> | null
  needsKiz: boolean
  /** A KIZ was bound for this selection: an exact copy may be printed (R8). */
  bound: boolean
  /** The pool had no KIZ; a repeated scan asks the server again (R7). */
  refresh: boolean
  /** The history step a later packing belongs to. */
  step: PackingScanStep | null
}

/** One selected order survives binding/printing failures; only success releases it. */
export function createPackingScanController(deps: PackingScanDeps): PackingScanController {
  let pending: Pending | null = null
  let selecting = false
  let cancelAfterSelect = false
  let undoing = false
  const history: PackingScanStep[] = []
  const pushStep = (kind: PackingScanStep['kind'], current: Pending, kiz: string | null) => {
    const step: PackingScanStep = {
      seq: ++packingStepSeq, kind, result: current.result, barcode: current.barcode,
      explicit: current.explicit, preferences: current.preferences, kiz, packKey: null, boxId: null,
    }
    history.push(step)
    current.step = step
  }
  const preload = (current: Pending) => {
    if (!current.preferences.printQr) return null
    const image = deps.preload(current.result)
    // Preload runs while the operator scans KIZ; consume rejection until finish.
    void image.catch(() => undefined)
    return image
  }
  const finish = async () => {
    if (!pending) return
    const current = pending
    if (deps.active?.() === false) throw new Error('Упаковка закрыта. Откройте её и повторите скан товара для продолжения.')
    const poolKiz = !current.explicit && current.preferences.printChz && requiresKiz(current.result)
    if (poolKiz && !current.result.printed_codes[0]) {
      current.refresh = true
      throw new Error(current.result.shortage > 0 ? 'Не хватает ЧЗ для выбранной единицы.' : 'ЧЗ выбранной единицы не подготовлен.')
    }
    // Д10: QR first, then the KIZ label or its exact copy.
    if (current.preferences.printQr) {
      if (!current.image) current.image = deps.preload(current.result)
      await deps.print(current.result, await current.image)
    }
    if (poolKiz) await deps.printChz(current.result)
    if (current.preferences.reprintChz && current.bound) await deps.printCopy(current.result)
    const outcome = await deps.pack(current.result, current.explicit, current.barcode)
    if (outcome?.packed && current.step) {
      current.step.packKey = packingScanPackKey(current.result)
      current.step.boxId = outcome.boxId
    }
    deps.complete(current.barcode)
    pending = null
    deps.changed()
  }
  const retryImage = (current: Pending) => {
    // Recover a failed preload on the same order; never reserve its neighbour.
    if (current.preferences.printQr) {
      current.image = (current.image ?? Promise.reject(new Error('preload'))).catch(() => deps.preload(current.result))
    }
  }
  const selectByProduct = async (raw: string, preferences: FbsScanPrintPreferences) => {
    const attempt = deps.claim(raw, preferences)
    const result = await deps.select(raw, attempt.key, attempt.preferences)
    deps.remember(raw, result)
    return { result, preferences: attempt.preferences, explicit: false }
  }
  const selectBySticker = async (raw: string, preferences: FbsScanPrintPreferences) => {
    const target = await deps.lookupSticker(raw)
    if (!target.can_bind) throw new Error(target.block_reason ?? 'На этот заказ ЧЗ внести нельзя')
    const attempt = deps.claim(raw, preferences)
    const result = explicitServerModes(attempt.preferences)
      ? await deps.select(raw, attempt.key, attempt.preferences, target.order_id)
      : localSelection(attempt.key, target)
    if (result.order_id !== target.order_id) throw new Error('Сервер вернул другой заказ.')
    deps.remember(raw, result)
    return { result, preferences: attempt.preferences, explicit: true }
  }
  /** Product barcode first (the main path), then the order sticker, then a direct KIZ copy. */
  const selectNew = async (raw: string) => {
    const preferences = deps.preferences()
    const anyMode = preferences.printQr || preferences.printChz || preferences.reprintChz
    let productMiss: unknown = null
    if (anyMode) {
      try { return await selectByProduct(raw, preferences) }
      catch (cause) {
        if (!(cause instanceof FbsApiError) || cause.code !== 'scan_product_not_found') throw cause
        productMiss = cause
      }
    }
    try { return await selectBySticker(raw, preferences) }
    catch (cause) {
      if (!(cause instanceof FbsApiError) || cause.code !== 'sticker_not_found') throw cause
      if (preferences.reprintChz) {
        try { await deps.directReprint(raw); return null }
        catch (reprintCause) {
          if (!(reprintCause instanceof FbsApiError) || reprintCause.code !== 'not_a_kiz') throw reprintCause
        }
      }
      throw productMiss ?? cause
    }
  }
  return {
    hasPending: () => pending !== null,
    hasSavedAttempt: deps.saved,
    view: () => pending ? {
      orderId: pending.result.order_id,
      name: pending.result.binding_target?.product.name ?? `WB № ${pending.result.wb_order_id}`,
      needsKiz: pending.needsKiz,
      target: pending.result.binding_target,
    } : null,
    canCancel: () => selecting || Boolean(pending?.needsKiz),
    lastStep: () => history.at(-1)?.seq ?? null,
    async undo() {
      if (undoing || selecting) throw new Error('Дождитесь окончания текущего скана.')
      const step = history.at(-1)
      if (!step) return
      undoing = true
      try {
        await deps.undo(step)
        history.pop()
        const same = pending?.result.scan_id === step.result.scan_id
        if (step.kind === 'kiz') {
          // The KIZ scan is undone: its order waits for the KIZ again, the selection stays.
          if (!pending || same) {
            pending = {
              barcode: step.barcode, result: step.result, preferences: step.preferences,
              explicit: step.explicit, image: null, needsKiz: true, bound: false, refresh: false,
              step: history.findLast((one) => one.result.scan_id === step.result.scan_id) ?? null,
            }
            pending.image = preload(pending)
          }
        } else {
          if (same) pending = null
          deps.complete(step.barcode)
        }
        deps.changed()
      } finally {
        undoing = false
      }
    },
    async cancel() {
      if (selecting) { cancelAfterSelect = true; return true }
      if (!pending || !pending.needsKiz) return false
      const current = pending
      if (!isLocalPackingSelection(current.result)) await deps.release(current.result)
      if (pending !== current) return true
      deps.complete(current.barcode)
      pending = null
      deps.changed()
      return true
    },
    async scanOrder(orderId, raw, target) {
      if (deps.active?.() === false) return
      if (pending && pending.result.order_id !== orderId) {
        if (!pending.needsKiz) throw new Error('Сначала завершите печать предыдущего заказа повторным сканом его штрихкода.')
        // Its durable product selection can still be resumed by its barcode.
        pending = null
      }
      const barcode = `order:${orderId}`
      try {
        if (!pending) {
          const attempt = deps.claim(barcode, deps.preferences())
          let result: FbsScanAutoPrintResult
          if (explicitServerModes(attempt.preferences)) {
            result = await deps.select(barcode, attempt.key, attempt.preferences, orderId)
          } else {
            if (!target) throw new Error('Заказ строки не найден.')
            result = localSelection(attempt.key, target)
          }
          if (result.order_id !== orderId) throw new Error('Сервер вернул другой заказ.')
          deps.remember(barcode, result)
          pending = {
            barcode, result, preferences: attempt.preferences, explicit: true,
            image: null, needsKiz: true, bound: false, refresh: false, step: null,
          }
          pending.image = preload(pending)
          deps.changed()
        }
        if (pending.needsKiz) {
          // R10, R18: the row's KIZ replaces its code at once, without any dialog.
          const newly = await deps.bind(pending.result, raw, true)
          pending.needsKiz = false
          pending.bound = true
          pushStep('row', pending, newly === true ? raw : null)
          deps.changed()
        }
        retryImage(pending)
        await finish()
      } catch (cause) {
        // A failed row scan never captures the following ordinary scans.
        if (pending?.barcode === barcode) pending = null
        deps.complete(barcode)
        deps.changed()
        throw cause
      }
    },
    async scan(raw) {
      if (deps.active?.() === false) return
      if (pending) {
        const current = pending
        if (!current.needsKiz && raw !== current.barcode) {
          throw new Error(`Не завершена упаковка ${current.result.binding_target?.product.name ?? `заказа WB № ${current.result.wb_order_id}`}. Повторите его штрихкод ${current.barcode}.`)
        }
        if (current.needsKiz && raw === current.barcode) {
          if (isLocalPackingSelection(current.result)) throw new Error('Товар уже выбран. Сканируйте его Честный знак.')
          const attempt = deps.claim(raw, current.preferences)
          const recovered = await deps.select(raw, attempt.key, attempt.preferences,
            current.explicit ? current.result.order_id : undefined)
          if (recovered.scan_id !== current.result.scan_id || recovered.order_id !== current.result.order_id) {
            throw new Error('Сервер вернул другой заказ для незавершённого скана.')
          }
          if (recovered.reprint_recovery?.status !== 'available') {
            throw new Error('Товар уже выбран. Сканируйте его Честный знак.')
          }
          current.needsKiz = false
          current.bound = true
          deps.changed()
        } else if (current.needsKiz) {
          // R18: an existing KIZ of the selected order is replaced without a dialog.
          const newly = await deps.bind(current.result, raw)
          current.needsKiz = false
          current.bound = true
          pushStep('kiz', current, newly === true ? raw : null)
          deps.changed()
        } else if (current.refresh) {
          // The same scan id asks the server for the pool KIZ again.
          const attempt = deps.claim(raw, current.preferences)
          const refreshed = await deps.select(raw, attempt.key, attempt.preferences)
          if (refreshed.scan_id !== current.result.scan_id || refreshed.order_id !== current.result.order_id) {
            throw new Error('Сервер вернул другой заказ для незавершённого скана.')
          }
          current.result = refreshed
          current.refresh = false
        }
        retryImage(current)
        await finish()
        return
      }
      selecting = true
      cancelAfterSelect = false
      let selected: Awaited<ReturnType<typeof selectNew>>
      try { selected = await selectNew(raw) }
      finally { selecting = false }
      if (!selected) return
      const { result, preferences, explicit } = selected
      if (cancelAfterSelect) {
        // Escape arrived while the selection was in flight: release it at once (R20).
        cancelAfterSelect = false
        if (!isLocalPackingSelection(result)) await deps.release(result)
        deps.complete(raw)
        deps.changed()
        return
      }
      if (deps.active?.() === false) return
      const bound = result.reprint_recovery?.status === 'available'
      // «Печатать ЧЗ» takes the KIZ from the pool; otherwise a KIZ product waits for its scan.
      const needsKiz = !(preferences.printChz && !explicit) && requiresKiz(result) && !bound
      pending = { barcode: raw, result, preferences, explicit, image: null, needsKiz, bound, refresh: false, step: null }
      pending.image = preload(pending)
      // A pool KIZ is bound by the server together with this selection (R7).
      const poolKiz = preferences.printChz && !explicit ? result.printed_codes[0]?.cis_code ?? null : null
      pushStep('select', pending, poolKiz)
      deps.changed()
      if (!pending.needsKiz) await finish()
    },
  }
}

export function makePackingScanDeps(
  token: string,
  authHeaders: (token: string) => Record<string, string>,
  workspace: () => FbsWorkspace,
  changed: () => void,
  refreshed: () => void,
  active: () => boolean = () => true,
  currentBox: () => string | null = () => null,
  onBound: (orderId: string, value: string) => void = () => undefined,
  onSelected: (orderId: string) => void = () => undefined,
  preferences: () => FbsScanPrintPreferences = () => ({ printQr: true, printChz: false, reprintChz: false }),
): PackingScanDeps {
  const supplyId = workspace().supply.id
  const scanBoxes = new Map<string, string | null>()
  const directKeys = new Map<string, string>()
  let startedWorkspace: FbsWorkspace | null = null
  const ensureSupplyStarted = async () => {
    const current = workspace()
    if (current.supply.id !== supplyId) throw new Error('Поставка изменилась. Повторите скан в исходной поставке.')
    if (current.supply.packaging_task_id) return current
    if (!startedWorkspace) startedWorkspace = await startFbsSupplyWork(token, authHeaders, supplyId)
    if (!startedWorkspace.supply.packaging_task_id) throw new Error('Не удалось начать работу с поставкой. Повторите скан.')
    return startedWorkspace
  }
  // Separate unfinished new-flow scans from historical checkbox-based print scans.
  const storageId = `${supplyId}:sequential-packing`
  const request = async (path: string, init?: RequestInit) => {
    const response = await fetch(apiUrl(path), { ...init, headers: {
      ...authHeaders(token), 'Content-Type': 'application/json', ...init?.headers,
    } })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new Error(error?.detail?.message ?? error?.detail?.code ?? 'Не удалось сохранить упаковку.')
    }
    return response.json()
  }
  const labelSize = () => resolveLabelSize(loadLabelSizeId())
  const send = (imageDataUrl: string, idempotencyKey: string) => {
    const size = labelSize()
    return dispatchPreparedQrInKiosk({ imageDataUrl, idempotencyKey, widthMm: size.widthMm, heightMm: size.heightMm })
  }
  return {
    active,
    preferences,
    claim: (raw, snapshot) => {
      const attempt = claimFbsPendingProductScan(token, storageId, raw, snapshot, createFbsIdempotencyKey)
      // Capture the operator's box before the request: an uncertain selection
      // and a later remount must never substitute the newly opened box.
      if (attempt.packingBoxId === undefined) {
        attempt.packingBoxId = currentBox()
        updateFbsPendingProductScan(token, storageId, attempt)
      }
      return { key: attempt.idempotencyKey, preferences: attempt.preferences }
    },
    saved: (raw) => Boolean(peekFbsPendingProductScan(token, storageId, raw)),
    remember: (raw, result) => {
      const attempt = peekFbsPendingProductScan(token, storageId, raw)
      if (!attempt) return
      if ((attempt.scanId && attempt.scanId !== result.scan_id) || (attempt.orderId && attempt.orderId !== result.order_id)) {
        throw new Error('Сервер вернул другой заказ для незавершённого скана.')
      }
      attempt.scanId = result.scan_id
      attempt.orderId = result.order_id
      updateFbsPendingProductScan(token, storageId, attempt)
      scanBoxes.set(result.scan_id, attempt.packingBoxId ?? null)
      onSelected(result.order_id)
    },
    complete: (raw) => { completeFbsPendingProductScan(token, storageId, raw); refreshed() },
    changed,
    select: async (barcode, idempotency_key, snapshot, orderId) => {
      try {
        return await scanFbsProductForAutoPrint(token, authHeaders, supplyId, {
          barcode, idempotency_key, print_qr: snapshot.printQr,
          // A sticker or row selection never allocates a pool KIZ (Д5, Д6).
          print_chz: orderId ? false : snapshot.printChz,
          reprint_chz: snapshot.reprintChz, await_honest_sign: true,
          ...(orderId ? { order_id: orderId } : {}),
        })
      } catch (cause) {
        if (cause instanceof FbsApiError && ['scan_product_not_found', 'scan_product_exhausted'].includes(cause.code)) {
          completeFbsPendingProductScan(token, storageId, barcode)
        }
        throw cause
      }
    },
    lookupSticker: (raw) => lookupFbsOrderBySticker(token, authHeaders, supplyId, raw),
    release: (result) => cancelFbsScanAutoPrintSelection(token, authHeaders, supplyId, result.scan_id),
    directReprint: async (raw) => {
      const idempotencyKey = directKeys.get(raw) ?? createFbsIdempotencyKey()
      directKeys.set(raw, idempotencyKey)
      let row
      try { row = await saveFbsDirectKizReprint(token, authHeaders, supplyId, raw, idempotencyKey) }
      catch (cause) {
        if (cause instanceof FbsApiError && cause.code === 'not_a_kiz') directKeys.delete(raw)
        throw cause
      }
      const printKey = `kiz-copy:${row.id}`
      await startClaimedAutomaticPrint(createFbsIdempotencyKey(), async () => {
        await send(await renderCzLabelPng({ cis: row.kiz }, labelSize()), printKey)
      }, {
        claim: async (attemptKey) => {
          const claim = await claimFbsDirectKizPrint(token, authHeaders, supplyId, row.id, attemptKey)
          return { claimed: claim.claimed, started: Boolean(claim.row.print_started_at) }
        },
        markStarted: async () => {
          const saved = await markFbsDirectKizPrintStarted(token, authHeaders, supplyId, row.id)
          return { claimed: false, started: Boolean(saved.print_started_at) }
        },
        releaseClaim: (attemptKey) => releaseFbsDirectKizPrintClaim(token, authHeaders, supplyId, row.id, attemptKey),
      })
      directKeys.delete(raw)
    },
    preload: async (result) => {
      if (!result.qr_asset?.preview_url) throw new Error('Стикер QR заказа не получен.')
      const response = await fetch(resolveFbsAssetUrl(result.qr_asset.preview_url), { headers: authHeaders(token) })
      if (!response.ok) throw new Error('Не удалось загрузить стикер заказа.')
      const blob = await response.blob()
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onerror = () => reject(new Error('Не удалось прочитать стикер заказа.'))
        reader.onload = () => resolve(String(reader.result))
        reader.readAsDataURL(blob)
      })
    },
    bind: async (result, raw, replace = false) => {
      await validateFbsKiz(token, authHeaders, result.order_id, raw)
      // The ordinary supply screen starts work before KIZ binding. The unified
      // screen has no Start button, so preserve the same server prerequisite here.
      await ensureSupplyStarted()
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))
      const codeKey = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
      const commit = (confirmed: boolean) => commitFbsKiz(token, authHeaders, [{
        order_id: result.order_id, value: raw, confirmed,
        ...(isLocalPackingSelection(result) ? {} : { scan_auto_print_id: result.scan_id }),
      }], `${result.scan_id}:${codeKey}:${confirmed ? 'replace' : 'bind'}`)
      let outcomes = await commit(replace)
      let outcome = outcomes.find((item) => item.order_id === result.order_id)
      // R18: an order that already has a KIZ gets the scanned one at once, without a dialog.
      if (outcome?.code === 'needs_confirmation') {
        outcomes = await commit(true)
        outcome = outcomes.find((item) => item.order_id === result.order_id)
      }
      if (outcome?.status !== 'ok') throw new Error(outcome?.message ?? 'Честный знак не сохранён.')
      onBound(result.order_id, outcome.bound_kiz ?? raw)
      refreshed()
      return outcome.newly_bound === true
    },
    print: async (result, imageDataUrl) => {
      await startClaimedAutomaticPrint(result.scan_id,
        () => send(imageDataUrl, result.scan_id), {
          claim: (key) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          markStarted: (key) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          // Preserve ownership after an uncertain print dispatch. The exact same
          // scan UUID lets the print transport reconcile a retry; it must never
          // create a new print intent or give this order to another scan.
          releaseClaim: async () => undefined,
        })
    },
    printChz: async (result) => {
      const code = result.printed_codes[0]
      if (!code) throw new Error('ЧЗ выбранной единицы не подготовлен.')
      const key = `${result.scan_id}:chz`
      await startClaimedAutomaticPrint(key, async () => {
        const image = await renderCzLabelPng(
          { cis: code.cis_code, codeId: code.id, hasLabelArtifact: code.has_label_artifact }, labelSize(), token)
        await send(image, key)
      }, {
        claim: (attemptKey) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        // Same rule as QR: WMS Print reconciles a retry of this key; no new intent.
        releaseClaim: async () => undefined,
      })
    },
    printCopy: async (result) => {
      const key = `${result.scan_id}:copy`
      await startClaimedAutomaticPrint<FbsScanAutoPrintReprintClaim>(key, async (claim) => {
        if (!claim.kiz) throw new Error('Сервер не подтвердил канонический ЧЗ для перепечати.')
        await send(await renderCzLabelPng({ cis: claim.kiz }, labelSize()), key)
      }, {
        claim: (attemptKey) => claimFbsScanAutoPrintReprint(token, authHeaders, supplyId, result.scan_id, attemptKey),
        markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        // The reprint slot must be released to be claimed again; WMS Print still
        // deduplicates the job by its key, so a retry never prints a second copy.
        releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
      })
    },
    pack: async (result, explicit, barcode) => {
      const current = await ensureSupplyStarted()
      // A sticker or row scan of an already packed order must not pack a second unit.
      if (explicit && current.orders.some((order) => order.id === result.order_id && order.pack.status === 'packed')) {
        return { packed: false, boxId: null }
      }
      const taskId = current.supply.packaging_task_id
      if (!taskId) throw new Error('Задание упаковки ещё не создано.')
      const task = await request(`/operations/packaging-tasks/${taskId}`) as PackagingTask
      const order = current.orders.find((row) => row.id === result.order_id)
      const line = task.lines.find((row) => row.product_id === order?.product.id)
      if (!line) throw new Error('Не найдена строка упаковки выбранного заказа.')
      await request(`/operations/packaging-tasks/${taskId}/lines/${line.id}/pack`, { method: 'POST', body: JSON.stringify({
        quantity: 1, order_id: result.order_id, idempotency_key: packingScanPackKey(result),
      }) })
      const boxId = scanBoxes.get(result.scan_id) ?? peekFbsPendingProductScan(token, storageId, barcode)?.packingBoxId ?? null
      if (boxId && !current.boxes.some((box) => box.assigned_order_ids.includes(result.order_id))) {
        await assignFbsPackingBoxOrders(token, authHeaders, supplyId, boxId, [result.order_id])
        return { packed: true, boxId }
      }
      return { packed: true, boxId: null }
    },
    undo: async (step) => {
      const local = isLocalPackingSelection(step.result)
      const release = step.kind !== 'kiz' && !local
      if (step.packKey || step.boxId || release) {
        await undoFbsPackingScan(token, authHeaders, supplyId, {
          order_id: step.result.order_id,
          scan_id: local ? null : step.result.scan_id,
          pack_idempotency_key: step.packKey,
          box_id: step.boxId,
          release_selection: release,
        })
      }
      if (step.kiz) await rollbackFbsOrderScanKiz(token, authHeaders, step.result.order_id, step.kiz)
      refreshed()
    },
  }
}
