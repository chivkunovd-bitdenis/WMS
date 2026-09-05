import { PrintQuantityField } from './PrintQuantityField'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { apiUrl } from '../api'
import { resolveProductBarcodeSelection, type ProductBarcodeOption } from '../types/wbProductCatalog'
import { plural } from '../utils/plural'
import {
  MARKING_PRINT_PRESETS,
  blockLabel,
  buildDefaultTape,
  buildTapePreviewUnits,
  cloneLayout,
  countTapeBlocksFromTape,
  expandLayoutToTape,
  tapeToLayout,
  type TapeBlock,
} from '../utils/markingPrintPresets'
import { resolvePrintTemplate, type PrintLabelOptions, type PrintLayout } from '../utils/printTemplate'
import { labelOptionsFromLayout } from '../utils/printMarkingCodeLabel'
import type { ProductLabelPrintOptions } from '../utils/productLabelText'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'
import {
  beginPrintUserGesture,
  buildMarkingTapeSections,
  buildWbOrderQrLabelHtml,
  printCzArtifactTape,
  printTapeSections,
  type MarkingTapeUnitInput,
} from '../utils/printMarkingCodeLabel'
import { buildProductLabelSectionHtml, type ProductThermalLabelData } from '../utils/printProductThermalLabel'
import { printProductThermalLabels } from '../utils/printProductThermalLabel'
import { resolveManualWbLabelCount } from '../utils/productBarcodePrint'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'
import {
  loadLabelPrintOrientation,
  loadLabelSizeId,
  resolveLabelSize,
  resolvePrintPageSize,
  saveLabelPrintOrientation,
  type LabelPrintOrientation,
  type LabelSize,
} from '../utils/labelSize'
import {
  refreshSeparateMarkingPrintEnabled,
  setSeparateMarkingPrintEnabled,
  useSeparateMarkingPrint,
} from '../utils/separateMarkingPrint'
import { LabelSizeSelect } from './LabelSizeSelect'
import { MarkingLabelPreview } from './MarkingLabelPreview'

type PrintedCodeOption = {
  id: string
  cis_masked: string
  status: string
}

type FbsTapeAsset = {
  id: string
  status: string
  preview_url: string | null
  applied_at: string | null
}

type FbsTapeOrderContext = {
  orderId: string
  wbOrderId: number
  requiresHonestSign: boolean
  productLabel: ProductThermalLabelData
}

type FbsTapePrintOrder = {
  order_id: string
  wb_order_id: number
  requires_honest_sign: boolean
  qr_asset: FbsTapeAsset | null
  printed_codes: Array<{ id: string; cis_code: string; has_label_artifact: boolean }>
  shortage: number | null
}

type FbsTapePrintResult = {
  orders: FbsTapePrintOrder[]
  order_errors: Array<{ order_id: string; wb_order_id: number; code: string; message: string }>
  shortage: number
}

type FbsTapeContext = {
  orders: FbsTapeOrderContext[]
  includeOrderQr: boolean
  print: (args: { layout: PrintLayout; allowPartial: boolean; reprint: boolean }) => Promise<FbsTapePrintResult>
  confirmQrApplied: (asset: FbsTapeAsset) => Promise<void>
}

/** Fixed layout for non-ЧЗ: one WB barcode label per unit, no constructor. */
const NON_HONEST_SIGN_LABEL_LAYOUT: PrintLayout = {
  units: [{ block: 'label', copies: 1 }],
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error ?? new Error('Не удалось загрузить изображение.'))
    reader.readAsDataURL(blob)
  })
}

async function fetchAuthorizedImageDataUrl(
  token: string,
  url: string,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(/^https?:\/\//i.test(url) ? url : apiUrl(url), {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!res.ok) {
    throw new Error('QR заказа WB не загружен.')
  }
  return blobToDataUrl(await res.blob())
}

const FBS_TAPE_BUILD_CONCURRENCY = 6

/** Параллельная обработка с ограничением нагрузки и сохранением исходного порядка. */
export async function mapConcurrentlyInOrder<T, R>(
  items: readonly T[],
  concurrency: number,
  task: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  if (items.length === 0) return []
  const results = new Array<R>(items.length)
  let cursor = 0
  const worker = async () => {
    while (true) {
      const index = cursor
      cursor += 1
      if (index >= items.length) return
      results[index] = await task(items[index] as T, index)
    }
  }
  await Promise.all(
    Array.from(
      { length: Math.min(Math.max(1, Math.floor(concurrency)), items.length) },
      worker,
    ),
  )
  return results
}

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw new DOMException('Сборка отменена.', 'AbortError')
}

function isAbortError(cause: unknown): boolean {
  return cause instanceof Error && cause.name === 'AbortError'
}

function labelCopiesFromLayout(layout: PrintLayout): number {
  return layout.units
    .filter((unit) => unit.block === 'label')
    .reduce((sum, unit) => sum + Math.max(1, unit.copies), 0)
}

function buildProductLabelSections(
  product: ProductThermalLabelData,
  count: number,
  size: LabelSize,
  labelOptions?: ProductLabelPrintOptions,
): string[] {
  const barcode = product.barcode?.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
  return Array.from({ length: count }, () =>
    buildProductLabelSectionHtml(
      product,
      barcodeDataUrl,
      labelOptions,
      size,
    ).replace('data-testid="product-thermal-label"', 'data-testid="product-thermal-label" data-tape-block="label"'),
  )
}

export type MarkingPrintContext = {
  token: string
  /** Пустой или отсутствует — печать из каталога/ЧЗ без строки упаковки (client-side). */
  lineId?: string
  source?: 'packaging' | 'catalog'
  productId: string
  /** Селлер товара: по нему подбирается закреплённый за селлером шаблон. */
  sellerId?: string | null
  documentNumber: string | null
  qtyNeedPack: number
  markingAvailable: number
  qtyMarkingPrinted: number
  requiresHonestSign: boolean
  skuCode: string
  productName: string
  productLabel?: ProductThermalLabelData | null
  /** Реальные коды связанной Ozon/объединённой карточки; WB-only не меняется. */
  productBarcodeOptions?: ProductBarcodeOption[]
  packagingInstructions?: string | null
  unitsInPack?: number | null
  fbsTape?: FbsTapeContext
  onPrinted: () => void
}

type Props = {
  open: boolean
  reprint: boolean
  ctx: MarkingPrintContext | null
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onClose: () => void
}

export function resolveTapeCounts(
  nextCz: number,
  nextWb: number,
  allowQrOnly: boolean,
  labelOptions?: PrintLabelOptions,
) {
  const cz = Math.max(0, Math.min(99, Math.floor(nextCz) || 0))
  const wb = Math.max(0, Math.min(99, Math.floor(nextWb) || 0))
  const qrOnly = allowQrOnly && cz === 0 && wb === 0
  const effectiveCz = qrOnly || cz > 0 || wb > 0 ? cz : 1
  const tape = buildDefaultTape(effectiveCz, wb)
  return {
    cz: effectiveCz,
    wb,
    tape,
    // Состав этикетки переживает смену количества блоков: он про товар
    // продавца, а не про раскладку оператора.
    layout: qrOnly
      ? ({ units: [], label_options: labelOptions } satisfies PrintLayout)
      : tapeToLayout(tape, labelOptions),
  }
}

export function resolveFbsFallbackLabelCopies(
  hasHonestSignOrders: boolean,
  printLayout: PrintLayout,
  configuredCopies: number,
  qrOnly: boolean,
) {
  if (qrOnly) return 0
  return hasHonestSignOrders
    ? Math.max(1, labelCopiesFromLayout(printLayout))
    : configuredCopies
}

export function resolveProductTapeBarcodeError(
  barcodeOptions: ProductBarcodeOption[] | undefined,
  barcode: string | null | undefined,
  layout: PrintLayout,
): string | null {
  if (barcodeOptions !== undefined && !barcode?.trim() && layout.units.some((unit) => unit.block === 'label')) {
    return 'У товара нет штрихкода Ozon для печати. Уберите ШК товара из ленты или добавьте штрихкод в привязке товара.'
  }
  return null
}

