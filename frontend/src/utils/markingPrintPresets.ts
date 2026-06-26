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
    label: 'Этикетки + ЧЗ',
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
    label: 'Только этикетки',
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
  return block === 'cz' ? 'ЧЗ' : 'Этикетка'
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
