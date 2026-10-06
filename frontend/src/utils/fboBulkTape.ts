import type { LabelSize } from './labelSize'
import { labelMm, labelScale } from './printProductThermalLabel'
import {
  buildMarkingTapeSections,
  buildProductLabelSections,
  labelOptionsFromLayout,
  type MarkingTapeUnitInput,
} from './printMarkingCodeLabel'
import type { PrintLayout, PrintLayoutUnit } from './printTemplate'
import type { ProductThermalLabelData } from './printProductThermalLabel'

/**
 * WMS-618: один товар отгрузки — одна и та же `product_id`, пришедшая из
 * нескольких строк задания (несколько ячеек хранения). R6: это один «артикул».
 */
export type FboBulkLineInput = {
  lineId: string
  productId: string
  productName: string
  skuCode: string
  requiresHonestSign: boolean
  qtyNeedPack: number
  productLabel: ProductThermalLabelData | null
}

export type FboBulkGroup = {
  productId: string
  productName: string
  skuCode: string
  productLabel: ProductThermalLabelData | null
  lines: FboBulkLineInput[]
}

/** Группирует строки по product_id в порядке первого появления (R6). */
export function groupFboBulkLinesByProduct(lines: FboBulkLineInput[]): FboBulkGroup[] {
  const byId = new Map<string, FboBulkGroup>()
  const order: string[] = []
  for (const line of lines) {
    const existing = byId.get(line.productId)
    if (existing) {
      existing.lines.push(line)
      continue
    }
    byId.set(line.productId, {
      productId: line.productId,
      productName: line.productName,
      skuCode: line.skuCode,
      productLabel: line.productLabel,
      lines: [line],
    })
    order.push(line.productId)
  }
  return order.map((id) => byId.get(id)!)
}

/** Один HTML-блок — пустая этикетка выбранного размера. */
export function buildFboBulkSeparatorSection(): string {
  return '<section class="label label--fbo-separator" data-testid="fbo-bulk-separator" data-tape-block="separator" aria-hidden="true"></section>'
}

/** CSS для превью пустой этикетки: подпись и штриховая рамка — только в превью. */
export function buildFboBulkPreviewSeparatorStyle(size: LabelSize): string {
  const k = labelScale(size)
  return `
    .label--fbo-separator {
      position: relative;
      background: #fff;
      border: 1.5px dashed rgba(17, 17, 17, 0.45);
    }
    .label--fbo-separator::after {
      content: 'Пустая этикетка';
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: Arial, Helvetica, sans-serif;
      font-size: ${labelMm(2.5 * k.font)};
      color: rgba(17, 17, 17, 0.55);
      font-weight: 700;
      letter-spacing: 0.02em;
    }
  `
}

export type FboBulkIssuedCode = {
  id: string
  cisCode: string
  hasLabelArtifact: boolean
}

/**
 * Единый источник ленты для общей FBO-печати.
 *
 * Используется и для превью (`codesByLineId` отсутствует → стабовые КМ),
 * и для реальной печати (`codesByLineId` из серверного ответа). Из-за этого
 * оператор точно видит, что уйдёт на принтер: разложенные группы, те же
 * копии блоков и те же разделители.
 *
 * - `layout` — то, что выбрано в конструкторе; `cz`-блоки применяются только
 *   к строкам с `requiresHonestSign`, `label`-блоки — ко всем строкам, у
 *   которых есть продуктовый ярлык.
 * - `splitArticles=true` вставляет ровно одну пустую этикетку между каждой
 *   парой соседних непустых товарных групп (ни перед первой, ни после
 *   последней — R5+R7).
 * - `maxUnits` ограничивает общее количество единиц в выдаче (превью режет
 *   длинную ленту до 3 единиц; печать не ограничивает — передаёт `Infinity`).
 */
export type BuildFboBulkTapeOptions = {
  groups: FboBulkGroup[]
  layout: PrintLayout
  labelSize: LabelSize
  splitArticles: boolean
  /** real: Map<lineId, issued codes>; preview: undefined → stub cis */
  codesByLineId?: Map<string, FboBulkIssuedCode[]>
  /** `(index) => cis` — для превью; при `codesByLineId` не используется. */
  previewCis?: (globalIndex: number) => string
  maxUnits?: number
  authToken?: string | null
  signal?: AbortSignal
}

function nonHonestLayout(layout: PrintLayout): PrintLayout {
  // Для строк без ЧЗ CZ-блоки не применяются: товар не маркируемый. Остаются
  // только `label`-блоки с теми же `copies`, что выбрал оператор, — так
  // `wbQty` действует и на не-ЧЗ единицы в смешанной отгрузке.
  const units: PrintLayoutUnit[] = layout.units.filter((unit) => unit.block === 'label')
  return { ...layout, units }
}

function stubUnits(count: number, previewCis: (idx: number) => string, startIndex: number, productLabel: ProductThermalLabelData | null): MarkingTapeUnitInput[] {
  return Array.from({ length: count }, (_, i) => ({
    cis: previewCis(startIndex + i),
    productLabel,
  }))
}

