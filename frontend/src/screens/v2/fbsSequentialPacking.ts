import { apiUrl } from '../../api'
import { printPreparedQr } from '../../utils/printPreparedQr'
import { loadLabelSizeId, resolveLabelSize } from '../../utils/labelSize'
import { startClaimedAutomaticPrint } from './fbsKizAutoReprint'
import {
  claimFbsPendingProductScan, completeFbsPendingProductScan, peekFbsPendingProductScan,
  updateFbsPendingProductScan,
} from './fbsScanAutoPrint'
import {
  assignFbsPackingBoxOrders, claimFbsScanAutoPrintTarget, commitFbsKiz, createFbsIdempotencyKey,
  markFbsScanAutoPrintTargetStarted,
  resolveFbsAssetUrl, scanFbsProductForAutoPrint, startFbsSupplyWork, validateFbsKiz,
  FbsApiError, type FbsScanAutoPrintResult, type FbsWorkspace,
} from './fbsApi'
import type { PackagingTask } from '../ff/FfPackagingPage'

export type PackingScanView = { orderId: string; name: string; needsKiz: boolean } | null
export type PackingScanController = {
  scan: (raw: string) => Promise<void>
  hasPending: () => boolean
  hasSavedAttempt: (raw: string) => boolean
  view: () => PackingScanView
}
export type PackingScanDeps = {
  active?: () => boolean
  select: (barcode: string, key: string) => Promise<FbsScanAutoPrintResult>
  preload: (result: FbsScanAutoPrintResult) => Promise<string>
  bind: (result: FbsScanAutoPrintResult, raw: string) => Promise<void>
  print: (result: FbsScanAutoPrintResult, image: string) => Promise<void>
  pack: (result: FbsScanAutoPrintResult) => Promise<void>
  claim: (raw: string) => string
  saved: (raw: string) => boolean
  remember: (raw: string, result: FbsScanAutoPrintResult) => void
  complete: (raw: string) => void
  changed: () => void
}

/** Resume an uncertain selection first, then continue through the remaining supplies. */
export async function routePackingScan(controllers: PackingScanController[], raw: string): Promise<void> {
  const pending = controllers.find((one) => one.hasPending())
  if (pending) return pending.scan(raw)
  const saved = controllers.find((one) => one.hasSavedAttempt(raw))
  const ordered = saved ? [saved, ...controllers.filter((one) => one !== saved)] : controllers
  for (const controller of ordered) {
    try { await controller.scan(raw); return }
    catch (cause) {
      if (cause instanceof FbsApiError && ['scan_product_not_found', 'scan_product_exhausted'].includes(cause.code)) continue
      throw cause
    }
  }
  throw new Error('В этой сборке не осталось заказов с таким штрихкодом.')
}

