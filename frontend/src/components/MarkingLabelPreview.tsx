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
import { plural } from '../utils/plural'
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
 * PRN-03: печать кладёт каждую секцию `.label` как отдельную страницу ленты
 * (page-break-after у printMarkingCodeLabel.ts/printProductThermalLabel.ts) — на
 * термопринтере это физически разные, разрезанные этикетки. В браузере page-break
 * ни на что не влияет, и секции рисуются вплотную одна к другой — предпросмотр
 * читался как одна слипшаяся картинка (QR заказа прямо на штрихкоде). Зазор ниже —
 * только для превью (см. injectPreviewSeparators); под него же корректируется
 * высота iframe (nativeHeightPx), чтобы контент не обрезался.
 */
const PREVIEW_LABEL_GAP_PX = 10
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

/**
 * PRN-03: добавляет CSS только для предпросмотра — то, что реально уходит на
 * принтер (буквально сам html из buildMarkingTapeDocument/buildProductThermalLabelDocument),
 * не трогаем, стиль дописывается уже поверх готового документа. Даёт каждой секции
 * `.label` свою рамку и зазор от соседней, плюс подпись по `data-tape-block` (его
 * расставляют buildCzLabelHtml/buildWbOrderQrLabelHtml/buildMarkingTapeSections),
 * чтобы QR заказа и штрихкод читались как два разных ярлыка, а не одна картинка.
 */
function injectPreviewSeparators(html: string): string {
  const style = `
    body { background: #dcdde0; }
    .label {
      position: relative;
      background: #fff;
      outline: 1.5px dashed rgba(17, 17, 17, 0.45);
      outline-offset: -1.5px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
      margin-top: ${PREVIEW_LABEL_GAP_PX}px;
    }
    .label[data-tape-block="wb_qr"]::before,
    .label[data-tape-block="cz"]::before,
    .label[data-tape-block="label"]::before {
      position: absolute;
      top: 2px;
      left: 2px;
      padding: 1px 4px;
      font: 700 8px/1.3 Arial, Helvetica, sans-serif;
      color: #111;
      background: rgba(255, 255, 255, 0.88);
      border-radius: 2px;
      pointer-events: none;
    }
    .label[data-tape-block="wb_qr"]::before { content: 'QR заказа'; }
    .label[data-tape-block="cz"]::before { content: 'Честный знак'; }
    .label[data-tape-block="label"]::before { content: 'Штрихкод'; }
  `
  return html.includes('</head>')
    ? html.replace('</head>', `<style>${style}</style></head>`)
    : html.replace('</body>', `<style>${style}</style></body>`)
}

export type FbsPreviewOrder = {
  requiresHonestSign: boolean
  productLabel: ProductThermalLabelData | null
}

