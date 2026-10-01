import { dispatchDurableQr, prepareDurableQr, restoreDurableQr, type DirectQrContext } from '../../utils/durableDirectQr'
import { loadLabelSizeId, resolveLabelSize } from '../../utils/labelSize'
import { packingScanLocks } from './fbsPackingScanLocks'
import { resolveFbsAssetUrl, type FbsPrintAsset } from './fbsApi'
import {
  buildWbOrderQrLabelHtml,
  printTapeSections,
} from '../../utils/printMarkingCodeLabel'

export type FbsScanPrintPreferences = {
  printQr: boolean
  printChz: boolean
  reprintChz: boolean
}

export type FbsProductScanPrintPlan = {
  printQr: boolean
  printChz: boolean
  reprintChz: boolean
}

const PREFERENCE_PREFIX = 'wms:fbs:scan-auto-print'
const PENDING_ATTEMPT_PREFIX = 'wms:fbs:scan-auto-print:pending'

export type FbsPendingProductScanAttempt = {
  barcode: string
  idempotencyKey: string
  preferences: FbsScanPrintPreferences
  createdAt: number
  ownerId?: string
  scanId?: string
  orderId?: string
  packingBoxId?: string | null
  qrStarted: boolean
  chzStarted: boolean
}

type TokenClaims = { sub?: unknown; tenant_id?: unknown }

export function tokenIdentity(token: string): { tenant: string; user: string } {
  try {
    const payload = token.split('.')[1]
    if (!payload) throw new Error('token payload is absent')
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as TokenClaims
    return {
      tenant: typeof claims.tenant_id === 'string' && claims.tenant_id ? claims.tenant_id : 'unknown-tenant',
      user: typeof claims.sub === 'string' && claims.sub ? claims.sub : 'unknown-user',
    }
  } catch {
    // A malformed identity must never inherit an enabled printer setting.
    return { tenant: 'unknown-tenant', user: 'unknown-user' }
  }
}

export function fbsScanPrintPreferencesStorageKey(token: string): string {
  const identity = tokenIdentity(token)
  return `${PREFERENCE_PREFIX}:${identity.tenant}:${identity.user}`
}

export function fbsPendingProductScanStorageKey(token: string, supplyId: string): string {
  const identity = tokenIdentity(token)
  return `${PENDING_ATTEMPT_PREFIX}:${identity.tenant}:${identity.user}:${supplyId}`
}

function normalizePreferences(value: unknown): FbsScanPrintPreferences | null {
  if (!value || typeof value !== 'object') return null
  const saved = value as Partial<FbsScanPrintPreferences>
  const printChz = saved.printChz === true
  return {
    printQr: saved.printQr === true,
    printChz,
    reprintChz: !printChz && saved.reprintChz === true,
  }
}

export function readPendingAttempts(token: string, supplyId: string): FbsPendingProductScanAttempt[] {
  try {
    const raw = window.localStorage.getItem(fbsPendingProductScanStorageKey(token, supplyId))
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) throw new Error('Invalid saved attempts')
    return parsed.flatMap((value): FbsPendingProductScanAttempt[] => {
      if (!value || typeof value !== 'object') {
        throw new Error('Invalid saved attempt')
        return []
      }
      const row = value as Partial<FbsPendingProductScanAttempt>
      const preferences = normalizePreferences(row.preferences)
      if (
        typeof row.barcode !== 'string'
        || typeof row.idempotencyKey !== 'string'
        || !row.barcode || !row.idempotencyKey
        || typeof row.createdAt !== 'number' || !Number.isFinite(row.createdAt)
        || !preferences
      ) {
        throw new Error('Invalid saved attempt')
        return []
      }
      return [{
        barcode: row.barcode,
        idempotencyKey: row.idempotencyKey,
        preferences,
        createdAt: row.createdAt,
        ownerId: typeof row.ownerId === 'string' ? row.ownerId : undefined,
        scanId: typeof row.scanId === 'string' ? row.scanId : undefined,
        orderId: typeof row.orderId === 'string' ? row.orderId : undefined,
        packingBoxId: typeof row.packingBoxId === 'string' || row.packingBoxId === null ? row.packingBoxId : undefined,
        qrStarted: row.qrStarted === true,
        chzStarted: row.chzStarted === true,
      }]
    })
  } catch {
    throw new Error('Не удалось прочитать сохранённую попытку скана. Не очищайте данные сайта: исходный заказ нужно восстановить до нового скана.')
  }
}

