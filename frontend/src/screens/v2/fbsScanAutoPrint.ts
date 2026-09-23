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
}

const PREFERENCE_PREFIX = 'wms:fbs:scan-auto-print'

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
