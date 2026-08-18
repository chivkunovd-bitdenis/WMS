import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'
import {
  buildMarkingTapeDocument,
  buildMarkingTapeSections,
  buildWbOrderQrLabelHtml,
  type MarkingTapeUnitInput,
} from '../utils/printMarkingCodeLabel'
import {
  buildProductLabelSectionHtml,
  buildProductThermalLabelDocument,
  type ProductThermalLabelData,
} from '../utils/printProductThermalLabel'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'
import type { PrintLayout } from '../utils/printTemplate'
import type { LabelSize } from '../utils/labelSize'
import type { ProductLabelPrintOptions } from '../utils/productLabelText'

const MM_TO_PX = 3.7795275591
/**
 * Раньше ширина превью была зашита константой 220px (≈ натуральный размер 58мм
 * этикетки на экране) — читать такую миниатюру тяжело. Теперь ширина считается
 * от реально доступного места (ResizeObserver на обёртке), а эти границы лишь
 * не дают превью схлопнуться в узкой модалке и не дают ему раздуться на весь
 * широкий диалог сильнее, чем нужно для чтения одной этикетки.
 */
const PREVIEW_MIN_WIDTH_PX = 260
const PREVIEW_MAX_WIDTH_PX = 480
/** Ширина до первого измерения контейнера (ResizeObserver срабатывает после монтирования). */
const PREVIEW_FALLBACK_WIDTH_PX = 320
/**
 * Потолок высоты превью. Раньше был 520px — уже это обрезало типичный дефолтный
 * макет (58×40мм, 2 блока «ЧЗ на единицу» — обычное состояние формы при открытии)
 * на ~140px снизу, и приходилось скроллить саму рамку превью, а не только диалог.
 * 900px посчитан от факта: при максимальной ширине превью (480px, см. выше)
 * 58×40 и 60×40 с типовыми 1–2 блоками умещаются с запасом (~640–670px), а вот
 * по-настоящему крупные этикетки (70×120, длинные ленты из нескольких единиц)
 * всё равно превышают и это — для них остаётся собственная прокрутка ниже,
 * как и задумано: превью не сжимается до нечитаемости, а скроллится целиком.
 */
const PREVIEW_MAX_HEIGHT_PX = 900
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

/**
 * PRN-01: QR заказа WB (как и КМ ЧЗ выше) реально появляется только после
 * нажатия «Печать» — до этого его негде взять. Для превью строим QR по той
 * же технологии, что и настоящий (bwip-js, bcid 'qrcode' — см. renderBoxQrDataUrl
 * в FfFbsSupplyWorkspace.tsx), но по заглушке: макет честный, содержимое — нет.
 */
async function renderOrderQrPreviewDataUrl(): Promise<string> {
  const bwipjs = await import('bwip-js')
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, {
    bcid: 'qrcode',
    text: 'PREVIEW-WB-ORDER-QR',
    scale: 5,
    includetext: false,
  })
  return canvas.toDataURL('image/png')
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
  /** «Печать всего» на поставке FBS: перед лентой в реальности печатается QR заказа. */
  showOrderQr?: boolean
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
  /** «Печать всего» на поставке FBS: перед этикеткой в реальности печатается QR заказа. */
  showOrderQr?: boolean
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
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [containerWidthPx, setContainerWidthPx] = useState(PREVIEW_FALLBACK_WIDTH_PX)

  // Ширина превью считается от реально доступного места в диалоге, а не зашита
  // константой — так расширение самой модалки (или другой контейнер, например
  // узкая ProductBarcodePrintDialog) сразу даёт крупнее/мельче превью.
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => {
      const w = el.clientWidth
      if (w > 0) setContainerWidthPx(w)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const shown = Math.min(Math.max(1, Math.floor(unitsToShow) || 1), MAX_PREVIEW_UNITS)
  const total = Math.max(shown, Math.floor(totalUnits ?? shown) || shown)
  const showOrderQr = props.showOrderQr ?? false
  const blocksPerUnit =
    props.variant === 'product'
      ? 1
      : Math.max(
          1,
          props.layout.units.reduce((sum, unit) => sum + Math.max(1, unit.copies), 0),
        )
  // QR заказа печатается один раз (не на единицу) — см. printFbsTape в MarkingPrintDialog.tsx.
  const sectionsCount = shown * blocksPerUnit + (showOrderQr ? 1 : 0)
  const layoutKey = props.variant === 'product' ? 'product' : JSON.stringify(props.layout)
  const productLabel = props.productLabel ?? null
  const productPrintOptions = props.variant === 'product' ? props.printOptions : undefined

  useEffect(() => {
    const myRequest = ++requestRef.current
    setError(null)
    void (async () => {
      try {
        // QR заказа WB — тем же порядком, что и в реальной ленте (см. printFbsTape):
        // сначала QR заказа, потом сами этикетки (ЧЗ+ШК либо только ШК).
        const qrSections: string[] = showOrderQr
          ? [buildWbOrderQrLabelHtml(await renderOrderQrPreviewDataUrl())]
          : []
        let nextHtml: string | null
        if (props.variant === 'product') {
          const barcode = productLabel?.barcode?.trim()
          if (!productLabel || !barcode) {
            nextHtml = null
          } else {
            const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
            if (showOrderQr) {
              // «Печать всего» на поставке FBS: ленту с QR собирает та же функция,
              // что и настоящую печать (printTapeSections → buildMarkingTapeDocument) —
              // buildProductThermalLabelDocument для одиночных ШК её не поддерживает
              // (нет стилей под .label--wb-qr).
              const productSections = Array.from({ length: shown }, () =>
                buildProductLabelSectionHtml(productLabel, barcodeDataUrl, productPrintOptions, size),
              )
              nextHtml = buildMarkingTapeDocument([...qrSections, ...productSections], size)
            } else {
              nextHtml = buildProductThermalLabelDocument(
                productLabel,
                shown,
                barcodeDataUrl,
                productPrintOptions,
                size,
              )
            }
          }
        } else {
          const units: MarkingTapeUnitInput[] = Array.from({ length: shown }, (_, i) => ({
            cis: previewCis(i),
            productLabel,
          }))
          const sections = await buildMarkingTapeSections(units, props.layout, productLabel)
          nextHtml = buildMarkingTapeDocument([...qrSections, ...sections], size)
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
    showOrderQr,
  ])

  const previewWidthPx = Math.min(
    PREVIEW_MAX_WIDTH_PX,
    Math.max(PREVIEW_MIN_WIDTH_PX, containerWidthPx),
  )
  const nativeWidthPx = size.widthMm * MM_TO_PX
  const nativeHeightPx = size.heightMm * MM_TO_PX * sectionsCount
  const scale = previewWidthPx / nativeWidthPx
  // Ширина никогда не режется под высоту — если этикетка после масштабирования
  // по ширине всё равно не помещается в PREVIEW_MAX_HEIGHT_PX (например 70×120мм
  // или несколько блоков на ленте), даём внутреннюю прокрутку вместо того, чтобы
  // сжимать макет до нечитаемости.
  const scaledHeightPx = Math.min(nativeHeightPx * scale, PREVIEW_MAX_HEIGHT_PX)

  return (
    <Box data-testid={testId} ref={containerRef} sx={{ width: '100%' }}>
      {error ? (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      ) : (
        <Box
          sx={{
            width: previewWidthPx,
            maxWidth: '100%',
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
