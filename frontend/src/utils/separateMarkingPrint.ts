import { useSyncExternalStore } from 'react'

/**
 * Флаг тенанта «Раздельная печать ЧЗ и ШК ВБ» (tenants.separate_marking_print_enabled).
 * Модуль-стор, чтобы не протаскивать проп через все места, открывающие модалку печати:
 * App.tsx заполняет его из /auth/me, FfSettingsScreen обновляет при переключении,
 * MarkingPrintDialog читает хуком.
 */

let enabled = false
const listeners = new Set<() => void>()

export function setSeparateMarkingPrintEnabled(value: boolean): void {
  if (value === enabled) {
    return
  }
  enabled = value
  listeners.forEach((listener) => listener())
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