function writePendingAttempts(
  token: string,
  supplyId: string,
  attempts: FbsPendingProductScanAttempt[],
): void {
  try {
    const key = fbsPendingProductScanStorageKey(token, supplyId)
    if (attempts.length === 0) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, JSON.stringify(attempts))
  } catch {
    throw new Error('Не удалось сохранить попытку скана в браузере. Освободите место или разрешите хранилище и повторите исходный штрихкод.')
  }
}

/**
 * A partial QR+CHZ attempt survives a workspace remount/browser reopen. The
 * original request id and checkbox snapshot stay together until every target
 * was handed to the browser.
 */
export function claimFbsPendingProductScan(
  token: string,
  supplyId: string,
  barcode: string,
  preferences: FbsScanPrintPreferences,
  createId: () => string,
  ownerId?: string,
): FbsPendingProductScanAttempt {
  const attempts = readPendingAttempts(token, supplyId)
  const existing = attempts.find((attempt) => attempt.barcode === barcode && attempt.ownerId === ownerId)
  if (existing) {
    writePendingAttempts(token, supplyId, attempts)
    return existing
  }
  const created: FbsPendingProductScanAttempt = {
    barcode,
    idempotencyKey: createId(),
    preferences: { ...preferences },
    createdAt: Date.now(),
    ownerId,
    qrStarted: false,
    chzStarted: false,
  }
  writePendingAttempts(token, supplyId, [...attempts, created])
  return created
}

export function peekFbsPendingProductScan(
  token: string,
  supplyId: string,
  barcode: string,
  ownerId?: string,
): FbsPendingProductScanAttempt | null {
  const attempts = readPendingAttempts(token, supplyId)
  return attempts.find((attempt) => attempt.barcode === barcode && attempt.ownerId === ownerId) ?? null
}

export function updateFbsPendingProductScan(
  token: string,
  supplyId: string,
  attempt: FbsPendingProductScanAttempt,
): void {
  const attempts = readPendingAttempts(token, supplyId)
  const next = attempts.filter((item) => item.idempotencyKey !== attempt.idempotencyKey)
  writePendingAttempts(token, supplyId, [...next, attempt])
}

export function completeFbsPendingProductScan(
  token: string,
  supplyId: string,
  barcode: string,
  ownerId?: string,
): void {
  writePendingAttempts(
    token,
    supplyId,
    readPendingAttempts(token, supplyId).filter((attempt) => attempt.barcode !== barcode || attempt.ownerId !== ownerId),
  )
}

/**
 * A durable product attempt is complete only after every output captured in
 * its original checkbox snapshot definitely reached the browser print path.
 * The same CHZ flag represents either a newly allocated code or an exact
 * bound-code reprint because those modes are mutually exclusive.
 */
export function fbsPendingProductScanComplete(
  attempt: FbsPendingProductScanAttempt,
): boolean {
  const plan = productScanPrintPlan(attempt.preferences)
  return (
    (!plan.printQr || attempt.qrStarted)
    && (!plan.printChz || attempt.chzStarted)
    && (!plan.reprintChz || attempt.chzStarted)
  )
}

/** Preserve a scanner burst that began while the controlled input was busy. */
export function mergeFbsBufferedHardwareScan(prefix: string, current: string): string {
  return `${prefix}${current}`
}

export function loadFbsScanPrintPreferences(token: string): FbsScanPrintPreferences {
  try {
    const raw = window.localStorage.getItem(fbsScanPrintPreferencesStorageKey(token))
    if (!raw) return { printQr: false, printChz: false, reprintChz: false }
    const saved = JSON.parse(raw) as Partial<FbsScanPrintPreferences>
    const printChz = saved.printChz === true
    return {
      printQr: saved.printQr === true,
      printChz,
      // Fail closed if an old/corrupt value has both mutually exclusive modes.
      reprintChz: !printChz && saved.reprintChz === true,
    }
  } catch {
    return { printQr: false, printChz: false, reprintChz: false }
  }
}

