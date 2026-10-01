import { packingScanLocks } from './fbsPackingScanLocks'
import { apiUrl } from '../../api'
import { dispatchDurableQr, prepareDurableQr, restoreDurableQr, type DirectQrContext } from '../../utils/durableDirectQr'
import { loadLabelSizeId, resolveLabelSize } from '../../utils/labelSize'
import { startClaimedAutomaticPrint } from './fbsKizAutoReprint'
import {
  claimFbsPendingProductScan, completeFbsPendingProductScan, peekFbsPendingProductScan,
  updateFbsPendingProductScan, tokenIdentity, readPendingAttempts, fbsPendingProductScanStorageKey,
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
  hasSavedAttempt: (raw: string) => boolean | Promise<boolean>
  view: () => PackingScanView
}
export type PackingScanDeps = {
  active?: () => boolean
  select: (barcode: string, key: string) => Promise<FbsScanAutoPrintResult>
  preload: (result: FbsScanAutoPrintResult) => Promise<string>
  bind: (result: FbsScanAutoPrintResult, raw: string) => Promise<void>
  print: (result: FbsScanAutoPrintResult, image: string) => Promise<void>
  pack: (result: FbsScanAutoPrintResult) => Promise<void>
  claim: (raw: string) => string | Promise<string>
  saved: (raw: string) => boolean | Promise<boolean>
  pendingBarcode?: () => string | undefined | Promise<string | undefined>
  exclusive?: (action: () => Promise<void>) => Promise<void>
  remember: (raw: string, result: FbsScanAutoPrintResult) => void | Promise<void>
  complete: (raw: string) => void | Promise<void>
  changed: () => void
}

