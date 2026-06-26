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
  const units: TapePreviewUnit[] = []
  for (let i = 0; i < maxUnits; i += 1) {
    const blocks: string[] = []
    for (const unit of layout.units) {
      for (let c = 0; c < unit.copies; c += 1) {
        blocks.push(blockLabel(unit.block))
      }
    }
    units.push({
      unitIndex: i + 1,
      blocks,
      codeHint: `#${i + 1}`,
    })
  }
  return units
}

export function cloneLayout(layout: PrintLayout): PrintLayout {
  return {
    units: layout.units.map((unit) => ({ ...unit })),
  }
}
