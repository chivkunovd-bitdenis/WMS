import { useSyncExternalStore } from 'react'
import { apiUrl } from '../api'

/**
 * Флаг тенанта «Раздельная печать ЧЗ и ШК ВБ» (tenants.separate_marking_print_enabled).
 * Модуль-стор, чтобы не протаскивать проп через все места, открывающие модалку печати:
 * App.tsx заполняет его из /auth/me, FfSettingsScreen обновляет при переключении,
 * MarkingPrintDialog читает хуком.
 */

const STORAGE_KEY = 'wms.separateMarkingPrintEnabled'

type MeWithSeparatePrint = {
  separate_marking_print_enabled?: boolean
}

function loadStoredEnabled(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function saveStoredEnabled(value: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false')
  } catch {
    // localStorage недоступен — держим значение только в памяти.
  }
}

let enabled = loadStoredEnabled()
const listeners = new Set<() => void>()

export function setSeparateMarkingPrintEnabled(value: boolean): void {
  saveStoredEnabled(value)
  if (value === enabled) {
    return
  }
  enabled = value
  listeners.forEach((listener) => listener())
}

export async function refreshSeparateMarkingPrintEnabled(token: string): Promise<boolean> {
  const authToken = token.trim()
  if (!authToken) {
    return enabled
  }
  const res = await fetch(apiUrl('/auth/me'), {
    headers: { Authorization: `Bearer ${authToken}` },
  })
  if (!res.ok) {
    return enabled
  }
  const me = (await res.json()) as MeWithSeparatePrint
  const next = me.separate_marking_print_enabled === true
  setSeparateMarkingPrintEnabled(next)
  return next
}

export function isSeparateMarkingPrintEnabled(): boolean {
  return enabled
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useSeparateMarkingPrint(): boolean {
  return useSyncExternalStore(subscribe, isSeparateMarkingPrintEnabled)
}
