/**
 * Единый источник размеров этикетки для всех модалок печати.
 * Дефолт 58×40 совпадает с ранее «зашитым» физическим размером термоэтикетки.
 */

export type LabelSizeId = '58x40' | '60x80' | '60x40' | '70x120'

export type LabelSize = {
  id: LabelSizeId
  /** Подпись для выпадающего списка, напр. «58 × 40 мм». */
  label: string
  widthMm: number
  heightMm: number
}

export const LABEL_SIZES: LabelSize[] = [
  { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
  { id: '60x80', label: '60 × 80 мм', widthMm: 60, heightMm: 80 },
  { id: '60x40', label: '60 × 40 мм', widthMm: 60, heightMm: 40 },
  { id: '70x120', label: '70 × 120 мм', widthMm: 70, heightMm: 120 },
]

/** Дефолт — как было зашито в CSS печати до появления выбора. */
export const DEFAULT_LABEL_SIZE_ID: LabelSizeId = '58x40'

export const DEFAULT_LABEL_SIZE: LabelSize = LABEL_SIZES[0]!

export function resolveLabelSize(id: LabelSizeId | null | undefined): LabelSize {
  return LABEL_SIZES.find((size) => size.id === id) ?? DEFAULT_LABEL_SIZE
}

const STORAGE_KEY = 'wms.print.labelSizeId'

function isLabelSizeId(value: unknown): value is LabelSizeId {
  return typeof value === 'string' && LABEL_SIZES.some((size) => size.id === value)
}

/** Последний выбранный пользователем размер (или дефолт). Безопасно в тестах/SSR. */
export function loadLabelSizeId(): LabelSizeId {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (isLabelSizeId(raw)) {
      return raw
    }
  } catch {
    // localStorage недоступен — используем дефолт
  }
  return DEFAULT_LABEL_SIZE_ID
}

export function saveLabelSizeId(id: LabelSizeId): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // localStorage недоступен — молча пропускаем запоминание
  }
}