function unitsFromIssuedCodes(
  codes: FboBulkIssuedCode[],
  productLabel: ProductThermalLabelData | null,
): MarkingTapeUnitInput[] {
  return codes.map((code) => ({
    cis: code.cisCode,
    codeId: code.id,
    hasLabelArtifact: code.hasLabelArtifact,
    productLabel,
  }))
}

export async function buildFboBulkTapeSections(
  opts: BuildFboBulkTapeOptions,
): Promise<string[]> {
  const {
    groups,
    layout,
    labelSize,
    splitArticles,
    codesByLineId,
    previewCis,
    maxUnits = Number.POSITIVE_INFINITY,
    authToken,
    signal,
  } = opts
  const nonHonestLay = nonHonestLayout(layout)
  const groupSections: string[][] = []
  let unitsEmitted = 0
  let previewSeq = 0
  for (const group of groups) {
    if (unitsEmitted >= maxUnits) break
    const sections: string[] = []
    for (const line of group.lines) {
      if (unitsEmitted >= maxUnits) break
      if (line.qtyNeedPack < 1) continue
      const takeUnits = Math.min(line.qtyNeedPack, maxUnits - unitsEmitted)
      if (takeUnits < 1) continue
      if (line.requiresHonestSign && layout.units.some((unit) => unit.block === 'cz')) {
        // Real print: use issued codes if available (full set covers ≥ takeUnits).
        // Preview or missing codes: emit stub units so the layout still renders.
        const issued = codesByLineId?.get(line.lineId) ?? []
        let units: MarkingTapeUnitInput[]
        if (issued.length >= takeUnits) {
          units = unitsFromIssuedCodes(issued.slice(0, takeUnits), line.productLabel)
        } else if (issued.length > 0 && codesByLineId) {
          // Partial print: use whatever codes we actually got, do not pad with stubs.
          units = unitsFromIssuedCodes(issued, line.productLabel)
        } else if (previewCis) {
          units = stubUnits(takeUnits, previewCis, previewSeq, line.productLabel)
          previewSeq += takeUnits
        } else {
          // No codes and no preview stub: skip this line entirely.
          continue
        }
        if (layout.units.length < 1) {
          // Пустой layout (например, после сброса конструктора) — нечего печатать.
          continue
        }
        sections.push(
          ...(await buildMarkingTapeSections(units, layout, line.productLabel, {
            authToken: authToken ?? undefined,
            labelSize,
            signal,
          })),
        )
        unitsEmitted += units.length
      } else {
        // Non-CZ line (or CZ line printed through the label-only path, e.g.
        // separate ШК): strip CZ blocks and emit label sections per unit.
        if (nonHonestLay.units.length < 1) {
          // Этот layout не даёт этой строке ни одной секции. Preview-бюджет
          // `maxUnits` считает ФАКТИЧЕСКИ выводимые единицы — иначе пустая
          // строка проглотила бы весь лимит и следующие группы, где секции
          // есть, перестали бы отображаться (R8).
          continue
        }
        if (!line.productLabel) throw new Error('Нет данных товара для печати.')
        const copies = nonHonestLay.units.reduce((sum, unit) => sum + Math.max(1, unit.copies), 0)
        sections.push(
          ...buildProductLabelSections(line.productLabel, takeUnits * copies, labelSize, labelOptionsFromLayout(layout)),
        )
        unitsEmitted += takeUnits
      }
    }
    if (sections.length > 0) groupSections.push(sections)
  }
  if (groupSections.length < 1) return []
  const result: string[] = []
  for (let i = 0; i < groupSections.length; i += 1) {
    if (i > 0 && splitArticles) {
      result.push(buildFboBulkSeparatorSection())
    }
    result.push(...groupSections[i]!)
  }
  return result
}

/** Сколько секций окажется в ленте — для сводной подписи «К печати: N блоков». */
export function countFboBulkSections(
  layout: PrintLayout,
  groups: FboBulkGroup[],
  splitArticles: boolean,
): number {
  const czCopies = layout.units
    .filter((u) => u.block === 'cz')
    .reduce((sum, u) => sum + Math.max(1, u.copies), 0)
  const labelCopies = layout.units
    .filter((u) => u.block === 'label')
    .reduce((sum, u) => sum + Math.max(1, u.copies), 0)
  const nonEmpty: number[] = []
  for (const group of groups) {
    let groupBlocks = 0
    for (const line of group.lines) {
      if (line.qtyNeedPack < 1) continue
      const perUnit = line.requiresHonestSign ? czCopies + labelCopies : labelCopies
      groupBlocks += Math.max(0, line.qtyNeedPack) * perUnit
    }
    if (groupBlocks > 0) nonEmpty.push(groupBlocks)
  }
  if (nonEmpty.length < 1) return 0
  const separators = splitArticles ? nonEmpty.length - 1 : 0
  return nonEmpty.reduce((sum, blocks) => sum + blocks, 0) + separators
}

/** Количество artikuла (не единиц) с хотя бы одной непустой строкой. */
export function countFboBulkGroups(groups: FboBulkGroup[]): number {
  return groups.filter((g) => g.lines.some((l) => l.qtyNeedPack > 0)).length
}

/** Используется диалогом, чтобы не пробрасывать весь layout в превью-функцию. */
export { labelOptionsFromLayout }