export function MarkingPrintDialog({ open, reprint, ctx, busy, onBusyChange, onClose }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [productBarcodeKey, setProductBarcodeKey] = useState('')
  const barcodeOptions = ctx?.productBarcodeOptions
  const selectedBarcode = barcodeOptions ? resolveProductBarcodeSelection(barcodeOptions, productBarcodeKey) : undefined
  const isOzonBarcode = selectedBarcode?.marketplace === 'ozon' || (barcodeOptions !== undefined && barcodeOptions.length === 0)
  const selectedProductLabel = useMemo(() => {
    const label = ctx?.productLabel
    if (!label || barcodeOptions === undefined) return label
    return { ...label, barcode: selectedBarcode?.barcode ?? '' }
  }, [ctx?.productLabel, barcodeOptions, selectedBarcode])
  const productBarcodeName = isOzonBarcode ? 'ШК Ozon' : 'ШК ВБ'

  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId()))
  const [layout, setLayout] = useState<PrintLayout>(MARKING_PRINT_PRESETS[0].layout)
  const [allowPartial, setAllowPartial] = useState(false)
  const [czQty, setCzQty] = useState(2)
  const [wbQty, setWbQty] = useState(0)
  const [tapeOrder, setTapeOrder] = useState<TapeBlock[]>(buildDefaultTape(2, 0))
  const requestedProductRef = useRef<string | null>(null)
  const [dragTapeIndex, setDragTapeIndex] = useState<number | null>(null)
  const [catalogPrintQty, setCatalogPrintQty] = useState(1)
  const [wbBarcodeQty, setWbBarcodeQty] = useState(1)
  const [printDoubleWbBarcode, setPrintDoubleWbBarcode] = useState(false)
  const [reprintCodes, setReprintCodes] = useState<PrintedCodeOption[]>([])
  const [selectedReprintCodeIds, setSelectedReprintCodeIds] = useState<string[]>([])
  const [reprintCodesLoading, setReprintCodesLoading] = useState(false)
  const [inlineReprint, setInlineReprint] = useState(false)
  // Раздельная печать ЧЗ и ШК ВБ: свои размеры и свои кнопки на каждый тип этикетки.
  const separateEnabledFromStore = useSeparateMarkingPrint()
  const [separateEnabledFromProfile, setSeparateEnabledFromProfile] = useState<boolean | null>(null)
  const [separateSettingLoading, setSeparateSettingLoading] = useState(false)
  /**
   * FBS-10: переключатель «раздельно / вместе» теперь живёт на самой форме печати,
   * а не только в настройках тенанта (см. FfSettingsScreen). Оператор решает
   * в момент печати; null — использовать значение по умолчанию из профиля/стора.
   */
  const [separateModeChoice, setSeparateModeChoice] = useState<boolean | null>(null)
  const [czLabelSize, setCzLabelSize] = useState<LabelSize>(() =>
    resolveLabelSize(loadLabelSizeId('cz')),
  )
  const [czPrintOrientation, setCzPrintOrientation] = useState<LabelPrintOrientation>(() =>
    loadLabelPrintOrientation(),
  )
  const [wbLabelSize, setWbLabelSize] = useState<LabelSize>(() =>
    resolveLabelSize(loadLabelSizeId('label')),
  )
  const [sepCzQty, setSepCzQty] = useState(2)
  const [sepWbQty, setSepWbQty] = useState(1)
  const [sepCzDone, setSepCzDone] = useState(false)
  const [fbsTapeBuildProgress, setFbsTapeBuildProgress] = useState<{
    completed: number
    total: number
  } | null>(null)
  const fbsTapeBuildAbortRef = useRef<AbortController | null>(null)

  const requiresHonestSign = ctx?.requiresHonestSign ?? true
  const fbsTapeMode = Boolean(ctx?.fbsTape)
  const fbsTapeOrders = ctx?.fbsTape?.orders ?? []
  const fbsHonestSignOrders = fbsTapeOrders.filter((order) => order.requiresHonestSign)
  /**
   * PRN-01: «Печать всего» на поставке FBS (openBulkOrderMarkingPrint) всегда
   * включает fbsTape.includeOrderQr — на ленту реально уходит QR заказа WB вместе
   * с ЧЗ/ШК (см. printFbsTape ниже). Раньше предпросмотр этот QR не показывал
   * вообще, а заголовок диалога назывался «Печать ШК ВБ», хотя печаталось всё —
   * заказчик жаловался, что кнопка обещает «всё», а окно показывает один элемент.
   * Флаг ниже включает QR в предпросмотр (MarkingLabelPreview) и правит заголовок
   * под фактический состав ленты; сама печать (что уходит на принтер) не меняется.
   */
  const includesOrderQr = fbsTapeMode && Boolean(ctx?.fbsTape?.includeOrderQr)
  const isCatalogSource = ctx?.source === 'catalog'
  /**
   * Перепечатка существует только чтобы не жечь коды ЧЗ повторно (FBS-11) — у товара
   * без ЧЗ печатать нечего повторно, там нет расходуемого пула. Поэтому режим
   * повторной печати для таких товаров не включаем, даже если вызывающий экран
   * попросил reprint:true — это тот же признак requiresHonestSign, что и у
   * NON_HONEST_SIGN_LABEL_LAYOUT выше.
   */
  const effectiveReprint = (reprint || inlineReprint) && requiresHonestSign
  const markingAlreadyPrinted = (ctx?.qtyMarkingPrinted ?? 0) > 0
  const canOpenInlineReprint = Boolean(
    ctx?.lineId && markingAlreadyPrinted && !fbsTapeMode && requiresHonestSign,
  )
  const separateEnabled = separateModeChoice ?? (separateEnabledFromProfile ?? separateEnabledFromStore)
  /** Раздельный режим: только для товаров с ЧЗ и не для перепечатки (там печатается один ЧЗ). */
  const separateMode = separateEnabled && requiresHonestSign && !effectiveReprint && !fbsTapeMode
  const separateModeResolving =
    open &&
    !fbsTapeMode &&
    Boolean(ctx?.token) &&
    requiresHonestSign &&
    !effectiveReprint &&
    !separateEnabledFromStore &&
    separateSettingLoading &&
    separateEnabledFromProfile === null &&
    separateModeChoice === null
  const resolvedCzPrintSize = useMemo(
    () => resolvePrintPageSize(czLabelSize, czPrintOrientation),
    [czLabelSize, czPrintOrientation],
  )
  /** Физический размер страницы ЧЗ для native PDF (все режимы + ориентация). */
  const czTapePrintSize = useMemo(
    () =>
      separateEnabled && requiresHonestSign
        ? resolvedCzPrintSize
        : resolvePrintPageSize(labelSize, czPrintOrientation),
    [separateEnabled, requiresHonestSign, resolvedCzPrintSize, labelSize, czPrintOrientation],
  )

  const applyTapeCounts = (nextCz: number, nextWb: number) => {
    // В общей FBS-ленте QR заказа является самостоятельной этикеткой. Поэтому
    // здесь законна пустая раскладка ЧЗ/ШК: оператор печатает только QR, а ЧЗ
    // сканирует или печатает позже. Во всех остальных режимах сохраняем прежний
    // минимум — хотя бы один блок ЧЗ.
    const next = resolveTapeCounts(nextCz, nextWb, includesOrderQr, layout.label_options)
    setCzQty(next.cz)
    setWbQty(next.wb)
    setTapeOrder(next.tape)
    setLayout(next.layout)
  }

  const applyTapeOrder = (nextTape: TapeBlock[]) => {
    setTapeOrder(nextTape)
    // Состав переносим в новый макет: он принадлежит товару продавца, а не
    // раскладке. Без этого перетаскивание блоков возвращало выключенные поля.
    setLayout((current) => tapeToLayout(nextTape, current.label_options))
    setCzQty(nextTape.filter((b) => b === 'cz').length)
    setWbQty(nextTape.filter((b) => b === 'label').length)
  }

  useEffect(() => {
    if (open) {
      setInlineReprint(false)
    }
  }, [open, ctx])

  useEffect(() => {
    if (open) return
    fbsTapeBuildAbortRef.current?.abort()
    fbsTapeBuildAbortRef.current = null
    setFbsTapeBuildProgress(null)
  }, [open])

  useEffect(() => {
    if (!open || !ctx?.token || !requiresHonestSign || effectiveReprint || fbsTapeMode) {
      setSeparateEnabledFromProfile(null)
      setSeparateSettingLoading(false)
      return
    }
    let cancelled = false
    setSeparateEnabledFromProfile(null)
    setSeparateSettingLoading(!separateEnabledFromStore)
    void refreshSeparateMarkingPrintEnabled(ctx.token)
      .then((value) => {
        if (!cancelled) {
          setSeparateEnabledFromProfile(value)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSeparateEnabledFromProfile(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSeparateSettingLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, ctx?.token, requiresHonestSign, effectiveReprint, separateEnabledFromStore, fbsTapeMode])

  /**
   * ВАЖНО: этот эффект — единственное место, которое обнуляет состояние диалога
   * между печатями. Сам диалог смонтирован постоянно (open только переключает
   * видимость MUI <Dialog>, компонент MarkingPrintDialog не пересоздаётся), поэтому
   * любой счётчик/флаг, заведённый через useState и не сброшенный здесь, протекает
   * из прошлой печати в следующую — даже если это печать того же товара по другой
   * строке упаковки. Если добавляешь новое поле состояния в этот компонент —
   * впиши его сброс сюда же, иначе получишь тот же класс бага, что был здесь раньше
   * (зависимость эффекта была точечной — ctx?.productId/ctx?.token — и не ловила
   * смену lineId при том же товаре).
   */
  useEffect(() => {
    if (!open || !ctx) {
      return
    }
    setError(null)
    setProductBarcodeKey('')
    setFbsTapeBuildProgress(null)
    setAllowPartial(false)
    setSeparateModeChoice(null)
    // Этикетка ШК ВБ клеится на единицу товара: разумное первое значение — сколько
    // единиц нужно напечатать/упаковать, а не жёсткая «1» (иначе оператор по умолчанию
    // печатает одну этикетку на несколько единиц и должен сам это заметить).
    // I4 (20.08.2026): в ленте FBS печать идёт циклом по заказам, и это поле —
    // число ШК-этикеток НА ОДИН заказ. Подставлять сюда число заказов значило
    // печатать 155 × 155 = 24 тысячи листов, что и случилось на бою.
    const wbDefaultQty = ctx.source === 'catalog' || ctx.fbsTape ? 1 : Math.max(1, ctx.qtyNeedPack || 1)
    setWbBarcodeQty(wbDefaultQty)
    setPrintDoubleWbBarcode(false)
    setCatalogPrintQty(1)
    setDragTapeIndex(null)
    setSepCzQty(2)
    setSepWbQty(wbDefaultQty)
    setSepCzDone(false)
    setCzLabelSize(resolveLabelSize(loadLabelSizeId('cz')))
    setCzPrintOrientation(loadLabelPrintOrientation())
    setWbLabelSize(resolveLabelSize(loadLabelSizeId('label')))
    // Метка «какой товар мы сейчас спрашиваем» ставится ДО развилки: её сверяют
    // обе ветки, и обе летят за шаблоном. Пока она стояла только в ветке обычного
    // товара, у маркируемого сверка шла с null и ответ выбрасывался всегда —
    // то есть шаблон переставал применяться на живом вайлдберрисовском потоке.
    requestedProductRef.current = ctx.productId
    if (!requiresHonestSign) {
      // Лента у обычного товара фиксированная — один ШК, без Честного знака.
      // Но состав этикетки всё равно принадлежит продавцу: без этого запроса
      // настройка не применялась к большинству товаров, у которых маркировки
      // нет вовсе.
      setLayout(cloneLayout(NON_HONEST_SIGN_LABEL_LAYOUT))
      void (async () => {
        try {
          const template = await resolvePrintTemplate(ctx.token, {
            productId: ctx.productId,
            sellerId: ctx.sellerId ?? undefined,
          })
          if (requestedProductRef.current !== ctx.productId) return
          if (template.layout.label_options) {
            setLayout({
              ...cloneLayout(NON_HONEST_SIGN_LABEL_LAYOUT),
              label_options: { ...template.layout.label_options },
            })
          }
        } catch {
          // Настройка не загрузилась — печатаем полным составом, как раньше.
        }
      })()
      return
    }
    const defaultPresetId = 'pairs' as const
    const defaultPreset =
      MARKING_PRINT_PRESETS.find((preset) => preset.id === defaultPresetId) ?? MARKING_PRINT_PRESETS[0]
    const defaultTape = expandLayoutToTape(defaultPreset.layout)
    setCzQty(defaultTape.filter((b) => b === 'cz').length)
    setWbQty(defaultTape.filter((b) => b === 'label').length)
    setTapeOrder(defaultTape)
    setLayout(cloneLayout(defaultPreset.layout))
    void (async () => {
      try {
        const template = await resolvePrintTemplate(ctx.token, {
          productId: ctx.productId,
          sellerId: ctx.sellerId ?? undefined,
        })
        // Ответ по прошлому товару не применяем к текущему: диалог могли
        // закрыть и открыть на другом заказе, пока запрос летел.
        if (requestedProductRef.current !== ctx.productId) return
        const matched = MARKING_PRINT_PRESETS.find(
          (preset) =>
            preset.id !== 'custom' &&
            JSON.stringify(preset.layout) === JSON.stringify(template.layout),
        )
        if (matched) {
          const tape = expandLayoutToTape(matched.layout)
          setCzQty(tape.filter((b) => b === 'cz').length)
          setWbQty(tape.filter((b) => b === 'label').length)
          setTapeOrder(tape)
          setLayout(cloneLayout(matched.layout))
        } else {
          const tape = expandLayoutToTape(template.layout)
          setCzQty(tape.filter((b) => b === 'cz').length || 1)
          setWbQty(tape.filter((b) => b === 'label').length)
          setTapeOrder(tape.length > 0 ? tape : buildDefaultTape(1, 0))
          setLayout(cloneLayout(template.layout))
        }
      } catch {
        const tape = expandLayoutToTape(defaultPreset.layout)
        setCzQty(tape.filter((b) => b === 'cz').length)
        setWbQty(tape.filter((b) => b === 'label').length)
        setTapeOrder(tape)
        setLayout(cloneLayout(defaultPreset.layout))
      }
    })()
  }, [open, ctx, requiresHonestSign])

  const reprintLineId = fbsTapeMode ? undefined : ctx?.lineId
  const reprintToken = ctx?.token

  useEffect(() => {
    if (!open) {
      setReprintCodes([])
      setSelectedReprintCodeIds([])
      setReprintCodesLoading(false)
      return
    }
    if (!effectiveReprint || !reprintLineId || !reprintToken) {
      setReprintCodes([])
      setSelectedReprintCodeIds([])
      setReprintCodesLoading(false)
      return
    }

    const controller = new AbortController()
    setReprintCodesLoading(true)
    void (async () => {
      try {
        const res = await fetch(
          apiUrl(`/operations/marking-codes/packaging-task-lines/${reprintLineId}/printed-codes`),
          {
            headers: { Authorization: `Bearer ${reprintToken}` },
            signal: controller.signal,
          },
        )
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          setReprintCodes([])
          setSelectedReprintCodeIds([])
          return
        }
        const data = (await res.json()) as { codes: PrintedCodeOption[] }
        const codes = data.codes ?? []
        setReprintCodes(codes)
        setSelectedReprintCodeIds(codes[0] ? [codes[0].id] : [])
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') {
          return
        }
        setError(e instanceof Error ? e.message : 'Не удалось загрузить напечатанные КМ.')
        setReprintCodes([])
        setSelectedReprintCodeIds([])
      } finally {
        if (!controller.signal.aborted) {
          setReprintCodesLoading(false)
        }
      }
    })()

    return () => {
      controller.abort()
    }
  }, [open, effectiveReprint, reprintLineId, reprintToken])

  const qtyNeed = effectiveReprint
    ? fbsTapeMode
      ? fbsHonestSignOrders.length || fbsTapeOrders.length
      : selectedReprintCodeIds.length > 0
        ? selectedReprintCodeIds.length
        : (ctx?.qtyMarkingPrinted ?? 0)
    : isCatalogSource
      ? catalogPrintQty
      : fbsTapeMode
        ? fbsHonestSignOrders.length || fbsTapeOrders.length
        : (ctx?.qtyNeedPack ?? 0)
  const totalWbLabels = resolveManualWbLabelCount(wbBarcodeQty, printDoubleWbBarcode)
  /**
   * I4/L2 (21.08.2026): в ленте FBS «Количество этикеток» — это копии ШК на ОДИН
   * заказ, и ноль здесь разрешён: тогда в ленту идут только QR заказов.
   * resolveManualWbLabelCount поднимает любое значение до единицы, поэтому для
   * ленты считаем отдельно, не трогая остальные экраны печати.
   */
  const fbsLabelCopiesPerOrder =
    Math.max(0, Math.min(999, Math.floor(Number(wbBarcodeQty) || 0))) * (printDoubleWbBarcode ? 2 : 1)
  const qrOnlyTape = includesOrderQr && layout.units.length === 0
  /** Сколько листов реально уйдёт на принтер лентой FBS без Честного знака. */
  const fbsTapeSheets = fbsTapeMode
    ? qrOnlyTape
      ? fbsTapeOrders.length
      : fbsTapeOrders.length * (fbsLabelCopiesPerOrder + (includesOrderQr ? 1 : 0))
    : 0
  /**
   * PRN-04: printFbsTape (ниже) печатает циклом по заказам — на каждый заказ
   * сначала QR, потом его этикетки. Раньше предпросмотр строил один общий QR +
   * один список «единиц» независимо от заказов, поэтому при нескольких заказах в
   * «Печать всего» показывал не то, что реально уходит на ленту. fbsPreviewOrders —
   * тот же ctx.fbsTape.orders, что видит printFbsTape; fbsPreviewLabelCopies —
   * то же правило числа копий ШК-only этикетки на заказ без ЧЗ (fallbackLabelCopies
   * в printFbsTape). Сама печать этим не затронута.
   */
  const fbsPreviewOrders = includesOrderQr
    ? fbsTapeOrders.map((order) => qrOnlyTape ? { ...order, requiresHonestSign: false } : order)
    : undefined
  const fbsPreviewLabelCopies =
    qrOnlyTape ? 0 : fbsHonestSignOrders.length > 0
      ? Math.max(1, labelCopiesFromLayout(layout))
      : fbsLabelCopiesPerOrder
  const available = ctx?.markingAvailable ?? 0
  const quantitySummaryText = requiresHonestSign
    ? effectiveReprint
      ? fbsTapeMode
        ? `К перепечатке: ${qtyNeed}`
        : `Выбрано для перепечатки: ${selectedReprintCodeIds.length} из ${ctx?.qtyMarkingPrinted ?? 0}`
      : isCatalogSource
        ? `К печати: ${catalogPrintQty} · Доступно в пуле: ${available}`
        : `Нужно: ${qtyNeed} · Доступно в пуле: ${available}`
    : isCatalogSource
      ? `К печати: ${totalWbLabels}`
      : `К упаковке: ${qtyNeed}`
  const shortage = requiresHonestSign && !qrOnlyTape && !effectiveReprint && available < qtyNeed
    ? qtyNeed - available
    : 0
  /**
   * PRN-02: перепечатка ленты FBS не строится по выбору конкретных КМ
   * (`selectedReprintCodeIds` там всегда пуст — построчный список кодов на выбор
   * не используется в fbsTapeMode, см. условие `!fbsTapeMode` ниже у самого списка),
   * поэтому для предпросмотра берём то же количество, что уже показывает счётчик
   * в шапке диалога (qtyNeed уже учитывает fbsTapeMode). Раньше здесь безусловно
   * стоял selectedReprintCodeIds.length, из-за чего в перепечатке FBS предпросмотр
   * ленты получал canPrintCount=0 и превью не строилось вовсе.
   */
  const canPrintCount = qrOnlyTape
    ? fbsTapeOrders.length
    : effectiveReprint
    ? fbsTapeMode
      ? qtyNeed
      : selectedReprintCodeIds.length
    : requiresHonestSign
      ? allowPartial
        ? Math.min(available, qtyNeed)
        : available >= qtyNeed
          ? qtyNeed
          : 0
      : totalWbLabels

  // Превью показывает фактическое количество к печати, но не больше трёх единиц,
  // чтобы при печати полусотни лента не превращалась в простыню. Если единиц больше —
  // подпись под превью честно говорит, что показаны первые три.
  const previewUnitCount = Math.min(Math.max(canPrintCount, 1), 3)

  const previewUnits = useMemo(
    () => qrOnlyTape ? [] : buildTapePreviewUnits(layout, previewUnitCount),
    [layout, previewUnitCount, qrOnlyTape],
  )
  const previewTapeCount = useMemo(
    () => countTapeBlocksFromTape(tapeOrder, previewUnitCount),
    [tapeOrder, previewUnitCount],
  )
  const totalTapeCount = useMemo(
    () => countTapeBlocksFromTape(tapeOrder, canPrintCount),
    [tapeOrder, canPrintCount],
  )
  const forceReprintOnConfirm =
    !separateEnabled &&
    !effectiveReprint &&
    requiresHonestSign &&
    markingAlreadyPrinted &&
    Boolean(ctx?.lineId)

  const reorderTape = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) {
      return
    }
    const next = [...tapeOrder]
    const [item] = next.splice(fromIndex, 1)
    if (!item) {
      return
    }
    next.splice(toIndex, 0, item)
    applyTapeOrder(next)
  }

  type TapePrintOptions = {
    layout: PrintLayout
    size: LabelSize
    closeAfter: boolean
    markDone?: 'cz' | 'wb' | null
    forceReprint?: boolean
  }

  const markSectionDone = (markDone: 'cz' | 'wb' | null) => {
    // ШК — не расходуемый ресурс (в отличие от кодов ЧЗ), поэтому печать ШК
    // никогда не блокируется повторным нажатием; отмечаем «сделано» только для ЧЗ.
    if (markDone === 'cz') {
      setSepCzDone(true)
    }
  }

  /** Физическая печать готовой ленты одним заданием (native PDF, иначе HTML fallback). */
  const deliverTape = async (
    tapeUnits: MarkingTapeUnitInput[],
    printLayout: PrintLayout,
    size: LabelSize,
    closeAfter: boolean,
    markDone: 'cz' | 'wb' | null,
  ) => {
    if (!ctx) {
      return
    }
    let printedNative = false
    try {
      printedNative = await printCzArtifactTape(tapeUnits, printLayout, ctx.token, size)
    } catch {
      // Native PDF иногда не стартует (viewer/блокировка) — ниже HTML fallback.
      printedNative = false
    }
    if (!printedNative) {
      const sections = await buildMarkingTapeSections(tapeUnits, printLayout, selectedProductLabel, {
        authToken: ctx.token,
      })
      await printTapeSections(sections, size)
    }
    markSectionDone(markDone)
    ctx.onPrinted()
    if (closeAfter) {
      onClose()
    }
  }

  const printLabelOnlyTape = async (
    count: number,
    size: LabelSize,
    closeAfter: boolean,
    markDone: 'cz' | 'wb' | null = null,
  ) => {
    if (!ctx || count < 1) {
      return false
    }
    const label: ProductThermalLabelData | null | undefined = selectedProductLabel
    if (!label?.barcode?.trim()) {
      setError('У товара нет штрихкода для печати.')
      return false
    }
    // Состав этикетки принадлежит продавцу и должен действовать одинаково
    // везде: и в ленте ФБС, и здесь — в упаковке, каталоге и раздельной печати.
    printProductThermalLabels(label, count, labelOptionsFromLayout(layout), size)
    markSectionDone(markDone)
    ctx.onPrinted()
    if (closeAfter) {
      onClose()
    }
    return true
  }

  const printFbsTape = async ({
    layout: printLayout,
    size,
    closeAfter,
  }: TapePrintOptions) => {
    if (!ctx?.fbsTape) {
      return false
    }
    const result = await ctx.fbsTape.print({
      layout: printLayout,
      allowPartial,
      reprint: effectiveReprint,
    })
    if (result.shortage > 0 && !allowPartial) {
      setError(`Не хватает ${result.shortage} КМ в пуле.`)
      return false
    }
    if (result.orders.length < 1) {
      const firstError = result.order_errors[0]
      setError(firstError ? firstError.message : 'Нет заказов для печати.')
      return false
    }
    const orderById = new Map(ctx.fbsTape.orders.map((order) => [order.orderId, order]))
    const fallbackLabelCopies = resolveFbsFallbackLabelCopies(
      fbsHonestSignOrders.length > 0,
      printLayout,
      fbsLabelCopiesPerOrder,
      printLayout.units.length === 0 && ctx.fbsTape.includeOrderQr,
    )
    const controller = new AbortController()
    fbsTapeBuildAbortRef.current?.abort()
    fbsTapeBuildAbortRef.current = controller
    setFbsTapeBuildProgress({ completed: 0, total: result.orders.length })

    type BuiltOrder = {
      sections: string[]
      qrAssetToConfirm: FbsTapeAsset | null
      error: { wbOrderId: number; message: string } | null
    }
    let builtOrders: BuiltOrder[]
    try {
      builtOrders = await mapConcurrentlyInOrder(
        result.orders,
        FBS_TAPE_BUILD_CONCURRENCY,
        async (printedOrder, orderIndex): Promise<BuiltOrder> => {
          try {
            throwIfAborted(controller.signal)
            const order = orderById.get(printedOrder.order_id)
            if (!order) {
              throw new Error('Заказ отсутствует в исходном списке печати.')
            }
            const orderSections: string[] = []
            let qrAssetToConfirm: FbsTapeAsset | null = null
            if (ctx.fbsTape?.includeOrderQr) {
              const asset = printedOrder.qr_asset
              if (!asset?.preview_url) {
                throw new Error('QR заказа WB не получен.')
              }
              const qrDataUrl = await fetchAuthorizedImageDataUrl(
                ctx.token,
                asset.preview_url,
                controller.signal,
              )
              orderSections.push(buildWbOrderQrLabelHtml(qrDataUrl, orderIndex + 1))
              if (!asset.applied_at) {
                qrAssetToConfirm = asset
              }
            }
            if (printedOrder.requires_honest_sign) {
              if (printedOrder.printed_codes.length > 0) {
                const units: MarkingTapeUnitInput[] = printedOrder.printed_codes.map((code) => ({
                  cis: code.cis_code,
                  codeId: code.id,
                  hasLabelArtifact: code.has_label_artifact,
                  productLabel: order.productLabel,
                }))
                orderSections.push(
                  ...(await buildMarkingTapeSections(units, printLayout, order.productLabel, {
                    authToken: ctx.token,
                    labelSize: size,
                    signal: controller.signal,
                  })),
                )
              }
            } else if (fallbackLabelCopies > 0) {
              orderSections.push(
                ...buildProductLabelSections(
                  order.productLabel,
                  fallbackLabelCopies,
                  size,
                  labelOptionsFromLayout(printLayout),
                ),
              )
            }
            if (orderSections.length === 0) {
              throw new Error('Для заказа не собрано ни одной этикетки.')
            }
            throwIfAborted(controller.signal)
            return { sections: orderSections, qrAssetToConfirm, error: null }
          } catch (cause) {
            if (isAbortError(cause)) throw cause
            return {
              sections: [],
              qrAssetToConfirm: null,
              error: {
                wbOrderId: printedOrder.wb_order_id,
                message: cause instanceof Error ? cause.message : 'Не удалось собрать этикетки.',
              },
            }
          } finally {
            if (!controller.signal.aborted) {
              setFbsTapeBuildProgress((current) =>
                current ? { ...current, completed: current.completed + 1 } : current,
              )
            }
          }
        },
      )

      throwIfAborted(controller.signal)
      const sections = builtOrders.flatMap((order) => order.sections)
      const clientErrors = builtOrders.flatMap((order) => (order.error ? [order.error] : []))
      if (sections.length < 1) {
        setError(clientErrors[0]?.message ?? 'Нет этикеток для печати.')
        return false
      }
      if (fbsTapeBuildAbortRef.current === controller) {
        fbsTapeBuildAbortRef.current = null
        setFbsTapeBuildProgress(null)
      }
      await printTapeSections(sections, size)
      for (const asset of builtOrders.flatMap((order) =>
        order.qrAssetToConfirm ? [order.qrAssetToConfirm] : [],
      )) {
        await ctx.fbsTape.confirmQrApplied(asset)
      }
      ctx.onPrinted()

      const allErrors = [
        ...result.order_errors.map((item) => ({
          wbOrderId: item.wb_order_id,
          message: item.message,
        })),
        ...clientErrors,
      ]
      if (allErrors.length > 0) {
        const numbers = allErrors.slice(0, 12).map((item) => item.wbOrderId).join(', ')
        const tail = allErrors.length > 12 ? ` и ещё ${allErrors.length - 12}` : ''
        setError(
          `Напечатано заказов: ${result.orders.length - clientErrors.length} из ${result.orders.length + result.order_errors.length}. ` +
          `Не попали в ленту: ${numbers}${tail}. Причина по первому: ${allErrors[0].message}. ` +
          'Повторите печать по этим заказам.',
        )
        return false
      }
    } finally {
      if (fbsTapeBuildAbortRef.current === controller) {
        fbsTapeBuildAbortRef.current = null
        setFbsTapeBuildProgress(null)
      }
    }
    if (closeAfter) {
      onClose()
    }
    return true
  }

  const printCatalogTape = async ({
    layout: printLayout,
    size,
    closeAfter,
    markDone = null,
  }: TapePrintOptions) => {
    if (!ctx || canPrintCount < 1) {
      return false
    }
    const barcodeError = resolveProductTapeBarcodeError(barcodeOptions, selectedProductLabel?.barcode, printLayout)
    if (barcodeError) {
      setError(barcodeError)
      return false
    }
    const res = await fetch(
      apiUrl(`/operations/marking-codes/products/${ctx.productId}/print`),
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${ctx.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          quantity: canPrintCount,
          layout_json: printLayout,
          allow_partial: allowPartial,
        }),
      },
    )
    if (!res.ok) {
      setError(await readApiErrorMessage(res))
      return false
    }
    const data = (await res.json()) as {
      codes: string[]
      duplicate_copies: number
      quantity: number
      shortage: number | null
      layout: PrintLayout
      printed_codes?: {
        id: string
        cis_code: string
        has_label_artifact: boolean
      }[]
    }
    if (data.quantity < 1) {
      setError(
        data.shortage
          ? `Не хватает ${data.shortage} КМ в пуле.`
          : 'Нет доступных КМ для печати.',
      )
      return false
    }
    const printedByCis = new Map(
      (data.printed_codes ?? []).map((row) => [row.cis_code, row]),
    )
    await deliverTape(
      data.codes.map((cis) => {
        const meta = printedByCis.get(cis)
        return {
          cis,
          codeId: meta?.id,
          hasLabelArtifact: meta?.has_label_artifact ?? false,
          productLabel: selectedProductLabel ?? null,
        }
      }),
      data.layout ?? printLayout,
      size,
      closeAfter,
      markDone,
    )
    return true
  }

  const printLineTape = async ({
    layout: printLayout,
    size,
    closeAfter,
    markDone = null,
    forceReprint = false,
  }: TapePrintOptions) => {
    if (!ctx?.lineId) {
      setError('Нет строки упаковки для печати КМ.')
      return false
    }
    const barcodeError = resolveProductTapeBarcodeError(barcodeOptions, selectedProductLabel?.barcode, printLayout)
    if (barcodeError) {
      setError(barcodeError)
      return false
    }
    const requestReprint = effectiveReprint || forceReprint
    const res = await fetch(
      apiUrl(`/operations/marking-codes/packaging-lines/${ctx.lineId}/print`),
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${ctx.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          layout_json: printLayout,
          allow_partial: allowPartial,
          reprint: requestReprint,
          ...(requestReprint && selectedReprintCodeIds.length > 0
            ? { code_ids: selectedReprintCodeIds }
            : {}),
        }),
      },
    )
    if (!res.ok) {
      setError(await readApiErrorMessage(res))
      return false
    }
    const data = (await res.json()) as {
      codes: string[]
      duplicate_copies: number
      quantity: number
      shortage: number | null
      layout: PrintLayout
      printed_codes?: {
        id: string
        cis_code: string
        has_label_artifact: boolean
      }[]
    }
    if (data.quantity < 1) {
      setError(
        data.shortage
          ? `Не хватает ${data.shortage} КМ в пуле.`
          : 'Нет доступных КМ для печати.',
      )
      return false
    }
    const printedByCis = new Map(
      (data.printed_codes ?? []).map((row) => [row.cis_code, row]),
    )
    await deliverTape(
      data.codes.map((cis) => {
        const meta = printedByCis.get(cis)
        return {
          cis,
          codeId: meta?.id,
          hasLabelArtifact: meta?.has_label_artifact ?? false,
          productLabel: selectedProductLabel ?? null,
        }
      }),
      data.layout ?? printLayout,
      size,
      closeAfter,
      markDone,
    )
    return true
  }

  // При раздельном режиме одиночные ветки используют свой скоуп размера:
  // перепечатка ЧЗ — размер ЧЗ, печать без ЧЗ — размер ШК ВБ.
  const nonCzPrintSize = separateEnabled ? wbLabelSize : labelSize
  const reprintPrintSize = czTapePrintSize

  const handlePrint = async (opts?: { forceReprint?: boolean }) => {
    if (!ctx) {
      return
    }
    const forceReprint = opts?.forceReprint ?? false
    if (requiresHonestSign) {
      beginPrintUserGesture()
    }
    onBusyChange(true)
    setError(null)
    try {
      if (ctx.fbsTape) {
        // I4 (20.08.2026): 155 заказов уже уезжали на принтер как 22 тысячи листов.
        // Пока нет нормального окна подтверждения из ui-kit — спрашиваем прямо здесь,
        // но только когда лента действительно большая.
        if (fbsTapeSheets > 100 && !window.confirm(
          `На печать уйдёт ${fbsTapeSheets} листов. Продолжить?`,
        )) {
          return
        }
        // PRN-05 (18.08.2026): для пачки, где ни одному заказу не нужен Честный знак,
        // размер надо брать тот, который оператор реально видит и меняет в поле
        // «Размер ШК ВБ» (nonCzPrintSize). czTapePrintSize читает другое хранилище,
        // которое в этой ветке не показывается, — оператор выбирал 60×80, а
        // печаталось 58×40. Соседняя ветка одиночной печати без ЧЗ (ниже) уже
        // использует nonCzPrintSize, приводим ленту к тому же правилу.
        await printFbsTape({
          layout,
          size: requiresHonestSign ? czTapePrintSize : nonCzPrintSize,
          closeAfter: true,
        })
      } else if (!requiresHonestSign) {
        if (wbBarcodeQty >= 1) {
          await printLabelOnlyTape(totalWbLabels, nonCzPrintSize, true)
        }
      } else if (!ctx.lineId && !effectiveReprint && !forceReprint) {
        await printCatalogTape({ layout, size: czTapePrintSize, closeAfter: true })
      } else {
        await printLineTape({
          layout,
          size: effectiveReprint || forceReprint ? reprintPrintSize : czTapePrintSize,
          closeAfter: true,
          forceReprint,
        })
      }
    } catch (e) {
      setError(
        isAbortError(e)
          ? 'Сборка ленты отменена.'
          : e instanceof Error
          ? e.message
          : requiresHonestSign
            ? 'Не удалось напечатать ЧЗ.'
            : 'Не удалось напечатать этикетки.',
      )
    } finally {
      onBusyChange(false)
    }
  }

  /** Раздельный режим: суммарные объёмы по секциям. */
  const sepCzLayout: PrintLayout = {
    units: [{ block: 'cz', copies: Math.max(1, sepCzQty) }],
  }
  const sepCzTotal = canPrintCount * Math.max(1, sepCzQty)
  const sepWbTotal = resolveManualWbLabelCount(sepWbQty, printDoubleWbBarcode)

  const handleSeparateCzPrint = async () => {
    if (!ctx) {
      return
    }
    if (canOpenInlineReprint) {
      setInlineReprint(true)
      return
    }
    if (canPrintCount < 1) {
      return
    }
    beginPrintUserGesture()
    onBusyChange(true)
    setError(null)
    try {
      const opts: TapePrintOptions = {
        layout: sepCzLayout,
        size: resolvedCzPrintSize,
        closeAfter: false,
        markDone: 'cz',
      }
      if (ctx.lineId) {
        await printLineTape(opts)
      } else {
        await printCatalogTape(opts)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать ЧЗ.')
    } finally {
      onBusyChange(false)
    }
  }

  const handleSeparateWbPrint = async () => {
    if (!ctx || sepWbTotal < 1) {
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      await printLabelOnlyTape(sepWbTotal, wbLabelSize, false, 'wb')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетки.')
    } finally {
      onBusyChange(false)
    }
  }

  /** FBS-10: оператор переключает конструктор «вместе / раздельно» прямо на форме печати. */
  const handleSeparateModeToggle = (next: boolean) => {
    setSeparateModeChoice(next)
    setSeparateMarkingPrintEnabled(next)
  }

  const printDisabled =
    busy ||
    (fbsTapeMode && fbsTapeOrders.length < 1) ||
    (effectiveReprint &&
      !fbsTapeMode &&
      requiresHonestSign &&
      (reprintCodesLoading || selectedReprintCodeIds.length < 1)) ||
    (!effectiveReprint && qtyNeed < 1) ||
    (requiresHonestSign && !qrOnlyTape && !effectiveReprint && !forceReprintOnConfirm && available < 1) ||
    (requiresHonestSign && !qrOnlyTape && !effectiveReprint && !forceReprintOnConfirm && !allowPartial && shortage > 0) ||
    // L2 (21.08.2026): ноль этикеток ШК — не повод гасить кнопку, если в ленту всё равно
    // идут QR заказов. Гасим, только когда печатать действительно нечего. Считаем по
    // fbsLabelCopiesPerOrder: totalWbLabels проходит через clampPackUnits и никогда не
    // бывает меньше единицы, поэтому проверять его тут бессмысленно.
    (!requiresHonestSign && !includesOrderQr && fbsTapeMode && fbsLabelCopiesPerOrder < 1) ||
    (!requiresHonestSign && !fbsTapeMode && totalWbLabels < 1)

  const dialogTitle = effectiveReprint
    ? 'Повторная печать'
    : includesOrderQr
      ? requiresHonestSign
        ? 'Печать ЧЗ, ШК и QR заказа'
        : 'Печать ШК и QR заказа'
      : requiresHonestSign
        ? 'Печать ЧЗ'
        : isOzonBarcode ? 'Печать ШК Ozon' : 'Печать ШК ВБ'

  return (
    <>
      <Dialog
        open={open}
        onClose={() => {
          if (!busy) {
            onClose()
          }
        }}
        maxWidth="md"
        fullWidth
        data-testid="marking-print-dialog"
      >
        <DialogTitle>{dialogTitle}</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 0.5 }}>
            {barcodeOptions && barcodeOptions.length > 1 && !effectiveReprint ? (
              <TextField select fullWidth size="small" label="Площадка и штрихкод"
                value={selectedBarcode ? `${selectedBarcode.marketplace}:${selectedBarcode.barcode}` : ''}
                disabled={busy}
                onChange={(event) => setProductBarcodeKey(event.target.value)}
                data-testid="marking-print-product-barcode-select">
                {barcodeOptions.map((option) => (
                  <MenuItem key={`${option.marketplace}:${option.barcode}`} value={`${option.marketplace}:${option.barcode}`}>
                    {option.marketplace === 'ozon' ? 'Ozon' : 'WB'} · {option.barcode}
                  </MenuItem>
                ))}
              </TextField>
            ) : null}
            {ctx ? (
              <Box data-testid="marking-print-header">
                <Typography variant="subtitle2">{ctx.productName}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {ctx.skuCode}
                  {ctx.documentNumber ? ` · ${ctx.documentNumber}` : ''}
                </Typography>
                <Typography variant="body2" data-testid="marking-print-qty">
                  {quantitySummaryText}
                </Typography>
              </Box>
            ) : null}

            {requiresHonestSign && !effectiveReprint && !fbsTapeMode && !separateModeResolving ? (
              <Box data-testid="marking-print-mode-toggle" data-task-id="FBS-10">
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                  {isOzonBarcode ? 'Как печатать ЧЗ и ШК Ozon' : 'Как печатать ЧЗ и ШК ВБ'}
                </Typography>
                <ToggleButtonGroup
                  exclusive
                  size="small"
                  value={separateEnabled ? 'separate' : 'joint'}
                  onChange={(_event, next: 'joint' | 'separate' | null) => {
                    if (!next) {
                      return
                    }
                    handleSeparateModeToggle(next === 'separate')
                  }}
                  disabled={busy}
                  data-testid="marking-print-mode-toggle-group"
                >
                  <ToggleButton value="joint" data-testid="marking-print-mode-joint">
                    Вместе на одной ленте
                  </ToggleButton>
                  <ToggleButton value="separate" data-testid="marking-print-mode-separate">
                    Раздельно: ЧЗ и ШК отдельно
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>
            ) : null}

            {separateMode || separateModeResolving ? null : separateEnabled && !requiresHonestSign ? (
              <LabelSizeSelect
                value={wbLabelSize.id}
                onChange={setWbLabelSize}
                disabled={busy}
                scope="label"
                label={isOzonBarcode ? "Размер ШК Ozon" : "Размер ШК ВБ"}
                testId="marking-print-label-size"
              />
            ) : separateEnabled && effectiveReprint ? (
              <LabelSizeSelect
                value={czLabelSize.id}
                onChange={setCzLabelSize}
                disabled={busy}
                scope="cz"
                label="Размер ЧЗ"
                testId="marking-print-label-size"
              />
            ) : (
              <LabelSizeSelect
                value={labelSize.id}
                onChange={setLabelSize}
                disabled={busy}
                testId="marking-print-label-size"
              />
            )}

            {!effectiveReprint && requiresHonestSign && !separateMode && !separateModeResolving ? (
              <ToggleButtonGroup
                exclusive
                size="small"
                value={czPrintOrientation}
                onChange={(_event, next: LabelPrintOrientation | null) => {
                  if (!next) {
                    return
                  }
                  setCzPrintOrientation(next)
                  saveLabelPrintOrientation(next)
                }}
                disabled={busy}
                data-testid="marking-print-orientation"
              >
                <ToggleButton value="portrait">Вертикальная</ToggleButton>
                <ToggleButton value="landscape">Горизонтальная</ToggleButton>
              </ToggleButtonGroup>
            ) : null}

            {separateModeResolving ? (
              <Typography
                variant="body2"
                color="text.secondary"
                data-testid="marking-print-separate-loading"
              >
                Проверяем настройку раздельной печати…
              </Typography>
            ) : null}

            {shortage > 0 && !forceReprintOnConfirm && !separateMode ? (
              <Alert severity="error" data-testid="marking-print-shortage-banner">
                Не хватает {shortage} из {qtyNeed} КМ
              </Alert>
            ) : null}

            {effectiveReprint && requiresHonestSign && !fbsTapeMode ? (
              <Alert severity="warning" data-testid="marking-print-reprint-notice">
                Повторная печать ЧЗ: выберите все или конкретные КМ, которые нужно напечатать ещё раз.
              </Alert>
            ) : null}

            {!effectiveReprint && requiresHonestSign && markingAlreadyPrinted ? (
              <Alert severity="warning" data-testid="marking-print-already-printed-warning">
                ЧЗ по этой строке уже печатался ранее. Повторная печать выпустит те же КМ.
              </Alert>
            ) : null}

            {!effectiveReprint && !forceReprintOnConfirm && shortage > 0 && available > 0 ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={allowPartial}
                    onChange={(e) => setAllowPartial(e.target.checked)}
                    data-testid="marking-print-allow-partial"
                  />
                }
                label={`Печатать доступные ${available}`}
              />
            ) : null}

            {!effectiveReprint && !requiresHonestSign ? (
              <>
                <PrintQuantityField
                  size="small"
                  label={fbsTapeMode ? `${productBarcodeName} на заказ` : 'Количество этикеток'}
                  helperText={
                    fbsTapeMode
                      ? '0 — печатать ленту только с QR заказов'
                      : undefined
                  }
                  value={wbBarcodeQty}
                  onChange={setWbBarcodeQty}
                  min={fbsTapeMode ? 0 : 1} max={999}
                  data-testid="marking-print-wb-qty"
                  sx={{ maxWidth: 280 }}
                />
                <Box>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={printDoubleWbBarcode}
                        onChange={(e) => setPrintDoubleWbBarcode(e.target.checked)}
                        data-testid="marking-print-wb-double"
                      />
                    }
                    label="Печатать 2 ШК"
                  />
                  {printDoubleWbBarcode ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 4 }}>
                      × 2 к введённому количеству — итого {totalWbLabels} шт.
                    </Typography>
                  ) : null}
                </Box>
                <Box sx={{ mt: 1 }}>
                  <MarkingLabelPreview
                    variant="product"
                    productLabel={selectedProductLabel ?? null}
                    size={nonCzPrintSize}
                    unitsToShow={Math.max(1, totalWbLabels)}
                    totalUnits={Math.max(1, totalWbLabels)}
                    showOrderQr={includesOrderQr}
                    fbsOrders={fbsPreviewOrders}
                    fbsNonHonestLabelCopies={fbsPreviewLabelCopies}
                    printOptions={labelOptionsFromLayout(layout)}
                    testId="marking-print-wb-only-preview"
                  />
                </Box>
              </>
            ) : null}

            {separateMode ? (
              <>
                {isCatalogSource ? (
                  <PrintQuantityField
                    size="small"
                    label="Количество товаров"
                    value={catalogPrintQty}
                    onChange={setCatalogPrintQty}
                    disabled={busy || sepCzDone}
                    min={1} max={999}
                    data-testid="marking-print-catalog-qty"
                    sx={{ maxWidth: 220 }}
                  />
                ) : null}

                <Paper
                  variant="outlined"
                  sx={{ p: 2.5 }}
                  data-testid="marking-print-separate-cz"
                  data-task-id="FBS-10"
                >
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Честный знак
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                    <PrintQuantityField
                      size="small"
                      label="ЧЗ на единицу"
                      value={sepCzQty}
                      onChange={setSepCzQty}
                      disabled={busy || sepCzDone}
                      min={1} max={99}
                      data-testid="marking-print-sep-cz-qty"
                      sx={{ width: 140 }}
                    />
                    <LabelSizeSelect
                      value={czLabelSize.id}
                      onChange={setCzLabelSize}
                      disabled={busy || sepCzDone}
                      scope="cz"
                      label="Размер ЧЗ"
                      testId="marking-print-cz-label-size"
                    />
                    <ToggleButtonGroup
                      exclusive
                      size="small"
                      value={czPrintOrientation}
                      onChange={(_event, next: LabelPrintOrientation | null) => {
                        if (!next) {
                          return
                        }
                        setCzPrintOrientation(next)
                        saveLabelPrintOrientation(next)
                      }}
                      disabled={busy || sepCzDone}
                      data-testid="marking-print-cz-orientation"
                    >
                      <ToggleButton value="portrait">Вертикальная</ToggleButton>
                      <ToggleButton value="landscape">Горизонтальная</ToggleButton>
                    </ToggleButtonGroup>
                    <Button
                      variant="contained"
                      disabled={busy || sepCzDone || (!canOpenInlineReprint && canPrintCount < 1)}
                      onClick={() => void handleSeparateCzPrint()}
                      data-testid="marking-print-sep-cz-print"
                    >
                      {sepCzDone ? 'ЧЗ напечатаны ✓' : 'Печать ЧЗ'}
                    </Button>
                  </Stack>
                  {canPrintCount > 0 ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 0.75, display: 'block' }}
                      data-testid="marking-print-sep-cz-total"
                    >
                      К печати: {sepCzTotal} ЧЗ ({canPrintCount} ед. × {Math.max(1, sepCzQty)})
                    </Typography>
                  ) : !canOpenInlineReprint && !sepCzDone ? (
                    <Typography
                      variant="caption"
                      color="error"
                      sx={{ mt: 0.75, display: 'block' }}
                      data-testid="marking-print-sep-cz-disabled-reason"
                      data-task-id="FBS-10"
                    >
                      {available < 1
                        ? 'Печать ЧЗ недоступна: в пуле нет свободных кодов маркировки. Пополните пул или обратитесь к администратору.'
                        : `Печать ЧЗ недоступна: нужно ${qtyNeed} КМ, в пуле доступно только ${available}. Включите «Печатать доступные» или пополните пул.`}
                    </Typography>
                  ) : null}
                  <Box sx={{ mt: 1.5 }}>
                    <MarkingLabelPreview
                      variant="tape"
                      layout={sepCzLayout}
                      size={resolvedCzPrintSize}
                      unitsToShow={1}
                      productLabel={null}
                      testId="marking-print-sep-cz-preview"
                    />
                  </Box>
                </Paper>

                <Paper
                  variant="outlined"
                  sx={{ p: 2.5 }}
                  data-testid="marking-print-separate-wb"
                  data-task-id="FBS-10"
                >
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    {productBarcodeName}
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                    <PrintQuantityField
                      size="small"
                      label="Количество этикеток"
                      value={sepWbQty}
                      onChange={setSepWbQty}
                      disabled={busy}
                      min={1} max={999}
                      data-testid="marking-print-sep-wb-qty"
                      sx={{ width: 180 }}
                    />
                    <Box>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={printDoubleWbBarcode}
                            onChange={(e) => setPrintDoubleWbBarcode(e.target.checked)}
                            disabled={busy}
                            data-testid="marking-print-sep-wb-double"
                          />
                        }
                        label="Печатать 2 ШК"
                      />
                      {printDoubleWbBarcode ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 4 }}>
                          × 2 к введённому количеству — итого {sepWbTotal} шт.
                        </Typography>
                      ) : null}
                    </Box>
                    <LabelSizeSelect
                      value={wbLabelSize.id}
                      onChange={setWbLabelSize}
                      disabled={busy}
                      scope="label"
                      label={isOzonBarcode ? "Размер ШК Ozon" : "Размер ШК ВБ"}
                      testId="marking-print-wb-label-size"
                    />
                    <Button
                      variant="contained"
                      disabled={busy || sepWbTotal < 1}
                      onClick={() => void handleSeparateWbPrint()}
                      data-testid="marking-print-sep-wb-print"
                    >
                      {/* Печать ШК — не расходуемый ресурс (в отличие от кодов ЧЗ), поэтому
                          кнопка не блокируется после первой печати: повторная печать должна
                          работать сколько угодно раз. */}
                      {isOzonBarcode ? 'Печать ШК Ozon' : 'Печать ШК ВБ'}
                    </Button>
                  </Stack>
                  {sepWbTotal > 0 ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 0.75, display: 'block' }}
                      data-testid="marking-print-sep-wb-total"
                    >
                      К печати: {sepWbTotal} {productBarcodeName}
                      {printDoubleWbBarcode ? ' (× 2)' : ''}
                    </Typography>
                  ) : null}
                  <Box sx={{ mt: 1.5 }}>
                    <MarkingLabelPreview
                      variant="product"
                      size={wbLabelSize}
                      unitsToShow={Math.max(1, sepWbTotal)}
                      totalUnits={Math.max(1, sepWbTotal)}
                      productLabel={selectedProductLabel ?? null}
                      printOptions={labelOptionsFromLayout(layout)}
                      testId="marking-print-sep-wb-preview"
                    />
                  </Box>
                </Paper>
              </>
            ) : null}

            {/*
              PRN-02: в перепечатке ленты FBS (`fbsTapeMode && effectiveReprint`) построчный
              список кодов на выбор ниже не рендерится (он завязан на `!fbsTapeMode` — для
              ленты нет самой концепции «выбрать конкретный код»), поэтому единственная ветка
              предпросмотра, которая вообще что-то показывает — эта, обычно предназначенная
              только для первой печати. Раньше её тоже закрывало условие `!effectiveReprint`,
              и в итоге окно перепечатки ленты FBS оставалось пустым — ни ленты, ни QR заказа,
              ни ЧЗ/ШК, только счётчик количества в шапке. Показываем эту же ветку и в
              перепечатке ленты FBS: то же самое, что видит оператор при первой печати —
              что уходит на принтер (printFbsTape ниже), эта правка не меняет.
            */}
            {(!effectiveReprint || fbsTapeMode) && requiresHonestSign && !separateMode && !separateModeResolving ? (
              <>
                {isCatalogSource ? (
                  <PrintQuantityField
                    size="small"
                    label="Количество товаров"
                    value={catalogPrintQty}
                    onChange={setCatalogPrintQty}
                    min={1} max={999}
                    data-testid="marking-print-catalog-qty"
                    sx={{ maxWidth: 220 }}
                  />
                ) : null}

                <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap' }}>
                  <PrintQuantityField
                    size="small"
                    label="ЧЗ"
                    value={czQty}
                    onChange={(next) => applyTapeCounts(next, wbQty)}
                    min={0} max={99}
                    data-testid="marking-print-cz-qty"
                    sx={{ width: 120 }}
                  />
                  <PrintQuantityField
                    size="small"
                    label={productBarcodeName}
                    value={wbQty}
                    onChange={(next) => applyTapeCounts(czQty, next)}
                    min={0} max={99}
                    data-testid="marking-print-wb-qty"
                    sx={{ width: 120 }}
                  />
                </Stack>

                <Box data-testid="marking-print-tape">
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mb: 0.5, display: 'block' }}
                    data-testid="marking-print-preview-tape-count"
                  >
                    Лента на одну единицу · {tapeOrder.length} {plural(tapeOrder.length, ['блок', 'блока', 'блоков'])}
                    {canPrintCount > previewUnitCount
                      ? ` · ниже показаны первые ${previewUnitCount} ед. из ${canPrintCount}`
                      : ` · ниже вся лента: ${previewTapeCount} ${plural(previewTapeCount, ['блок', 'блока', 'блоков'])} на ${canPrintCount} ед.`}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={0.5}
                    sx={{ flexWrap: 'wrap', alignItems: 'center', minHeight: 32 }}
                  >
                    {tapeOrder.map((block, index) => (
                      <Chip
                        key={`${block}-${index}`}
                        size="small"
                        label={blockLabel(block)}
                        variant="outlined"
                        draggable
                        onDragStart={() => setDragTapeIndex(index)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={() => {
                          if (dragTapeIndex !== null) {
                            reorderTape(dragTapeIndex, index)
                          }
                          setDragTapeIndex(null)
                        }}
                        onDragEnd={() => setDragTapeIndex(null)}
                        sx={{
                          cursor: 'grab',
                          opacity: dragTapeIndex === index ? 0.45 : 1,
                        }}
                        data-testid={`marking-print-tape-item-${index}`}
                      />
                    ))}
                  </Stack>
                </Box>

                <Box data-testid="marking-print-preview">
                  {previewUnits.map((unit) => (
                    <Stack
                      key={unit.unitIndex}
                      direction="row"
                      spacing={0.5}
                      sx={{ mb: 0.5, flexWrap: 'wrap', alignItems: 'center' }}
                      data-testid={`marking-print-preview-unit-${unit.unitIndex}`}
                    >
                      <Typography variant="caption" sx={{ minWidth: 52 }}>
                        Ед. {unit.unitIndex}:
                      </Typography>
                      {unit.blocks.map((label, bi) => (
                        <Chip
                          key={`${unit.unitIndex}-${bi}`}
                          size="small"
                          label={label}
                          variant="outlined"
                          data-testid={`marking-print-preview-chip-${unit.unitIndex}-${bi}`}
                        />
                      ))}
                      <Typography variant="caption" color="text.secondary">
                        (КМ {unit.codeHint})
                      </Typography>
                    </Stack>
                  ))}
                </Box>

                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                    Реальный макет ленты
                  </Typography>
                  <MarkingLabelPreview
                    variant="tape"
                    layout={layout}
                    size={czTapePrintSize}
                    unitsToShow={previewUnitCount}
                    totalUnits={canPrintCount}
                    productLabel={selectedProductLabel ?? null}
                    showOrderQr={includesOrderQr}
                    fbsOrders={fbsPreviewOrders}
                    fbsNonHonestLabelCopies={fbsPreviewLabelCopies}
                    testId="marking-print-tape-preview"
                  />
                </Box>
              </>
            ) : null}

            {effectiveReprint && requiresHonestSign && !fbsTapeMode ? (
              reprintCodesLoading ? (
                <Typography variant="body2" color="text.secondary">
                  Загрузка напечатанных КМ…
                </Typography>
              ) : reprintCodes.length < 1 ? (
                <Alert severity="warning" data-testid="marking-reprint-no-codes">
                  Нет напечатанных КМ для перепечатки
                </Alert>
              ) : (
                <Box data-testid="marking-reprint-pick-list">
                  <Stack direction="row" spacing={1} sx={{ mb: 0.5 }}>
                    <Button
                      size="small"
                      disabled={busy || selectedReprintCodeIds.length === reprintCodes.length}
                      onClick={() => setSelectedReprintCodeIds(reprintCodes.map((c) => c.id))}
                      data-testid="marking-reprint-pick-all"
                    >
                      Выбрать все
                    </Button>
                    <Button
                      size="small"
                      disabled={busy || selectedReprintCodeIds.length < 1}
                      onClick={() => setSelectedReprintCodeIds([])}
                      data-testid="marking-reprint-pick-none"
                    >
                      Снять всё
                    </Button>
                  </Stack>
                  {reprintCodes.map((code) => (
                    <FormControlLabel
                      key={code.id}
                      sx={{ display: 'flex' }}
                      control={
                        <Checkbox
                          size="small"
                          value={code.id}
                          checked={selectedReprintCodeIds.includes(code.id)}
                          onChange={(e) =>
                            setSelectedReprintCodeIds((prev) =>
                              e.target.checked
                                ? [...prev, code.id]
                                : prev.filter((id) => id !== code.id),
                            )
                          }
                          data-testid={`marking-reprint-pick-${code.id}`}
                        />
                      }
                      label={code.cis_masked}
                    />
                  ))}
                </Box>
              )
            ) : null}

            {effectiveReprint && requiresHonestSign && !fbsTapeMode && selectedReprintCodeIds.length > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К перепечатке: {selectedReprintCodeIds.length} КМ
              </Typography>
            ) : null}

            {!effectiveReprint && requiresHonestSign && !separateMode && canPrintCount > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {canPrintCount} ед. · {czQty * canPrintCount} ЧЗ + {wbQty * canPrintCount} {productBarcodeName} ·{' '}
                {totalTapeCount} {plural(totalTapeCount, ['блок', 'блока', 'блоков'])} в ленте
              </Typography>
            ) : null}

            {!effectiveReprint && !requiresHonestSign && fbsTapeMode ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {fbsTapeOrders.length} {plural(fbsTapeOrders.length, ['заказ', 'заказа', 'заказов'])} ·{' '}
                {includesOrderQr ? `${fbsTapeOrders.length} QR + ` : ''}
                {fbsTapeOrders.length * fbsLabelCopiesPerOrder} ШК ВБ · итого {fbsTapeSheets}{' '}
                {plural(fbsTapeSheets, ['лист', 'листа', 'листов'])}
              </Typography>
            ) : null}

            {!effectiveReprint && !requiresHonestSign && !fbsTapeMode && totalWbLabels > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {totalWbLabels} {productBarcodeName}{printDoubleWbBarcode ? ' (× 2)' : ''}
              </Typography>
            ) : null}

            {error ? (
              <Alert severity="error" data-testid="marking-print-error">
                {error}
              </Alert>
            ) : null}

            {fbsTapeBuildProgress ? (
              <Box data-testid="marking-print-build-progress">
                <Typography variant="body2" sx={{ mb: 0.75 }}>
                  Собрано {fbsTapeBuildProgress.completed} из {fbsTapeBuildProgress.total}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={
                    fbsTapeBuildProgress.total > 0
                      ? (fbsTapeBuildProgress.completed / fbsTapeBuildProgress.total) * 100
                      : 0
                  }
                />
              </Box>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          {separateModeResolving ? (
            <Button onClick={onClose} disabled={busy}>
              Отмена
            </Button>
          ) : separateMode ? (
            <Button onClick={onClose} disabled={busy} data-testid="marking-print-separate-close">
              Закрыть
            </Button>
          ) : (
            <>
              <Button
                onClick={() => {
                  if (fbsTapeBuildProgress) {
                    fbsTapeBuildAbortRef.current?.abort()
                    return
                  }
                  onClose()
                }}
                disabled={busy && !fbsTapeBuildProgress}
                data-testid={
                  fbsTapeBuildProgress ? 'marking-print-cancel-build' : undefined
                }
              >
                {fbsTapeBuildProgress ? 'Отменить сборку' : 'Отмена'}
              </Button>
              <Button
                variant="contained"
                disabled={printDisabled}
                onClick={() => void handlePrint({ forceReprint: forceReprintOnConfirm })}
                data-testid="marking-print-confirm"
              >
                {effectiveReprint ? 'Перепечатать' : 'Печать'}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </>
  )
}
