import type { LabelSize } from './labelSize'
import {
  buildCzArtifactLabelHtml,
  buildCzLabelHtml,
  buildTapePageCss,
  fetchLabelArtifactDataUrl,
  renderDataMatrixDataUrl,
} from './printMarkingCodeLabel'

/** Print resolution of the PNG handed to WMS Print (about 300 dpi). */
const PX_PER_MM = 12
const CSS_PX_PER_MM = 96 / 25.4

export type CzLabelPngInput = {
  cis: string
  codeId?: string | null
  hasLabelArtifact?: boolean
}

/**
 * WMS-631 R12: the same CZ label the browser tape prints (DataMatrix + fields,
 * or the seller's label image), rendered by the browser itself into one PNG
 * of the saved label size. No print dialog, iframe or window is involved.
 */
export async function renderCzLabelPng(
  unit: CzLabelPngInput,
  size: LabelSize,
  authToken?: string | null,
): Promise<string> {
  const section = unit.codeId && unit.hasLabelArtifact && authToken
    ? buildCzArtifactLabelHtml(await fetchLabelArtifactDataUrl(unit.codeId, authToken))
    : buildCzLabelHtml(unit.cis, await renderDataMatrixDataUrl(unit.cis))
  return renderLabelSectionPng(section, size)
}

export async function renderLabelSectionPng(section: string, size: LabelSize): Promise<string> {
  const cssWidth = size.widthMm * CSS_PX_PER_MM
  const cssHeight = size.heightMm * CSS_PX_PER_MM
  const width = Math.round(size.widthMm * PX_PER_MM)
  const height = Math.round(size.heightMm * PX_PER_MM)
  // The tape CSS is used unchanged; only the matrix is kept pixel-sharp when scaled.
  const css = `${buildTapePageCss(size)}\n.cz-matrix img { image-rendering: pixelated; }`
  const xhtml = `<div xmlns="http://www.w3.org/1999/xhtml" style="width:${size.widthMm}mm;height:${size.heightMm}mm;margin:0;padding:0;overflow:hidden;background:#fff;color:#111;font-family:Arial, Helvetica, sans-serif"><style><![CDATA[${css}]]></style>${section}</div>`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${cssWidth} ${cssHeight}"><foreignObject x="0" y="0" width="${cssWidth}" height="${cssHeight}">${xhtml}</foreignObject></svg>`
  const image = new Image()
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve()
    image.onerror = () => reject(new Error('Не удалось подготовить этикетку ЧЗ для печати.'))
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  })
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Не удалось подготовить этикетку ЧЗ для печати.')
  context.fillStyle = '#fff'
  context.fillRect(0, 0, width, height)
  context.drawImage(image, 0, 0, width, height)
  return canvas.toDataURL('image/png')
}
