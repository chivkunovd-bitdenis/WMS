import { useEffect, useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'
import {
  buildMarkingTapeDocument,
  buildMarkingTapeSections,
  type MarkingTapeUnitInput,
} from '../utils/printMarkingCodeLabel'
import {
  buildProductThermalLabelDocument,
  type ProductThermalLabelData,
} from '../utils/printProductThermalLabel'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'
import type { PrintLayout } from '../utils/printTemplate'
import type { LabelSize } from '../utils/labelSize'
import type { ProductLabelPrintOptions } from '../utils/productLabelText'

const MM_TO_PX = 3.7795275591
const PREVIEW_WIDTH_PX = 220
const PREVIEW_MAX_HEIGHT_PX = 420
const MAX_PREVIEW_UNITS = 3

/**
 * КМ ещё не зарезервирован в пуле — это происходит только при реальном
 * нажатии «Печать». Для превью строим DataMatrix по заглушке, но той же
 * функцией (buildMarkingTapeSections → renderDataMatrixDataUrl), которой
 * рендерится настоящий КМ при печати. Макет и раскладка — честные,
 * только конкретные цифры кода — нет (их и не может быть до печати).
 */
function previewCis(index: number): string {
  const gtin = '04607975432198'
  return `\x1d01${gtin}21PREVIEW${index + 1}`
}

type TapeVariantProps = {
  variant?: 'tape'
  layout: PrintLayout
  productLabel?: ProductThermalLabelData | null
  size: LabelSize
  /** Сколько единиц (продукт-юнитов либо копий) реально показать — обрезается до 3. */
  unitsToShow: number
  /** Настоящее суммарное количество к печати, если оно больше unitsToShow. */
  totalUnits?: number
  testId?: string
}

type ProductVariantProps = {
  variant: 'product'
  productLabel: ProductThermalLabelData | null
  size: LabelSize
  unitsToShow: number
  totalUnits?: number
  /** Какие опциональные поля показывать (например, состав) — как при реальной печати. */
  printOptions?: ProductLabelPrintOptions
  testId?: string
}

type Props = TapeVariantProps | ProductVariantProps

/**
 * FBS-10: реальный макет этикетки до печати. Строится той же функцией, что и
 * настоящая печать (buildMarkingTapeSections/buildMarkingTapeDocument из
 * printMarkingCodeLabel.ts — общая лента ЧЗ+ШК; buildProductThermalLabelDocument
 * из printProductThermalLabel.ts — печать только ШК ВБ без ЧЗ), просто
 * отрисован в масштабированном iframe вместо реальной печати. Заказчик:
 * «я не понимаю, как ШК распечатается, пока не нажму печать» — это превью
 * закрывает именно это, а не рисует вторую (и потому способную разойтись
 * с реальностью) картинку.
 */
export function MarkingLabelPreview(props: Props) {
  const { size, unitsToShow, totalUnits, testId } = props
  const [html, setHtml] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const requestRef = useRef(0)

  const shown = Math.min(Math.max(1, Math.floor(unitsToShow) || 1), MAX_PREVIEW_UNITS)
  const total = Math.max(shown, Math.floor(totalUnits ?? shown) || shown)
  const blocksPerUnit =
    props.variant === 'product'
      ? 1
      : Math.max(
          1,
          props.layout.units.reduce((sum, unit) => sum + Math.max(1, unit.copies), 0),
        )
  const sectionsCount = shown * blocksPerUnit
  const layoutKey = props.variant === 'product' ? 'product' : JSON.stringify(props.layout)
  const productLabel = props.productLabel ?? null
  const productPrintOptions = props.variant === 'product' ? props.printOptions : undefined

  useEffect(() => {
    const myRequest = ++requestRef.current
    setError(null)
    void (async () => {
      try {
        let nextHtml: string | null
        if (props.variant === 'product') {
          const barcode = productLabel?.barcode?.trim()
          if (!productLabel || !barcode) {
            nextHtml = null
          } else {
            const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
            nextHtml = buildProductThermalLabelDocument(
              productLabel,
              shown,
              barcodeDataUrl,
              productPrintOptions,
              size,
            )
          }
        } else {
          const units: MarkingTapeUnitInput[] = Array.from({ length: shown }, (_, i) => ({
            cis: previewCis(i),
            productLabel,
          }))
          const sections = await buildMarkingTapeSections(units, props.layout, productLabel)
          nextHtml = buildMarkingTapeDocument(sections, size)
        }
        if (requestRef.current === myRequest) {
          setHtml(nextHtml)
        }
      } catch (e) {
        if (requestRef.current === myRequest) {
          setError(e instanceof Error ? e.message : 'Не удалось построить макет.')
          setHtml(null)
        }
      }
    })()
    // layoutKey сериализует layout для tape-варианта; size/shown/productLabel — остальные входы макета.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    layoutKey,
    size.widthMm,
    size.heightMm,
    shown,
    productLabel?.barcode,
    productLabel?.product_name,
    productPrintOptions?.includeComposition,
    productPrintOptions?.includeSize,
  ])

  const nativeWidthPx = size.widthMm * MM_TO_PX
  const nativeHeightPx = size.heightMm * MM_TO_PX * sectionsCount
  const scale = PREVIEW_WIDTH_PX / nativeWidthPx
  const scaledHeightPx = Math.min(nativeHeightPx * scale, PREVIEW_MAX_HEIGHT_PX)

  return (
    <Box data-testid={testId}>
      {error ? (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      ) : (
        <Box
          sx={{
            width: PREVIEW_WIDTH_PX,
            height: scaledHeightPx,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 0.5,
            overflow: 'auto',
            bgcolor: '#fff',
          }}
        >
          {html ? (
            <iframe
              title="Предпросмотр этикетки"
              srcDoc={html}
              sandbox=""
              style={{
                display: 'block',
                border: 0,
                width: nativeWidthPx,
                height: nativeHeightPx,
                transform: `scale(${scale})`,
                transformOrigin: 'top left',
                pointerEvents: 'none',
              }}
            />
          ) : null}
        </Box>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        {total > shown
          ? `Показаны первые ${shown} из ${total}`
          : `${total} ${total === 1 ? 'копия' : 'копий'} на ленте`}
      </Typography>
    </Box>
  )
}
