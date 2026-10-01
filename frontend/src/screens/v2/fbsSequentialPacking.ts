import { apiUrl } from '../../api'
import { dispatchPreparedQrInKiosk } from '../../utils/printPreparedQr'
import { renderCzLabelPng } from '../../utils/czLabelPng'
import { loadLabelSizeId, resolveLabelSize, type LabelSizeId } from '../../utils/labelSize'
import { startClaimedAutomaticPrint } from './fbsKizAutoReprint'
import {
  claimFbsPendingProductScan, completeFbsPendingProductScan, peekFbsPendingProductScan,
  updateFbsPendingProductScan, type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'
import {
  assignFbsPackingBoxOrders, cancelFbsScanAutoPrintSelection, undoFbsPackingScan, claimFbsDirectKizPrint,
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
 * Recorded as an intent before its requests and refined by their answers, so a
 * failure in the middle still knows what may have been saved (the server undo
 * of each part is a no-op when that part did not happen).
 */
export type PackingScanStep = {
  seq: number
  kind: 'select' | 'kiz' | 'row'
  result: FbsScanAutoPrintResult
  barcode: string
  explicit: boolean
  preferences: FbsScanPrintPreferences
  labelSizeId: LabelSizeId
  /** The KIZ this scan bound (canonical value), or the pool KIZ this scan was given. */
  kiz: string | null
  /** Set before the pack request of this scan. */
  packKey: string | null
  /** Set before this scan puts the order into a box. */
  boxId: string | null
}
let packingStepSeq = 0

export function packingScanPackKey(result: FbsScanAutoPrintResult): string {
  return `${result.scan_id}:packed`
}

/** A bind the server definitely refused: nothing of it was saved. */
export class PackingBindRejectedError extends Error {}

/**
 * WMS-631 P0-06: scans, Escape and «Назад» run strictly one after another for
 * every WB packing controller on the page.
 */
let packingChain: Promise<unknown> = Promise.resolve()
let packingQueued = 0
export function runPackingSerial<T>(task: () => Promise<T>): Promise<T> {
  packingQueued += 1
  const run = packingChain.then(task, task)
  packingChain = run.catch(() => undefined).finally(() => { packingQueued -= 1 })
  return run
}
export function packingSerialBusy(): boolean {
  return packingQueued > 0
}

export type PackingScanController = {
  hasSelectedRow?: () => boolean
  scan: (raw: string) => Promise<void>
  scanOrder?: (orderId: string, raw: string, target?: FbsKizLookup) => Promise<void>
  /** R20: drop the started scan (waiting for KIZ or after a print failure); true when dropped. */
  cancel?: () => Promise<boolean>
  /** Synchronous: Escape has something to drop now or a queued operation to follow. */
  canCancel?: () => boolean
  /** R19: order number of the newest step that can be undone, or null. */
  lastStep?: () => number | null
  /** R19: undo the newest step; resolves a warning text when the result is partial. */
  undo?: () => Promise<string | null>
  hasPending: () => boolean
  hasSavedAttempt: (raw: string) => boolean
  view: () => PackingScanView
}
export type PackingAttempt = {
  key: string
  preferences: FbsScanPrintPreferences
  labelSizeId: LabelSizeId
  explicit: boolean
  orderId?: string
  qrDone: boolean
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
  /** Resolves the canonical KIZ bound to the order. Throws PackingBindRejectedError when nothing was saved. */
  bind: (result: FbsScanAutoPrintResult, raw: string, replace?: boolean) => Promise<string | void>
  print: (result: FbsScanAutoPrintResult, image: string, size: LabelSizeId) => Promise<void>
  printChz: (result: FbsScanAutoPrintResult, size: LabelSizeId) => Promise<void>
  printCopy: (result: FbsScanAutoPrintResult, size: LabelSizeId) => Promise<void>
  /** Packs one unit; notes the pack key and box on the step before each request. */
  pack: (result: FbsScanAutoPrintResult, explicit: boolean, barcode: string, step: PackingScanStep | null) => Promise<void>
  /** R19: server undo of one step (KIZ, unit, box, selection); resolves a warning or null. */
  undo: (step: PackingScanStep, releaseSelection: boolean) => Promise<string | null>
  claim: (raw: string, preferences: FbsScanPrintPreferences, explicit?: boolean) => PackingAttempt
  attempt?: (raw: string) => PackingAttempt | null
  markQrDone?: (raw: string) => void
  saved: (raw: string) => boolean
  remember: (raw: string, result: FbsScanAutoPrintResult) => void
  complete: (raw: string) => void
  changed: () => void
}

const NOT_FOUND_CODES = ['scan_product_not_found', 'scan_product_exhausted', 'sticker_not_found']
const LOCAL_SCAN_PREFIX = 'local:'
/** Д20: a step that can never be undone leaves the top of the history with its error. */
const UNDO_FINAL_CODES = ['scan_undo_order_moved', 'scan_undo_task_closed', 'order_frozen', 'order_not_found']

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

function poolKizOf(result: FbsScanAutoPrintResult): string | null {
  return result.chz_issued_by_scan ? result.printed_codes[0]?.cis_code ?? null : null
}

/** Resume an uncertain selection first, then continue through the remaining supplies. */
export function routePackingScan(controllers: PackingScanController[], raw: string): Promise<void> {
  return runPackingSerial(() => routePackingScanNow(controllers, raw))
}

async function routePackingScanNow(controllers: PackingScanController[], raw: string): Promise<void> {
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
  labelSizeId: LabelSizeId
  explicit: boolean
  image: Promise<string> | null
  needsKiz: boolean
  /** A KIZ was bound for this selection: an exact copy may be printed (R8). */
  bound: boolean
  /** The QR of this order was already handed to WMS Print by an earlier attempt. */
  qrDone: boolean
  /** The pool had no KIZ; a repeated scan asks the server again (R7). */
  refresh: boolean
  /** The history step a later packing belongs to. */
  step: PackingScanStep | null
}

/** One selected order survives binding/printing failures; only success releases it. */
export function createPackingScanController(deps: PackingScanDeps): PackingScanController {
  let pending: Pending | null = null
  const history: PackingScanStep[] = []
  const pushStep = (kind: PackingScanStep['kind'], current: Pending, kiz: string | null) => {
    const step: PackingScanStep = {
      seq: ++packingStepSeq, kind, result: current.result, barcode: current.barcode,
      explicit: current.explicit, preferences: current.preferences, labelSizeId: current.labelSizeId,
      kiz, packKey: null, boxId: null,
    }
    history.push(step)
    current.step = step
    return step
  }
  const dropStep = (step: PackingScanStep) => {
    const index = history.indexOf(step)
    if (index >= 0) history.splice(index, 1)
  }
  const preload = (current: Pending) => {
    if (!current.preferences.printQr || current.qrDone) return null
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
    if (current.preferences.printQr && !current.qrDone) {
      if (!current.image) current.image = deps.preload(current.result)
      await deps.print(current.result, await current.image, current.labelSizeId)
      current.qrDone = true
      deps.markQrDone?.(current.barcode)
    }
    if (poolKiz) await deps.printChz(current.result, current.labelSizeId)
    if (current.preferences.reprintChz && current.bound) await deps.printCopy(current.result, current.labelSizeId)
    await deps.pack(current.result, current.explicit, current.barcode, current.step)
    deps.complete(current.barcode)
    if (pending === current) pending = null
    deps.changed()
  }
  const retryImage = (current: Pending) => {
    // Recover a failed preload on the same order; never reserve its neighbour.
    if (current.preferences.printQr && !current.qrDone) {
      current.image = (current.image ?? Promise.reject(new Error('preload'))).catch(() => deps.preload(current.result))
    }
  }
  const startPending = (barcode: string, result: FbsScanAutoPrintResult, attempt: PackingAttempt, explicit: boolean, needsKiz: boolean, bound: boolean): Pending => {
    const next: Pending = {
      barcode, result, preferences: attempt.preferences, labelSizeId: attempt.labelSizeId, explicit,
      image: null, needsKiz, bound, qrDone: attempt.qrDone, refresh: false, step: null,
    }
    next.image = preload(next)
    return next
  }
  const bindKiz = async (current: Pending, raw: string, replace: boolean, kind: 'kiz' | 'row') => {
    // The intent is recorded first: a lost answer may still have saved the KIZ.
    const step = kind === 'row' ? pushStep('row', current, raw) : pushStep('kiz', current, raw)
    try {
      const canonical = await deps.bind(current.result, raw, replace)
      if (typeof canonical === 'string') step.kiz = canonical
    } catch (cause) {
      if (cause instanceof PackingBindRejectedError || cause instanceof FbsApiError) {
        dropStep(step)
        if (current.step === step) current.step = history.findLast((one) => one.result.scan_id === current.result.scan_id) ?? null
      }
      throw cause
    }
    current.needsKiz = false
    current.bound = true
    deps.changed()
  }
  const selectByProduct = async (raw: string, preferences: FbsScanPrintPreferences) => {
    const attempt = deps.claim(raw, preferences)
    const result = await deps.select(raw, attempt.key, attempt.preferences)
    deps.remember(raw, result)
    return { result, attempt, explicit: false }
  }
  const selectBySticker = async (raw: string, preferences: FbsScanPrintPreferences) => {
    const target = await deps.lookupSticker(raw)
    if (!target.can_bind) throw new Error(target.block_reason ?? 'На этот заказ ЧЗ внести нельзя')
    const attempt = deps.claim(raw, preferences, true)
    const result = explicitServerModes(attempt.preferences)
      ? await deps.select(raw, attempt.key, attempt.preferences, target.order_id)
      : localSelection(attempt.key, target)
    if (result.order_id !== target.order_id) throw new Error('Сервер вернул другой заказ.')
    deps.remember(raw, result)
    return { result, attempt, explicit: true }
  }
  /** Product barcode first (the main path), then the order sticker, then a direct KIZ copy. */
  const selectNew = async (raw: string) => {
    const preferences = deps.preferences()
    // A sticker (or re-selected) attempt saved before a reload resumes its own
    // explicit selection with the same key: the same scan, the same print keys.
    const saved = deps.attempt?.(raw)
    if (saved?.explicit) {
      if (saved.orderId && explicitServerModes(saved.preferences)) {
        const result = await deps.select(raw, saved.key, saved.preferences, saved.orderId)
        deps.remember(raw, result)
        return { result, attempt: saved, explicit: true }
      }
      return selectBySticker(raw, preferences)
    }
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
  /** After «Назад» on a KIZ scan the order is selected again with fresh keys (new scan id). */
  const reselect = async (step: PackingScanStep) => {
    const selectStep = history.findLast((one) => one.kind === 'select' && one.result.scan_id === step.result.scan_id)
    if (!selectStep || pending) return
    deps.complete(step.barcode)
    const attempt = deps.claim(step.barcode, step.preferences, true)
    const result = isLocalPackingSelection(step.result)
      ? localSelection(attempt.key, step.result.binding_target!)
      : await deps.select(step.barcode, attempt.key, attempt.preferences, step.result.order_id)
    deps.remember(step.barcode, result)
    // The QR of this order is already on paper; the next KIZ scan does not print it again.
    deps.markQrDone?.(step.barcode)
    pending = startPending(step.barcode, result, { ...attempt, qrDone: true }, true, true, false)
    pending.step = selectStep
    selectStep.result = result
    selectStep.explicit = true
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
    canCancel: () => packingSerialBusy() || pending !== null,
    lastStep: () => history.at(-1)?.seq ?? null,
    async undo() {
      const step = history.at(-1)
      if (!step) return null
      const holdsSelection = pending?.result.scan_id === step.result.scan_id
      let warning: string | null
      try {
        // Every undone step frees its selection; a KIZ step re-selects with fresh keys below.
        warning = await deps.undo(step, true)
      } catch (cause) {
        if (cause instanceof FbsApiError && UNDO_FINAL_CODES.includes(cause.code)) dropStep(step)
        deps.changed()
        throw cause
      }
      dropStep(step)
      if (step.kind === 'kiz') {
        if (holdsSelection) pending = null
        // The KIZ scan is undone: the order waits for its KIZ again under a fresh selection.
        await reselect(step)
      } else {
        if (holdsSelection) pending = null
        deps.complete(step.barcode)
      }
      deps.changed()
      return warning
    },
    async cancel() {
      if (!pending) return false
      const current = pending
      if (!isLocalPackingSelection(current.result)) await deps.release(current.result)
      // The released selection is no longer a step of the history (P1-08).
      for (const one of [...history]) {
        if (one.kind === 'select' && one.result.scan_id === current.result.scan_id) dropStep(one)
      }
      if (pending === current) pending = null
      deps.complete(current.barcode)
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
      let boundSaved = false
      try {
        if (!pending) {
          const attempt = deps.claim(barcode, deps.preferences(), true)
          let result: FbsScanAutoPrintResult
          if (explicitServerModes(attempt.preferences)) {
            result = await deps.select(barcode, attempt.key, attempt.preferences, orderId)
          } else {
            if (!target) throw new Error('Заказ строки не найден.')
            result = localSelection(attempt.key, target)
          }
          if (result.order_id !== orderId) throw new Error('Сервер вернул другой заказ.')
          deps.remember(barcode, result)
          pending = startPending(barcode, result, attempt, true, true, false)
          deps.changed()
        }
        // R10, R18: the row's KIZ replaces its code at once, without any dialog.
        await bindKiz(pending, raw, true, 'row')
        boundSaved = true
        retryImage(pending)
        await finish()
      } catch (cause) {
        // A failed row scan never captures the following ordinary scans.
        if (pending?.barcode === barcode) pending = null
        // After the KIZ was saved the same attempt keeps its print keys for the
        // next scan of this row (P0-10); a refused bind starts afresh.
        if (!boundSaved) deps.complete(barcode)
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
          const attempt = deps.claim(raw, current.preferences, current.explicit)
          const recovered = await deps.select(raw, attempt.key, attempt.preferences,
            current.explicit ? current.result.order_id : undefined)
          if (recovered.scan_id !== current.result.scan_id || recovered.order_id !== current.result.order_id) {
            throw new Error('Сервер вернул другой заказ для незавершённого скана.')
          }
          if (!['available', 'started'].includes(recovered.reprint_recovery?.status ?? '')) {
            throw new Error('Товар уже выбран. Сканируйте его Честный знак.')
          }
          current.needsKiz = false
          current.bound = true
          deps.changed()
        } else if (current.needsKiz) {
          // R18: an existing KIZ of the selected order is replaced without a dialog.
          await bindKiz(current, raw, false, 'kiz')
        } else if (current.refresh) {
          // The same scan id asks the server for the pool KIZ again.
          const attempt = deps.claim(raw, current.preferences, current.explicit)
          const refreshed = await deps.select(raw, attempt.key, attempt.preferences)
          if (refreshed.scan_id !== current.result.scan_id || refreshed.order_id !== current.result.order_id) {
            throw new Error('Сервер вернул другой заказ для незавершённого скана.')
          }
          current.result = refreshed
          current.refresh = false
          if (current.step) {
            current.step.result = refreshed
            current.step.kiz = poolKizOf(refreshed) ?? current.step.kiz
          }
        }
        retryImage(current)
        await finish()
        return
      }
      const selected = await selectNew(raw)
      if (!selected) return
      const { result, attempt, explicit } = selected
      if (deps.active?.() === false) return
      const recoveryStatus = result.reprint_recovery?.status
      const bound = recoveryStatus === 'available' || recoveryStatus === 'started'
      // «Печатать ЧЗ» takes the KIZ from the pool; otherwise a KIZ product waits for its scan.
      const needsKiz = !(attempt.preferences.printChz && !explicit) && requiresKiz(result) && !bound
      pending = startPending(raw, result, attempt, explicit, needsKiz, bound)
      // A pool KIZ is bound by the server together with this selection (R7).
      pushStep('select', pending, explicit ? null : poolKizOf(result))
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
  const send = (imageDataUrl: string, idempotencyKey: string, sizeId: LabelSizeId) => {
    const size = resolveLabelSize(sizeId)
    return dispatchPreparedQrInKiosk({ imageDataUrl, idempotencyKey, widthMm: size.widthMm, heightMm: size.heightMm })
  }
  const toAttempt = (raw: string): PackingAttempt | null => {
    const saved = peekFbsPendingProductScan(token, storageId, raw)
    return saved ? {
      key: saved.idempotencyKey, preferences: saved.preferences,
      labelSizeId: resolveLabelSize(saved.labelSizeId as LabelSizeId | undefined).id,
      explicit: saved.explicit === true, orderId: saved.orderId, qrDone: saved.qrStarted,
    } : null
  }
  return {
    active,
    preferences,
    claim: (raw, snapshot, explicit = false) => {
      const attempt = claimFbsPendingProductScan(token, storageId, raw, snapshot, createFbsIdempotencyKey)
      let dirty = false
      // Capture the operator's box before the request: an uncertain selection
      // and a later remount must never substitute the newly opened box.
      if (attempt.packingBoxId === undefined) { attempt.packingBoxId = currentBox(); dirty = true }
      // The label size is frozen for every label (and every retry) of this attempt.
      if (!attempt.labelSizeId) { attempt.labelSizeId = loadLabelSizeId(); dirty = true }
      if (explicit && !attempt.explicit) { attempt.explicit = true; dirty = true }
      if (dirty) updateFbsPendingProductScan(token, storageId, attempt)
      return toAttempt(raw)!
    },
    attempt: toAttempt,
    markQrDone: (raw) => {
      const saved = peekFbsPendingProductScan(token, storageId, raw)
      if (!saved || saved.qrStarted) return
      saved.qrStarted = true
      updateFbsPendingProductScan(token, storageId, saved)
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
        if (!orderId && cause instanceof FbsApiError && ['scan_product_not_found', 'scan_product_exhausted'].includes(cause.code)) {
          completeFbsPendingProductScan(token, storageId, barcode)
        }
        throw cause
      }
    },
    lookupSticker: (raw) => lookupFbsOrderBySticker(token, authHeaders, supplyId, raw),
    release: (result) => cancelFbsScanAutoPrintSelection(token, authHeaders, supplyId, result.scan_id),
    directReprint: async (raw) => {
      // The request identity survives a reload: a lost answer never makes a second copy (P0-09).
      const storageKey = `kiz-copy:${raw}`
      const saved = claimFbsPendingProductScan(token, storageId, storageKey,
        { printQr: false, printChz: false, reprintChz: true }, createFbsIdempotencyKey)
      if (!saved.labelSizeId) {
        saved.labelSizeId = loadLabelSizeId()
        updateFbsPendingProductScan(token, storageId, saved)
      }
      let row
      try { row = await saveFbsDirectKizReprint(token, authHeaders, supplyId, raw, saved.idempotencyKey) }
      catch (cause) {
        if (cause instanceof FbsApiError && cause.code === 'not_a_kiz') completeFbsPendingProductScan(token, storageId, storageKey)
        throw cause
      }
      const printKey = `kiz-copy:${row.id}`
      const sizeId = resolveLabelSize(saved.labelSizeId as LabelSizeId).id
      await startClaimedAutomaticPrint(createFbsIdempotencyKey(), async () => {
        await send(await renderCzLabelPng({ cis: row.kiz }, resolveLabelSize(sizeId)), printKey, sizeId)
      }, {
        claim: async (attemptKey) => {
          const claim = await claimFbsDirectKizPrint(token, authHeaders, supplyId, row.id, attemptKey)
          return { claimed: claim.claimed, started: Boolean(claim.row.print_started_at) }
        },
        markStarted: async () => {
          const marked = await markFbsDirectKizPrintStarted(token, authHeaders, supplyId, row.id)
          return { claimed: false, started: Boolean(marked.print_started_at) }
        },
        releaseClaim: (attemptKey) => releaseFbsDirectKizPrintClaim(token, authHeaders, supplyId, row.id, attemptKey),
      })
      completeFbsPendingProductScan(token, storageId, storageKey)
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
      if (outcome?.status !== 'ok') {
        // The server answered: an outcome other than «pending confirmation» saved nothing.
        if (outcome?.code === 'wb_pending_confirmation') throw new Error(outcome.message ?? 'Честный знак ждёт подтверждения WB.')
        throw new PackingBindRejectedError(outcome?.message ?? 'Честный знак не сохранён.')
      }
      const bound = outcome.bound_kiz ?? raw
      onBound(result.order_id, bound)
      refreshed()
      return bound
    },
    print: async (result, imageDataUrl, sizeId) => {
      await startClaimedAutomaticPrint(result.scan_id,
        () => send(imageDataUrl, result.scan_id, sizeId), {
          claim: (key) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          markStarted: (key) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          // Preserve ownership after an uncertain print dispatch. The exact same
          // scan UUID lets the print transport reconcile a retry; it must never
          // create a new print intent or give this order to another scan.
          releaseClaim: async () => undefined,
        })
    },
    printChz: async (result, sizeId) => {
      const code = result.printed_codes[0]
      if (!code) throw new Error('ЧЗ выбранной единицы не подготовлен.')
      const key = `${result.scan_id}:chz`
      await startClaimedAutomaticPrint(key, async () => {
        const image = await renderCzLabelPng(
          { cis: code.cis_code, codeId: code.id, hasLabelArtifact: code.has_label_artifact }, resolveLabelSize(sizeId), token)
        await send(image, key, sizeId)
      }, {
        claim: (attemptKey) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        // Same rule as QR: WMS Print reconciles a retry of this key; no new intent.
        releaseClaim: async () => undefined,
      })
    },
    printCopy: async (result, sizeId) => {
      const key = `${result.scan_id}:copy`
      await startClaimedAutomaticPrint<FbsScanAutoPrintReprintClaim>(key, async (claim) => {
        if (!claim.kiz) throw new Error('Сервер не подтвердил канонический ЧЗ для перепечати.')
        await send(await renderCzLabelPng({ cis: claim.kiz }, resolveLabelSize(sizeId)), key, sizeId)
      }, {
        claim: (attemptKey) => claimFbsScanAutoPrintReprint(token, authHeaders, supplyId, result.scan_id, attemptKey),
        markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
        // The same attempt key re-claims its own slot on the server; WMS Print
        // deduplicates the job by its key, so a retry never prints a second copy.
        releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(token, authHeaders, supplyId, result.scan_id, 'chz', attemptKey),
      })
    },
    pack: async (result, explicit, barcode, step) => {
      const current = await ensureSupplyStarted()
      // A sticker or row scan of an already packed order must not pack a second unit.
      if (explicit && current.orders.some((order) => order.id === result.order_id && order.pack.status === 'packed')) return
      const taskId = current.supply.packaging_task_id
      if (!taskId) throw new Error('Задание упаковки ещё не создано.')
      const task = await request(`/operations/packaging-tasks/${taskId}`) as PackagingTask
      const order = current.orders.find((row) => row.id === result.order_id)
      const line = task.lines.find((row) => row.product_id === order?.product.id)
      if (!line) throw new Error('Не найдена строка упаковки выбранного заказа.')
      // Intent before the request: a lost answer may still have packed the unit.
      if (step) step.packKey = packingScanPackKey(result)
      await request(`/operations/packaging-tasks/${taskId}/lines/${line.id}/pack`, { method: 'POST', body: JSON.stringify({
        quantity: 1, order_id: result.order_id, idempotency_key: packingScanPackKey(result),
      }) })
      const boxId = scanBoxes.get(result.scan_id) ?? peekFbsPendingProductScan(token, storageId, barcode)?.packingBoxId ?? null
      if (boxId && !current.boxes.some((box) => box.assigned_order_ids.includes(result.order_id))) {
        if (step) step.boxId = boxId
        await assignFbsPackingBoxOrders(token, authHeaders, supplyId, boxId, [result.order_id])
      }
    },
    undo: async (step, releaseSelection) => {
      const local = isLocalPackingSelection(step.result)
      const release = releaseSelection && !local
      let warning: string | null = null
      if (step.kiz || step.packKey || step.boxId || release) {
        const answer = await undoFbsPackingScan(token, authHeaders, supplyId, {
          order_id: step.result.order_id,
          scan_id: local ? null : step.result.scan_id,
          pack_idempotency_key: step.packKey,
          box_id: step.boxId,
          release_selection: release,
          kiz: step.kiz,
        })
        warning = answer.warning
      }
      refreshed()
      return warning
    },
  }
}