/** Resume an uncertain selection first, then continue through the remaining supplies. */
export async function routePackingScan(controllers: PackingScanController[], raw: string): Promise<void> {
  const pending = controllers.find((one) => one.hasPending())
  if (pending) return pending.scan(raw)
  let saved: PackingScanController | undefined
  for (const controller of controllers) { if (await controller.hasSavedAttempt(raw)) { saved = controller; break } }
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
    await deps.complete(current.barcode)
    pending = null
    deps.changed()
  }
  return {
    hasPending: () => pending !== null,
    hasSavedAttempt: async (raw) => Boolean(await deps.pendingBarcode?.()) || await deps.saved(raw),
    view: () => pending ? {
      orderId: pending.result.order_id,
      name: pending.result.binding_target?.product.name ?? `WB № ${pending.result.wb_order_id}`,
      needsKiz: pending.needsKiz,
    } : null,
    async scan(raw) {
      const run = async () => {
      if (deps.active?.() === false) return
      if (pending) {
        if (!pending.needsKiz && raw !== pending.barcode) {
          throw new Error(`Не завершена упаковка ${pending.result.binding_target?.product.name ?? `заказа WB № ${pending.result.wb_order_id}`}. Повторите его штрихкод ${pending.barcode}.`)
        }
        if (pending.needsKiz && raw === pending.barcode) {
          const recovered = await deps.select(raw, await deps.claim(raw))
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
      const savedBarcode = await deps.pendingBarcode?.()
      if (savedBarcode && savedBarcode !== raw) throw new Error(`Есть незавершённая попытка упаковки. Повторите её штрихкод ${savedBarcode}, чтобы восстановить исходный заказ.`)
      const result = await deps.select(raw, await deps.claim(raw))
      await deps.remember(raw, result)
      if (deps.active?.() === false) return
      pending = {
        barcode: raw, result, image: deps.preload(result),
        needsKiz: result.requires_honest_sign && result.reprint_recovery?.status !== 'available',
      }
      // Preload runs while the operator scans KIZ; consume rejection until finish.
      void pending.image.catch(() => undefined)
      deps.changed()
      if (!pending.needsKiz) await finish()
      }
      if (deps.exclusive) await deps.exclusive(run)
      else await run()
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
  locks: typeof packingScanLocks = packingScanLocks,
): PackingScanDeps {
  const supplyId = workspace().supply.id
  const scanBoxes = new Map<string, string | null>()
  const scanBarcodes = new Map<string, string>()
  const contextFor = (result: FbsScanAutoPrintResult): DirectQrContext => {
    const identity = tokenIdentity(token)
    const barcode = scanBarcodes.get(result.scan_id)
    if (!barcode) throw new Error('Не найден исходный штрихкод попытки печати. Повторите скан товара.')
    return { tenantId: identity.tenant, userId: identity.user, supplyId, orderId: result.order_id,
      scanId: result.scan_id, barcode, marketplace: 'wildberries', wbOrderId: result.wb_order_id }
  }
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
  const scope = fbsPendingProductScanStorageKey(token, storageId)
  const stateLock = <T>(action: () => Promise<T>) => locks().run(`${scope}:state`, action)
  const recoverable = async () => {
    const ownerId = await locks().owner()
    const attempts = readPendingAttempts(token, storageId)
    const own = attempts.filter((attempt) => attempt.ownerId === ownerId)
    const inactive = []
    for (const attempt of attempts) {
      if (attempt.ownerId !== ownerId && (!attempt.ownerId || !await locks().active(attempt.ownerId))) inactive.push(attempt)
    }
    return [...own, ...inactive]
  }
  const ownAttempt = async (raw: string) => peekFbsPendingProductScan(token, storageId, raw, await locks().owner())
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
    exclusive: (action) => locks().run(fbsPendingProductScanStorageKey(token, supplyId), action),
    pendingBarcode: async () => (await recoverable())[0]?.barcode,
    claim: (raw) => stateLock(async () => {
      const ownerId = await locks().owner()
      const original = (await recoverable()).find((attempt) => attempt.barcode === raw)
      if (original && original.ownerId !== ownerId) {
        original.ownerId = ownerId
        updateFbsPendingProductScan(token, storageId, original)
      }
      const attempt = original ?? claimFbsPendingProductScan(token, storageId, raw,
        { printQr: true, printChz: false, reprintChz: false }, createFbsIdempotencyKey, ownerId)
      if (attempt.packingBoxId === undefined) {
        attempt.packingBoxId = currentBox()
        updateFbsPendingProductScan(token, storageId, attempt)
      }
      return attempt.idempotencyKey
    }),
    saved: async (raw) => (await recoverable()).some((attempt) => attempt.barcode === raw),
    remember: (raw, result) => stateLock(async () => {
      const attempt = await ownAttempt(raw)
      if (!attempt) throw new Error('Исходная попытка скана не принадлежит этой вкладке. Заказ не завершён.')
      if ((attempt.scanId && attempt.scanId !== result.scan_id) || (attempt.orderId && attempt.orderId !== result.order_id)) {
        throw new Error('Сервер вернул другой заказ для незавершённого скана.')
      }
      attempt.scanId = result.scan_id
      attempt.orderId = result.order_id
      updateFbsPendingProductScan(token, storageId, attempt)
      onSelected(result.order_id)
    }),
    complete: (raw) => stateLock(async () => {
      completeFbsPendingProductScan(token, storageId, raw, await locks().owner())
      refreshed()
    }),
    changed,
    select: async (barcode, idempotency_key) => {
      try {
        const attempt = await ownAttempt(barcode)
        if (!attempt || attempt.idempotencyKey !== idempotency_key) throw new Error('Исходный ключ скана не сохранён за этой вкладкой. Новый заказ не выбран.')
        const boxId = attempt.packingBoxId ?? null
        const selected = await scanFbsProductForAutoPrint(token, authHeaders, supplyId, {
          barcode, idempotency_key, print_qr: true, print_chz: false, reprint_chz: false, await_honest_sign: true,
        })
        scanBoxes.set(selected.scan_id, boxId)
        scanBarcodes.set(selected.scan_id, barcode)
        return selected
      } catch (cause) {
        if (cause instanceof FbsApiError && ['scan_product_not_found', 'scan_product_exhausted'].includes(cause.code)) {
          const saved = await ownAttempt(barcode)
          if (saved?.scanId) throw new Error('Не удалось восстановить исходный заказ незавершённой печати. Повторный выбор другого заказа остановлен.')
          await stateLock(async () => completeFbsPendingProductScan(token, storageId, barcode, await locks().owner()))
        }
        throw cause
      }
    },
    preload: async (result) => {
      const context = contextFor(result)
      const saved = await restoreDurableQr(result.scan_id, context)
      if (saved) return saved.input.imageDataUrl
      const size = resolveLabelSize(loadLabelSizeId())
      if (!result.qr_asset?.preview_url) throw new Error('Стикер QR заказа не получен.')
      const response = await fetch(resolveFbsAssetUrl(result.qr_asset.preview_url), { headers: authHeaders(token) })
      if (!response.ok) throw new Error('Не удалось загрузить стикер заказа.')
      const blob = await response.blob()
      const imageDataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onerror = () => reject(new Error('Не удалось прочитать стикер заказа.'))
        reader.onload = () => resolve(String(reader.result))
        reader.readAsDataURL(blob)
      })
      await prepareDurableQr({ imageDataUrl, idempotencyKey: result.scan_id, widthMm: size.widthMm, heightMm: size.heightMm, context })
      return imageDataUrl
    },
    bind: async (result, raw) => {
      await validateFbsKiz(token, authHeaders, result.order_id, raw)
      // The ordinary supply screen starts work before KIZ binding. The unified
      // screen has no Start button, so preserve the same server prerequisite here.
      await ensureSupplyStarted()
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
      const saved = await restoreDurableQr(result.scan_id, contextFor(result))
      if (!saved || saved.input.imageDataUrl !== imageDataUrl) throw new Error('Исходная этикетка не сохранена. Повторите штрихкод товара.')
      const dispatch = () => dispatchDurableQr(saved.input)
      await startClaimedAutomaticPrint(result.scan_id, dispatch, {
          reconcileStarted: () => dispatchDurableQr(saved.input, undefined, undefined, true),
          claim: (key) => claimFbsScanAutoPrintTarget(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          markStarted: (key) => markFbsScanAutoPrintTargetStarted(token, authHeaders, supplyId, result.scan_id, 'qr', key),
          // Preserve ownership after an uncertain print dispatch. The exact same
          // scan UUID lets the print transport reconcile a retry; it must never
          // create a new print intent or give this order to another scan.
          releaseClaim: async () => undefined,
        })
    },
    pack: async (result) => {
      const current = await ensureSupplyStarted()
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