/** One selected order survives binding/printing failures; only success releases it. */
export function createPackingScanController(deps: PackingScanDeps): PackingScanController {
  let pending: { barcode: string; result: FbsScanAutoPrintResult; image: Promise<string>; needsKiz: boolean } | null = null
  const finish = async () => {
    if (!pending) return
    const current = pending
    const image = await current.image
    if (deps.active?.() === false) throw new Error('Упаковка закрыта. Откройте её и повторите скан товара для продолжения.')
    await deps.print(current.result, image)
    await deps.pack(current.result)
    deps.complete(current.barcode)
    pending = null
    deps.changed()
  }
  return {
    hasPending: () => pending !== null,
    hasSavedAttempt: deps.saved,
    view: () => pending ? {
      orderId: pending.result.order_id,
      name: pending.result.binding_target?.product.name ?? `WB № ${pending.result.wb_order_id}`,
      needsKiz: pending.needsKiz,
    } : null,
    async scan(raw) {
      if (deps.active?.() === false) return
      if (pending) {
        if (!pending.needsKiz && raw !== pending.barcode) {
          throw new Error(`Не завершена упаковка ${pending.result.binding_target?.product.name ?? `заказа WB № ${pending.result.wb_order_id}`}. Повторите его штрихкод ${pending.barcode}.`)
        }
        if (pending.needsKiz && raw === pending.barcode) {
          const recovered = await deps.select(raw, deps.claim(raw))
          if (recovered.scan_id !== pending.result.scan_id || recovered.order_id !== pending.result.order_id) {
            throw new Error('Сервер вернул другой заказ для незавершённого скана.')
          }
          if (recovered.reprint_recovery?.status !== 'available') {
            throw new Error('Товар уже выбран. Сканируйте его Честный знак.')
          }
          pending.needsKiz = false
          deps.changed()
        } else if (pending.needsKiz) {
          await deps.bind(pending.result, raw)
          pending.needsKiz = false
          deps.changed()
        }
        // Recover a failed preload on the same order; never reserve its neighbour.
        pending.image = pending.image.catch(() => deps.preload(pending!.result))
        await finish()
        return
      }
      const result = await deps.select(raw, deps.claim(raw))
      deps.remember(raw, result)
      if (deps.active?.() === false) return
      pending = {
        barcode: raw, result, image: deps.preload(result),
        needsKiz: result.requires_honest_sign && result.reprint_recovery?.status !== 'available',
      }
      // Preload runs while the operator scans KIZ; consume rejection until finish.
      void pending.image.catch(() => undefined)
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
): PackingScanDeps {
  const supplyId = workspace().supply.id
  const scanBoxes = new Map<string, string | null>()
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
  return {
    active,
    claim: (raw) => {
      const attempt = claimFbsPendingProductScan(token, storageId, raw,
        { printQr: true, printChz: false, reprintChz: false }, createFbsIdempotencyKey)
      // Capture the operator's box before the request: an uncertain selection
      // and a later remount must never substitute the newly opened box.
      if (attempt.packingBoxId === undefined) {
        attempt.packingBoxId = currentBox()
        updateFbsPendingProductScan(token, storageId, attempt)
      }
      return attempt.idempotencyKey
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
    },
    complete: (raw) => { completeFbsPendingProductScan(token, storageId, raw); refreshed() },
    changed,
    select: async (barcode, idempotency_key) => {
      try {
        const boxId = peekFbsPendingProductScan(token, storageId, barcode)?.packingBoxId ?? null
        const selected = await scanFbsProductForAutoPrint(token, authHeaders, supplyId, {
          barcode, idempotency_key, print_qr: true, print_chz: false, reprint_chz: false, await_honest_sign: true,
        })
        scanBoxes.set(selected.scan_id, boxId)
        return selected
      } catch (cause) {
        if (cause instanceof FbsApiError && ['scan_product_not_found', 'scan_product_exhausted'].includes(cause.code)) {
          completeFbsPendingProductScan(token, storageId, barcode)
        }
        throw cause
      }
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
    bind: async (result, raw) => {
      await validateFbsKiz(token, authHeaders, result.order_id, raw)
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))
      const codeKey = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
      const commit = (confirmed: boolean) => commitFbsKiz(token, authHeaders, [{
        order_id: result.order_id, value: raw, confirmed, scan_auto_print_id: result.scan_id,
      }], `${result.scan_id}:${codeKey}:${confirmed ? 'replace' : 'bind'}`)
      let outcomes = await commit(false)
      let outcome = outcomes.find((item) => item.order_id === result.order_id)
      if (outcome?.code === 'needs_confirmation' && window.confirm('У заказа уже есть Честный знак. Заменить его отсканированным кодом?')) {
        outcomes = await commit(true)
        outcome = outcomes.find((item) => item.order_id === result.order_id)
      }
      if (outcome?.status !== 'ok') throw new Error(outcome?.message ?? 'Честный знак не сохранён.')
      onBound(result.order_id, outcome.bound_kiz ?? raw)
      refreshed()
    },
    print: async (result, imageDataUrl) => {
      const size = resolveLabelSize(loadLabelSizeId())
      await startClaimedAutomaticPrint(result.scan_id,
        () => printPreparedQr({ imageDataUrl, idempotencyKey: result.scan_id, widthMm: size.widthMm, heightMm: size.heightMm }), {
          claim: (key) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          markStarted: (key) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          // Preserve ownership after an uncertain print dispatch. The exact same
          // scan UUID lets the print transport reconcile a retry; it must never
          // create a new print intent or give this order to another scan.
          releaseClaim: async () => undefined,
        })
    },
    pack: async (result) => {
      let current = workspace()
      if (current.supply.id !== supplyId) throw new Error('Поставка изменилась. Повторите скан в исходной поставке.')
      if (!current.supply.packaging_task_id) current = await startFbsSupplyWork(token, authHeaders, supplyId)
      const taskId = current.supply.packaging_task_id
      if (!taskId) throw new Error('Задание упаковки ещё не создано.')
      const task = await request(`/operations/packaging-tasks/${taskId}`) as PackagingTask
      const order = current.orders.find((row) => row.id === result.order_id)
      const line = task.lines.find((row) => row.product_id === order?.product.id)
      if (!line) throw new Error('Не найдена строка упаковки выбранного заказа.')
      await request(`/operations/packaging-tasks/${taskId}/lines/${line.id}/pack`, { method: 'POST', body: JSON.stringify({
        quantity: 1, order_id: result.order_id, idempotency_key: `${result.scan_id}:packed`,
      }) })
      const boxId = scanBoxes.get(result.scan_id)
      if (boxId && !current.boxes.some((box) => box.assigned_order_ids.includes(result.order_id))) {
        await assignFbsPackingBoxOrders(token, authHeaders, supplyId, boxId, [result.order_id])
      }
    },
  }
}
