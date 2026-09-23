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
const PENDING_ATTEMPT_TTL_MS = 12 * 60 * 60 * 1000

export type FbsPendingProductScanAttempt = {
  barcode: string
  idempotencyKey: string
  preferences: FbsScanPrintPreferences
  createdAt: number
  scanId?: string
  orderId?: string
  qrStarted: boolean
  chzStarted: boolean
}

type TokenClaims = { sub?: unknown; tenant_id?: unknown }

function tokenIdentity(token: string): { tenant: string; user: string } {
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

function readPendingAttempts(token: string, supplyId: string): FbsPendingProductScanAttempt[] {
  try {
    const raw = window.localStorage.getItem(fbsPendingProductScanStorageKey(token, supplyId))
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    const now = Date.now()
    return parsed.flatMap((value): FbsPendingProductScanAttempt[] => {
      if (!value || typeof value !== 'object') return []
      const row = value as Partial<FbsPendingProductScanAttempt>
      const preferences = normalizePreferences(row.preferences)
      if (
        typeof row.barcode !== 'string'
        || typeof row.idempotencyKey !== 'string'
        || typeof row.createdAt !== 'number'
        || !preferences
        || now - row.createdAt > PENDING_ATTEMPT_TTL_MS
      ) return []
      return [{
        barcode: row.barcode,
        idempotencyKey: row.idempotencyKey,
        preferences,
        createdAt: row.createdAt,
        scanId: typeof row.scanId === 'string' ? row.scanId : undefined,
        orderId: typeof row.orderId === 'string' ? row.orderId : undefined,
        qrStarted: row.qrStarted === true,
        chzStarted: row.chzStarted === true,
      }]
    })
  } catch {
    return []
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
    // Server idempotency remains authoritative when workstation storage is unavailable.
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
): FbsPendingProductScanAttempt {
  const attempts = readPendingAttempts(token, supplyId)
  const existing = attempts.find((attempt) => attempt.barcode === barcode)
  if (existing) {
    writePendingAttempts(token, supplyId, attempts)
    return existing
  }
  const created: FbsPendingProductScanAttempt = {
    barcode,
    idempotencyKey: createId(),
    preferences: { ...preferences },
    createdAt: Date.now(),
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
): FbsPendingProductScanAttempt | null {
  const attempts = readPendingAttempts(token, supplyId)
  writePendingAttempts(token, supplyId, attempts)
  return attempts.find((attempt) => attempt.barcode === barcode) ?? null
}

export function updateFbsPendingProductScan(
  token: string,
  supplyId: string,
  attempt: FbsPendingProductScanAttempt,
): void {
  const attempts = readPendingAttempts(token, supplyId)
  const next = attempts.filter((item) => item.barcode !== attempt.barcode)
  writePendingAttempts(token, supplyId, [...next, attempt])
}

export function completeFbsPendingProductScan(
  token: string,
  supplyId: string,
  barcode: string,
): void {
  writePendingAttempts(
    token,
    supplyId,
    readPendingAttempts(token, supplyId).filter((attempt) => attempt.barcode !== barcode),
  )
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