type FbsOrdersPreviewProps = {
  /**
   * PRN-04: printFbsTape в MarkingPrintDialog.tsx печатает циклом по заказам —
   * на каждый заказ сначала QR заказа, потом его этикетки, и так на каждый
   * следующий заказ. Если задано вместе с showOrderQr=true, предпросмотр
   * повторяет тот же порядок (по заказам), а не один общий QR + один блок.
   */
  fbsOrders?: FbsPreviewOrder[]
  /** Сколько копий ШК-only этикетки на заказ без ЧЗ — fallbackLabelCopies из printFbsTape. */
  fbsNonHonestLabelCopies?: number
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
} & FbsOrdersPreviewProps

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
} & FbsOrdersPreviewProps

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
  const productLabel = props.productLabel ?? null
  const productPrintOptions = props.variant === 'product' ? props.printOptions : undefined
  // PRN-04: показываем не больше MAX_PREVIEW_UNITS заказов — та же граница, что и
  // раньше была у «единиц» (см. подпись под превью ниже).
  const fbsOrdersCapped =
    showOrderQr && props.fbsOrders && props.fbsOrders.length > 0
      ? props.fbsOrders.slice(0, MAX_PREVIEW_UNITS)
      : null
  const fbsOrdersTotal = props.fbsOrders?.length ?? 0
  const nonHonestLabelCopies = Math.max(1, Math.floor(props.fbsNonHonestLabelCopies ?? 1) || 1)
  const fbsOrdersKey = fbsOrdersCapped
    ? JSON.stringify(
        fbsOrdersCapped.map((order) => ({
          h: order.requiresHonestSign,
          b: order.productLabel?.barcode ?? '',
          n: order.productLabel?.product_name ?? '',
        })),
      )
    : ''
  // QR заказа печатается один раз на заказ (не на единицу) — см. printFbsTape в
  // MarkingPrintDialog.tsx. В режиме fbsOrders (PRN-04) секции считаются по
  // заказам; иначе — старым способом (один общий QR + плоский список единиц).
  const sectionsCount = fbsOrdersCapped
    ? fbsOrdersCapped.reduce((sum, order) => {
        const orderLabel = order.productLabel ?? productLabel
        const isHonestTape = props.variant === 'tape' && order.requiresHonestSign
        const labelSections = isHonestTape
          ? blocksPerUnit
          : orderLabel?.barcode?.trim()
            ? nonHonestLabelCopies
            : 0
        return sum + 1 + labelSections
      }, 0)
    : shown * blocksPerUnit + (showOrderQr ? 1 : 0)
  const layoutKey = props.variant === 'product' ? 'product' : JSON.stringify(props.layout)

  useEffect(() => {
    const myRequest = ++requestRef.current
    setError(null)
    void (async () => {
      try {
        let nextHtml: string | null
        if (fbsOrdersCapped) {
          /**
           * PRN-04: тот же порядок, что и в printFbsTape (MarkingPrintDialog.tsx) —
           * цикл `for (const printedOrder of result.orders)`: на каждый заказ
           * сначала QR заказа, потом его этикетки (ЧЗ+ШК для заказов с обязательным
           * ЧЗ, иначе — просто ШК), потом следующий заказ и снова QR. Раньше здесь
           * строился один общий QR и один плоский список единиц — предпросмотр не
           * отличался от печати одного-единственного заказа.
           */
          const orderSections: string[] = []
          let previewIndex = 0
          for (const order of fbsOrdersCapped) {
            orderSections.push(buildWbOrderQrLabelHtml(await renderOrderQrPreviewDataUrl()))
            const orderLabel = order.productLabel ?? productLabel
            if (props.variant === 'tape' && order.requiresHonestSign) {
              const units: MarkingTapeUnitInput[] = [
                { cis: previewCis(previewIndex), productLabel: orderLabel },
              ]
              previewIndex += 1
              orderSections.push(...(await buildMarkingTapeSections(units, props.layout, orderLabel)))
            } else {
              const barcode = orderLabel?.barcode?.trim()
              if (orderLabel && barcode) {
                const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
                for (let i = 0; i < nonHonestLabelCopies; i += 1) {
                  orderSections.push(
                    buildProductLabelSectionHtml(orderLabel, barcodeDataUrl, productPrintOptions, size).replace(
                      'data-testid="product-thermal-label"',
                      'data-testid="product-thermal-label" data-tape-block="label"',
                    ),
                  )
                }
              }
            }
          }
          nextHtml = orderSections.length > 0 ? buildMarkingTapeDocument(orderSections, size) : null
        } else if (props.variant === 'product') {
          // QR заказа WB — тем же порядком, что и в реальной ленте (см. printFbsTape):
          // сначала QR заказа, потом сами этикетки (ЧЗ+ШК либо только ШК).
          const qrSections: string[] = showOrderQr
            ? [buildWbOrderQrLabelHtml(await renderOrderQrPreviewDataUrl())]
            : []
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
          const qrSections: string[] = showOrderQr
            ? [buildWbOrderQrLabelHtml(await renderOrderQrPreviewDataUrl())]
            : []
          const units: MarkingTapeUnitInput[] = Array.from({ length: shown }, (_, i) => ({
            cis: previewCis(i),
            productLabel,
          }))
          const sections = await buildMarkingTapeSections(units, props.layout, productLabel)
          nextHtml = buildMarkingTapeDocument([...qrSections, ...sections], size)
        }
        if (requestRef.current === myRequest) {
          setHtml(nextHtml ? injectPreviewSeparators(nextHtml) : null)
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
    fbsOrdersKey,
    nonHonestLabelCopies,
  ])

  const previewWidthPx = Math.min(
    PREVIEW_MAX_WIDTH_PX,
    Math.max(PREVIEW_MIN_WIDTH_PX, containerWidthPx),
  )
  const nativeWidthPx = size.widthMm * MM_TO_PX
  // PRN-03: injectPreviewSeparators добавляет зазор перед каждой секцией — учитываем
  // его здесь, иначе реальная высота содержимого iframe разойдётся с заданной.
  const nativeHeightPx = (size.heightMm * MM_TO_PX + PREVIEW_LABEL_GAP_PX) * sectionsCount
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
        {fbsOrdersCapped
          ? fbsOrdersTotal > fbsOrdersCapped.length
            ? `Показаны первые ${fbsOrdersCapped.length} ${plural(fbsOrdersCapped.length, ['заказ', 'заказа', 'заказов'])} из ${fbsOrdersTotal}`
            : `${fbsOrdersCapped.length} ${plural(fbsOrdersCapped.length, ['заказ', 'заказа', 'заказов'])} на ленте`
          : total > shown
            ? `Показаны первые ${shown} из ${total}`
            : `${total} ${total === 1 ? 'копия' : 'копий'} на ленте`}
      </Typography>
    </Box>
  )
}
