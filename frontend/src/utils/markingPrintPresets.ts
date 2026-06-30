import type { PrintLayout, PrintLayoutUnit } from './printTemplate'

export type PrintPresetId = 'pairs' | 'label_cz' | 'cz_only' | 'label_only' | 'custom'

export type PrintPreset = {
  id: PrintPresetId
  label: string
  layout: PrintLayout
}

export const MARKING_PRINT_PRESETS: PrintPreset[] = [
  {
    id: 'pairs',
    label: 'Парами (реком.)',
    layout: { units: [{ block: 'cz', copies: 2 }] },
  },
  {
    id: 'label_cz',
    label: 'ШК ВБ + ЧЗ',
    layout: {
      units: [
        { block: 'label', copies: 1 },
        { block: 'cz', copies: 1 },
      ],
    },
  },
  {
    id: 'cz_only',
    label: 'Только ЧЗ',
    layout: { units: [{ block: 'cz', copies: 1 }] },
  },
  {
    id: 'label_only',
    label: 'Только ШК ВБ',
    layout: { units: [{ block: 'label', copies: 1 }] },
  },
  {
    id: 'custom',
    label: 'Свой шаблон',
    layout: { units: [{ block: 'cz', copies: 1 }] },
  },
]

export type LayoutTapeItem = {
  block: PrintLayoutUnit['block']
  cis: string
  unitIndex: number
}

/** Разворачивает коды в ленту по layout: на каждую единицу — блоки units по порядку. */
export function expandLayoutTape(codes: string[], layout: PrintLayout): LayoutTapeItem[] {
  const units = layout.units.length > 0 ? layout.units : [{ block: 'cz' as const, copies: 1 }]
  const out: LayoutTapeItem[] = []
  for (let i = 0; i < codes.length; i += 1) {
    const cis = codes[i]
    for (const unit of units) {
      const copies = Math.max(1, unit.copies)
      for (let c = 0; c < copies; c += 1) {
        out.push({ block: unit.block, cis, unitIndex: i })
      }
    }
  }
  return out
}

export function blockLabel(block: PrintLayoutUnit['block']): string {
  return block === 'cz' ? 'ЧЗ' : 'ШК ВБ'
}

export type TapeBlock = PrintLayoutUnit['block']

/** Разворачивает layout одной единицы в плоскую ленту блоков. */
export function expandLayoutToTape(layout: PrintLayout): TapeBlock[] {
  const units = layout.units.length > 0 ? layout.units : [{ block: 'cz' as const, copies: 1 }]
  const out: TapeBlock[] = []
  for (const unit of units) {
    const copies = Math.max(1, unit.copies)
    for (let c = 0; c < copies; c += 1) {
      out.push(unit.block)
    }
  }
  return out
}

/** Лента по умолчанию: сначала все ЧЗ, затем все ШК ВБ. */
export function buildDefaultTape(czCount: number, wbCount: number): TapeBlock[] {
  const cz = Math.max(0, Math.min(99, Math.floor(czCount) || 0))
  const wb = Math.max(0, Math.min(99, Math.floor(wbCount) || 0))
  return [...Array(cz).fill('cz' as const), ...Array(wb).fill('label' as const)]
}

/** Сжимает соседние одинаковые блоки в layout.units (порядок сохраняется). */
export function tapeToLayout(tape: TapeBlock[]): PrintLayout {
  if (tape.length < 1) {
    return { units: [{ block: 'cz', copies: 1 }] }
  }
  const units: PrintLayoutUnit[] = []
  for (const block of tape) {
    const last = units[units.length - 1]
    if (last && last.block === block) {
      last.copies += 1
    } else {
      units.push({ block, copies: 1 })
    }
  }
  return { units }
}

export function countTapeBlocksFromTape(tape: TapeBlock[], unitCount: number): number {
  if (unitCount < 1 || tape.length < 1) {
    return 0
  }
  return tape.length * unitCount
}

export type TapePreviewUnit = {
  unitIndex: number
  blocks: string[]
  codeHint: string
}

/** Предпросмотр 2–3 единиц ленты: внутри единицы код одинаковый. */
export function buildTapePreviewUnits(layout: PrintLayout, maxUnits = 3): TapePreviewUnit[] {
  const codeHints = Array.from({ length: maxUnits }, (_, i) => `#${i + 1}`)
  const tape = expandLayoutTape(codeHints, layout)
  const byUnit = new Map<number, string[]>()
  for (const item of tape) {
    const blocks = byUnit.get(item.unitIndex) ?? []
    blocks.push(blockLabel(item.block))
    byUnit.set(item.unitIndex, blocks)
  }
  return [...byUnit.entries()]
    .sort(([a], [b]) => a - b)
    .map(([unitIndex, blocks]) => ({
      unitIndex: unitIndex + 1,
      blocks,
      codeHint: codeHints[unitIndex] ?? `#${unitIndex + 1}`,
    }))
}

export function cloneLayout(layout: PrintLayout): PrintLayout {
  return {
    units: layout.units.map((unit) => ({ ...unit })),
  }
}

/** Умножает копии блоков «ШК ВБ» на «ШК ВБ на каждый товар» (A-002: ЧЗ не умножается). */
export function applyLabelsPerProductToLayout(
  layout: PrintLayout,
  labelsPerProduct: number,
): PrintLayout {
  const lpp = Math.max(1, Math.min(99, Math.floor(labelsPerProduct) || 1))
  return {
    units: layout.units.map((unit) =>
      unit.block === 'label' ? { ...unit, copies: unit.copies * lpp } : { ...unit },
    ),
  }
}

export function countTapeBlocks(
  unitCount: number,
  layout: PrintLayout,
  labelsPerProduct = 1,
): number {
  if (unitCount < 1) {
    return 0
  }
  const codes = Array.from({ length: unitCount }, (_, i) => `#${i + 1}`)
  return expandLayoutTape(codes, applyLabelsPerProductToLayout(layout, labelsPerProduct)).length
}