export function saveFbsScanPrintPreferences(
  token: string,
  preferences: FbsScanPrintPreferences,
): void {
  const normalized: FbsScanPrintPreferences = {
    printQr: preferences.printQr,
    printChz: preferences.printChz,
    reprintChz: !preferences.printChz && preferences.reprintChz,
  }
  try {
    window.localStorage.setItem(
      fbsScanPrintPreferencesStorageKey(token),
      JSON.stringify(normalized),
    )
  } catch {
    // Hardened workstations can disable storage; current React state remains valid.
  }
}

/** Six UI modes collapse to the two product-scan outputs sent to the server. */
export function productScanPrintPlan(
  preferences: FbsScanPrintPreferences,
): FbsProductScanPrintPlan {
  return {
    printQr: preferences.printQr,
    // Reprint mode never invents a KIZ from a product barcode.
    printChz: preferences.printChz && !preferences.reprintChz,
    reprintChz: preferences.reprintChz && !preferences.printChz,
  }
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error ?? new Error('Не удалось прочитать стикер заказа.'))
    reader.readAsDataURL(blob)
  })
}

/** Fetch and immediately send one WB order sticker through the silent-print iframe. */
export async function printFbsOrderQrAsset(
  token: string,
  asset: FbsPrintAsset,
): Promise<void> {
  if (asset.status !== 'ready' || !asset.preview_url) {
    throw new Error('Стикер заказа ещё не готов к печати.')
  }
  const response = await fetch(resolveFbsAssetUrl(asset.preview_url), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new Error('Не удалось загрузить стикер заказа для печати.')
  }
  const dataUrl = await blobToDataUrl(await response.blob())
  await printTapeSections([buildWbOrderQrLabelHtml(dataUrl)])
}

/** Call inside the supply flow lock, before selecting any server-side unit. */
export async function claimOwnedFbsPendingProductScan(
  token: string, supplyId: string, barcode: string, preferences: FbsScanPrintPreferences,
  createId: () => string, ownerId: string,
): Promise<FbsPendingProductScanAttempt> {
  const attempts = readPendingAttempts(token, supplyId)
  const own = attempts.find((attempt) => attempt.ownerId === ownerId)
  if (own && own.barcode !== barcode) throw new Error(`Есть незавершённая попытка печати. Повторите её штрихкод ${own.barcode}, чтобы восстановить исходный заказ.`)
  let original = own
  if (!original) {
    for (const attempt of attempts) {
      if (!attempt.ownerId || !await packingScanLocks().active(attempt.ownerId)) { original = attempt; break }
    }
  }
  if (original) {
    if (original.barcode !== barcode) throw new Error(`Есть незавершённая попытка печати. Повторите её штрихкод ${original.barcode}, чтобы восстановить исходный заказ.`)
    original.ownerId = ownerId
    updateFbsPendingProductScan(token, supplyId, original)
    return original
  }
  return claimFbsPendingProductScan(token, supplyId, barcode, preferences, createId, ownerId)
}

/** Ordinary WB only shares QR transport, keeping selection and quantity semantics. */
export async function printFbsDurableOrderQrAsset(
  token: string, asset: FbsPrintAsset, context: DirectQrContext, requireExisting = false,
): Promise<void> {
  let attempt = await restoreDurableQr(context.scanId, context)
  if (!attempt) {
    if (requireExisting) throw new Error('Исходная этикетка не найдена в браузере. Результат прежней отправки нужно сверить в журнале WMS Print; новая копия не отправлена.')
    if (asset.status !== 'ready' || !asset.preview_url) throw new Error('Стикер заказа ещё не готов к печати.')
    const response = await fetch(resolveFbsAssetUrl(asset.preview_url), { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Не удалось загрузить стикер заказа для печати.')
    const imageDataUrl = await blobToDataUrl(await response.blob())
    const size = resolveLabelSize(loadLabelSizeId())
    attempt = await prepareDurableQr({ imageDataUrl, idempotencyKey: context.scanId, widthMm: size.widthMm, heightMm: size.heightMm, context })
  }
  await dispatchDurableQr(attempt.input, undefined, undefined, requireExisting)
}
