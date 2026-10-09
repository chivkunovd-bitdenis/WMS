import { renderCzLabelPng, renderLabelSectionPng } from '../../../utils/czLabelPng'
import { loadLabelSizeId, resolveLabelSize, type LabelSize } from '../../../utils/labelSize'
import { displayMetaToProductLabel } from '../../../utils/productBarcodePrint'
import { printPreparedQr } from '../../../utils/printPreparedQr'
import {
  buildProductLabelSectionHtml,
  type ProductThermalLabelData,
} from '../../../utils/printProductThermalLabel'
import { renderBarcodeDataUrl } from '../../../utils/renderBarcodeDataUrl'
import { isSeparateMarkingPrintEnabled } from '../../../utils/separateMarkingPrint'
import { randomId } from '../../../utils/randomId'
import {
  resolveProductBarcodeOptions,
  type ProductLineDisplayMeta,
} from '../../../types/wbProductCatalog'
import type { FboMarkingCode } from './fboPackingTypes'

/**
 * Печать упаковки FBO идёт только через WMS Print (PNG + ключ операции).
 * Ключ стабилен для одной штуки или одного кода: повтор после потери ответа
 * не печатает вторую копию. Явная «Перепечатать» берёт новый ключ.
 */

export function czLabelSize(): LabelSize {
  return resolveLabelSize(loadLabelSizeId(isSeparateMarkingPrintEnabled() ? 'cz' : 'default'))
}

export function productLabelSize(): LabelSize {
  return resolveLabelSize(loadLabelSizeId(isSeparateMarkingPrintEnabled() ? 'label' : 'default'))
}

/** ШК товара для этикетки: код площадки отгрузки, иначе первый имеющийся. */
export function productBarcodeForMarketplace(meta: ProductLineDisplayMeta, marketplace: string): string {
  const options = resolveProductBarcodeOptions(meta)
  const wanted = marketplace === 'ozon' ? 'ozon' : 'wb'
  return options.find((option) => option.marketplace === wanted)?.barcode ?? options[0]?.barcode ?? ''
}

export function productLabelData(meta: ProductLineDisplayMeta, marketplace: string): ProductThermalLabelData {
  return { ...displayMetaToProductLabel(meta), barcode: productBarcodeForMarketplace(meta, marketplace) }
}

function copyKey(key: string, index: number, copies: number): string {
  return copies > 1 ? `${key}:c${index + 1}` : key
}

/** Этикетка ШК товара: одна картинка, по заданию WMS Print на каждую копию. */
export async function printProductBarcodeLabels(
  label: ProductThermalLabelData,
  keyBase: string,
  copies = 1,
): Promise<void> {
  const barcode = label.barcode.trim()
  if (!barcode) throw new Error('У товара нет штрихкода для печати.')
  const size = productLabelSize()
  const section = buildProductLabelSectionHtml(label, renderBarcodeDataUrl(barcode, { variant: 'thermal58' }), undefined, size)
  const imageDataUrl = await renderLabelSectionPng(section, size)
  for (let index = 0; index < copies; index += 1) {
    await printPreparedQr({
      imageDataUrl,
      idempotencyKey: copyKey(keyBase, index, copies),
      widthMm: size.widthMm,
      heightMm: size.heightMm,
    })
  }
}

/** Ключ первой печати кода: один и тот же, пока код не напечатан. */
export function firstPrintKey(code: FboMarkingCode): string {
  return `fbo-chz:${code.marking_code_id}`
}

/** Ключ явной перепечати: каждое нажатие печатает ещё одну этикетку. */
export function reprintKey(code: FboMarkingCode): string {
  return `fbo-chz-re:${code.marking_code_id}:${randomId()}`
}

export async function printMarkingCodeLabel(code: FboMarkingCode, token: string, key: string): Promise<void> {
  const size = czLabelSize()
  const imageDataUrl = await renderCzLabelPng(
    { cis: code.cis_code, codeId: code.marking_code_id, hasLabelArtifact: code.has_label_artifact === true },
    size,
    token,
  )
  await printPreparedQr({
    imageDataUrl,
    idempotencyKey: key,
    widthMm: size.widthMm,
    heightMm: size.heightMm,
  })
}

export type MarkingPrintOutcome = {
  /** Коды, которые не ушли в печать: на первом сбое остановка, остальные ждут повтора. */
  unprinted: FboMarkingCode[]
  error: Error | null
}

/** Печать списка кодов по очереди. Сбой не теряет коды: их можно напечатать теми же ключами. */
export async function printMarkingCodes(
  codes: FboMarkingCode[],
  token: string,
  keyOf: (code: FboMarkingCode) => string = firstPrintKey,
): Promise<MarkingPrintOutcome> {
  for (let index = 0; index < codes.length; index += 1) {
    const code = codes[index]!
    try {
      await printMarkingCodeLabel(code, token, keyOf(code))
    } catch (cause) {
      return {
        unprinted: codes.slice(index),
        error: cause instanceof Error ? cause : new Error('Не удалось напечатать этикетку ЧЗ.'),
      }
    }
  }
  return { unprinted: [], error: null }
}
