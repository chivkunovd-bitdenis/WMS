import type { ObjKind } from './pickStub'

// WMS-686 · подбор отгрузки FBO: то, что экран должен помнить между перерисовками,
// ошибками и сменой вкладок документа, и правило «двойного скана короба».
//
// Это логика без React: её можно проверить без экрана. Всё здесь включается только
// для отгрузки FBO — подбор поставки FBS этих функций не вызывает.

/** Вид подбора FBO: по ячейкам (по умолчанию) или от товара. */
export type FboPickView = 'cells' | 'products'

/** Что оператор успел настроить на экране: вид, раскрытия, выбранный источник. */
export type FboPickUi = {
  view: FboPickView
  /** Ключ источника: ячейка (cell:id) или тара (obj:id); пусто — источник не выбран. */
  source: string | null
  sourceLabel: string | null
  /** Сырая строка, которой выбрали источник: по ней «Забрать короб целиком» находит короб. */
  sourceBarcode: string | null
  /** «По товарам»: раскрытые строки товаров. */
  expanded: string[]
  /** «По ячейкам»: свёрнутые ячейки и короба (по умолчанию всё раскрыто). */
  collapsed: string[]
  /** Строки, под которыми открыт список КИЗ. */
  kizOpen: string[]
}

/** Тара, выбранная сканом, но ещё не встретившаяся среди источников pick-options. */
export type FboScannedContainer = {
  locationId: string
  containerKind: ObjKind
  containerId: string
}

const UI_KEY = 'wms.fbo-pick.ui.v1.'
const CONTAINERS_KEY = 'wms.fbo-pick.containers.v1.'

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === 'string') : []
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

/** Прочитать сохранённое состояние экрана; повреждённая запись не должна ронять экран. */
export function loadFboPickUi(documentId: string): FboPickUi | null {
  const store = storage()
  if (!store || !documentId) return null
  try {
    const raw = store.getItem(UI_KEY + documentId)
    if (!raw) return null
    const data = JSON.parse(raw) as Partial<Record<keyof FboPickUi, unknown>>
    return {
      view: data.view === 'products' ? 'products' : 'cells',
      source: nullableString(data.source),
      sourceLabel: nullableString(data.sourceLabel),
      sourceBarcode: nullableString(data.sourceBarcode),
      expanded: strings(data.expanded),
      collapsed: strings(data.collapsed),
      kizOpen: strings(data.kizOpen),
    }
  } catch {
    return null
  }
}

export function saveFboPickUi(documentId: string, ui: FboPickUi): void {
  const store = storage()
  if (!store || !documentId) return
  try {
    store.setItem(UI_KEY + documentId, JSON.stringify(ui))
  } catch {
    // Память вкладки недоступна или полна — экран работает и без неё.
  }
}

export function loadFboContainers(documentId: string): Map<string, FboScannedContainer> {
  const result = new Map<string, FboScannedContainer>()
  const store = storage()
  if (!store || !documentId) return result
  try {
    const raw = store.getItem(CONTAINERS_KEY + documentId)
    if (!raw) return result
    const entries = JSON.parse(raw) as Array<[unknown, unknown]>
    for (const [key, value] of entries) {
      const one = value as Partial<FboScannedContainer> | null
      if (
        typeof key === 'string' &&
        one &&
        typeof one.locationId === 'string' &&
        typeof one.containerId === 'string' &&
        (one.containerKind === 'pallet' || one.containerKind === 'box' || one.containerKind === 'cargo_place')
      ) {
        result.set(key, {
          locationId: one.locationId,
          containerKind: one.containerKind,
          containerId: one.containerId,
        })
      }
    }
  } catch {
    // Повреждённая запись — как будто её не было.
  }
  return result
}

export function saveFboContainers(documentId: string, containers: Map<string, FboScannedContainer>): void {
  const store = storage()
  if (!store || !documentId) return
  try {
    store.setItem(CONTAINERS_KEY + documentId, JSON.stringify([...containers.entries()]))
  } catch {
    // см. saveFboPickUi
  }
}

/** Окно двойного скана короба: от прихода первого кода до прихода второго. */
export const BOX_PAIR_WINDOW_MS = 2000

type BoxPair = {
  /** Сырая строка кода, которым выбран короб. */
  code: string
  firstAt: number
  lastAt: number
  /** Пара уже сработала (или короб уже перенесён): дальнейшие быстрые сканы глотаем молча. */
  taken: boolean
  sourceKey: string
}

export type BoxScanVerdict =
  /** Второй скан в окне: забрать короб целиком. */
  | 'take'
  /** Третий быстрый скан после переноса: не делать ничего и не показывать ошибку. */
  | 'ignore'
  /** Обычный скан: отправить на сервер как раньше. */
  | 'normal'

/**
 * Правило «двойного скана» (WMS-686 D1.6).
 *
 * Время — момент прихода кода (его записывает onReceived сканера), а не момент,
 * когда дошла очередь до обработки: медленный ответ сервера на первый скан не
 * должен «растягивать» окно. Любой другой код между двумя сканами рвёт пару.
 */
export function createBoxPairTracker(windowMs: number = BOX_PAIR_WINDOW_MS) {
  let pair: BoxPair | null = null
  return {
    /** Пришёл код `code` в момент `at`; `sourceKey` — источник на экране сейчас. */
    arrive(code: string, at: number, sourceKey: string | null): BoxScanVerdict {
      const current = pair
      if (!current || current.code !== code) {
        pair = null
        return 'normal'
      }
      if (current.taken) {
        if (at - current.lastAt <= windowMs) {
          current.lastAt = at
          return 'ignore'
        }
        pair = null
        return 'normal'
      }
      if (at - current.firstAt <= windowMs && sourceKey === current.sourceKey) {
        current.taken = true
        current.lastAt = at
        return 'take'
      }
      pair = null
      return 'normal'
    },
    /** Сервер подтвердил: этим кодом выбран короб — следующий такой же код в окне заберёт его. */
    selected(code: string, at: number, sourceKey: string): void {
      pair = { code, firstAt: at, lastAt: at, taken: false, sourceKey }
    },
    reset(): void {
      pair = null
    },
  }
}

export type BoxPairTracker = ReturnType<typeof createBoxPairTracker>
