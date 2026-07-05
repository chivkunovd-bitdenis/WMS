import { useEffect, useMemo, useState } from 'react'
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
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../api'
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
import { createPrintTemplate, resolvePrintTemplate, type PrintLayout } from '../utils/printTemplate'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'
import {
  buildMarkingTapeSections,
  printTapeSections,
  type MarkingTapeUnitInput,
} from '../utils/printMarkingCodeLabel'
import type { ProductThermalLabelData } from '../utils/printProductThermalLabel'
import { resolvePackUnits, resolveWbBarcodeLabelCount } from '../utils/productBarcodePrint'
import { resolveLabelSize, loadLabelSizeId, type LabelSize } from '../utils/labelSize'
import { useSeparateMarkingPrint } from '../utils/separateMarkingPrint'
import { LabelSizeSelect } from './LabelSizeSelect'

type PrintedCodeOption = {
  id: string
  cis_masked: string
  status: string
}

/** Fixed layout for non-ЧЗ: one WB barcode label per unit, no constructor. */
const NON_HONEST_SIGN_LABEL_LAYOUT: PrintLayout = {
  units: [{ block: 'label', copies: 1 }],
}

/**
 * Печать пачками: большие ленты режутся на пачки по столько этикеток,
 * чтобы обрыв ленты терял максимум одну пачку.
 */
const PRINT_CHUNK_SIZE = 20

type ChunkPrintJob = {
  sections: string[]
  size: LabelSize
  printedChunks: number
  closeAfter: boolean
  /** В раздельном режиме какой флаг «напечатано ✓» выставить по завершении. */
  markDone: 'cz' | 'wb' | null
}

export type MarkingPrintContext = {
  token: string
  /** Пустой или отсутствует — печать из каталога/ЧЗ без строки упаковки (client-side). */
  lineId?: string
  source?: 'packaging' | 'catalog'
  productId: string
  documentNumber: string | null
  qtyNeedPack: number
  markingAvailable: number
  qtyMarkingPrinted: number
  requiresHonestSign: boolean
  skuCode: string
  productName: string
  productLabel?: ProductThermalLabelData | null
  packagingInstructions?: string | null
  unitsInPack?: number | null
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

export function MarkingPrintDialog({ open, reprint, ctx, busy, onBusyChange, onClose }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId()))
  const [layout, setLayout] = useState<PrintLayout>(MARKING_PRINT_PRESETS[0].layout)
  const [allowPartial, setAllowPartial] = useState(false)
  const [czQty, setCzQty] = useState(2)
  const [wbQty, setWbQty] = useState(0)
  const [tapeOrder, setTapeOrder] = useState<TapeBlock[]>(buildDefaultTape(2, 0))
  const [dragTapeIndex, setDragTapeIndex] = useState<number | null>(null)
  const [catalogPrintQty, setCatalogPrintQty] = useState(1)
  const [wbBarcodeQty, setWbBarcodeQty] = useState(1)
  const [saveName, setSaveName] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const [reprintCodes, setReprintCodes] = useState<PrintedCodeOption[]>([])
  const [selectedReprintCodeIds, setSelectedReprintCodeIds] = useState<string[]>([])
  const [reprintCodesLoading, setReprintCodesLoading] = useState(false)
  const [chunkJob, setChunkJob] = useState<ChunkPrintJob | null>(null)
  // Раздельная печать ЧЗ и ШК ВБ: свои размеры и свои кнопки на каждый тип этикетки.
  const separateEnabled = useSeparateMarkingPrint()
  const [czLabelSize, setCzLabelSize] = useState<LabelSize>(() =>
    resolveLabelSize(loadLabelSizeId('cz')),
  )
  const [wbLabelSize, setWbLabelSize] = useState<LabelSize>(() =>
    resolveLabelSize(loadLabelSizeId('label')),
  )
  const [sepCzQty, setSepCzQty] = useState(2)
  const [sepWbQty, setSepWbQty] = useState(1)
  const [sepCzDone, setSepCzDone] = useState(false)
  const [sepWbDone, setSepWbDone] = useState(false)

  const requiresHonestSign = ctx?.requiresHonestSign ?? true
  const isCatalogSource = ctx?.source === 'catalog'
  /** Раздельный режим: только для товаров с ЧЗ и не для перепечатки (там печатается один ЧЗ). */
  const separateMode = separateEnabled && requiresHonestSign && !reprint

  const applyTapeCounts = (nextCz: number, nextWb: number) => {
    const cz = Math.max(0, Math.min(99, Math.floor(nextCz) || 0))
    const wb = Math.max(0, Math.min(99, Math.floor(nextWb) || 0))
    const tape = buildDefaultTape(cz > 0 || wb > 0 ? cz : 1, wb)
    setCzQty(cz > 0 || wb > 0 ? cz : 1)
    setWbQty(wb)
    setTapeOrder(tape)
    setLayout(tapeToLayout(tape))
  }

  const applyTapeOrder = (nextTape: TapeBlock[]) => {
    setTapeOrder(nextTape)
    setLayout(tapeToLayout(nextTape))
    setCzQty(nextTape.filter((b) => b === 'cz').length)
    setWbQty(nextTape.filter((b) => b === 'label').length)
  }

  useEffect(() => {
    if (!open || !ctx) {
      return
    }
    setError(null)
    setAllowPartial(false)
    setSaveName('')
    setWbBarcodeQty(1)
    setCatalogPrintQty(1)
    setReprintCodes([])
    setSelectedReprintCodeIds([])
    setReprintCodesLoading(false)
    setDragTapeIndex(null)
    setChunkJob(null)
    setSepCzQty(2)
    setSepWbQty(1)
    setSepCzDone(false)
    setSepWbDone(false)
    setCzLabelSize(resolveLabelSize(loadLabelSizeId('cz')))
    setWbLabelSize(resolveLabelSize(loadLabelSizeId('label')))
    if (!requiresHonestSign) {
      setLayout(cloneLayout(NON_HONEST_SIGN_LABEL_LAYOUT))
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
        const template = await resolvePrintTemplate(ctx.token, { productId: ctx.productId })
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
    if (reprint && ctx.lineId) {
      setReprintCodesLoading(true)
      void (async () => {
        try {
          const res = await fetch(
            apiUrl(`/operations/marking-codes/packaging-task-lines/${ctx.lineId}/printed-codes`),
            { headers: { Authorization: `Bearer ${ctx.token}` } },
          )
          if (!res.ok) {
            setError(await readApiErrorMessage(res))
            setReprintCodes([])
            return
          }
          const data = (await res.json()) as { codes: PrintedCodeOption[] }
          const codes = data.codes ?? []
          setReprintCodes(codes)
          // Один код выбран по умолчанию — типовой случай «порвалась одна этикетка».
          setSelectedReprintCodeIds(codes[0] ? [codes[0].id] : [])
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Не удалось загрузить напечатанные КМ.')
          setReprintCodes([])
        } finally {
          setReprintCodesLoading(false)
        }
      })()
    }
  }, [open, ctx, requiresHonestSign, reprint])

  const qtyNeed = reprint
    ? selectedReprintCodeIds.length > 0
      ? selectedReprintCodeIds.length
      : (ctx?.qtyMarkingPrinted ?? 0)
    : isCatalogSource
      ? catalogPrintQty
      : (ctx?.qtyNeedPack ?? 0)
  const packUnits = useMemo(
    () =>
      resolvePackUnits({
        units_in_pack: ctx?.unitsInPack,
        packaging_instructions: ctx?.packagingInstructions,
      }),
    [ctx?.unitsInPack, ctx?.packagingInstructions],
  )
  const wbLabelMultiplier = isCatalogSource || ctx?.lineId ? wbBarcodeQty : wbBarcodeQty * Math.max(1, qtyNeed)
  const totalWbLabels = resolveWbBarcodeLabelCount(wbLabelMultiplier, packUnits)
  const available = ctx?.markingAvailable ?? 0
  const shortage = requiresHonestSign && !reprint && available < qtyNeed ? qtyNeed - available : 0
  const canPrintCount = reprint
    ? selectedReprintCodeIds.length
    : requiresHonestSign
      ? allowPartial
        ? Math.min(available, qtyNeed)
        : available >= qtyNeed
          ? qtyNeed
          : 0
      : totalWbLabels

  const previewUnits = useMemo(() => buildTapePreviewUnits(layout, 3), [layout])
  const previewTapeCount = useMemo(
    () => countTapeBlocksFromTape(tapeOrder, 3),
    [tapeOrder],
  )
  const totalTapeCount = useMemo(
    () => countTapeBlocksFromTape(tapeOrder, canPrintCount),
    [tapeOrder, canPrintCount],
  )

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
  }

  const markSectionDone = (markDone: 'cz' | 'wb' | null) => {
    if (markDone === 'cz') {
      setSepCzDone(true)
    }
    if (markDone === 'wb') {
      setSepWbDone(true)
    }
  }

  /**
   * Физическая печать готовой ленты: короткая — одним заданием,
   * длинная — пачками через диалог прогресса (данные к этому моменту
   * уже отправлены/списаны, дальше только физика печати).
   */
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
    const sections = await buildMarkingTapeSections(tapeUnits, printLayout, ctx.productLabel, {
      authToken: ctx.token,
    })
    if (sections.length <= PRINT_CHUNK_SIZE) {
      await printTapeSections(sections, size)
      markSectionDone(markDone)
      ctx.onPrinted()
      if (closeAfter) {
        onClose()
      }
      return
    }
    // Данные уже на бэкенде — обновляем родителя сразу, физику печатаем пачками.
    ctx.onPrinted()
    setChunkJob({ sections, size, printedChunks: 0, closeAfter, markDone })
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
    const units = Array.from({ length: count }, (_, index) => ({
      cis: `label-only-${index + 1}`,
      productLabel: ctx.productLabel ?? null,
    }))
    await deliverTape(units, NON_HONEST_SIGN_LABEL_LAYOUT, size, closeAfter, markDone)
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
          productLabel: ctx.productLabel ?? null,
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
  }: TapePrintOptions) => {
    if (!ctx?.lineId) {
      setError('Нет строки упаковки для печати КМ.')
      return false
    }
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
          reprint,
          ...(reprint && selectedReprintCodeIds.length > 0
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
          productLabel: ctx.productLabel ?? null,
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
  const reprintPrintSize = separateEnabled ? czLabelSize : labelSize

  const handlePrint = async () => {
    if (!ctx) {
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      if (!requiresHonestSign) {
        if (wbBarcodeQty >= 1) {
          await printLabelOnlyTape(totalWbLabels, nonCzPrintSize, true)
        }
      } else if (!ctx.lineId && !reprint) {
        await printCatalogTape({ layout, size: labelSize, closeAfter: true })
      } else {
        await printLineTape({
          layout,
          size: reprint ? reprintPrintSize : labelSize,
          closeAfter: true,
        })
      }
    } catch (e) {
      setError(
        e instanceof Error
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
  const sepWbTotal = resolveWbBarcodeLabelCount(
    Math.max(0, sepWbQty) * Math.max(1, qtyNeed),
    packUnits,
  )

  const handleSeparateCzPrint = async () => {
    if (!ctx || canPrintCount < 1) {
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      const opts: TapePrintOptions = {
        layout: sepCzLayout,
        size: czLabelSize,
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

  /** Печать пачками: обработчики диалога прогресса. */
  const chunkTotal = chunkJob ? Math.ceil(chunkJob.sections.length / PRINT_CHUNK_SIZE) : 0

  const printChunk = async (chunkIndex: number) => {
    if (!chunkJob) {
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      const slice = chunkJob.sections.slice(
        chunkIndex * PRINT_CHUNK_SIZE,
        (chunkIndex + 1) * PRINT_CHUNK_SIZE,
      )
      await printTapeSections(slice, chunkJob.size)
      setChunkJob((prev) =>
        prev ? { ...prev, printedChunks: Math.max(prev.printedChunks, chunkIndex + 1) } : prev,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать пачку.')
    } finally {
      onBusyChange(false)
    }
  }

  const finishChunkJob = () => {
    if (!chunkJob) {
      return
    }
    markSectionDone(chunkJob.markDone)
    const { closeAfter } = chunkJob
    setChunkJob(null)
    if (closeAfter) {
      onClose()
    }
  }

  const abortChunkJob = () => {
    setChunkJob(null)
  }

  const handleSaveTemplate = async () => {
    if (!ctx || !saveName.trim()) {
      setError('Укажите название шаблона.')
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      await createPrintTemplate(ctx.token, {
        name: saveName.trim(),
        layout,
        product_id: ctx.productId,
      })
      setToast('Шаблон сохранён')
      setSaveName('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить шаблон.')
    } finally {
      onBusyChange(false)
    }
  }

  const printDisabled =
    busy ||
    (reprint &&
      requiresHonestSign &&
      (reprintCodesLoading || selectedReprintCodeIds.length < 1)) ||
    (!reprint && qtyNeed < 1) ||
    (requiresHonestSign && !reprint && available < 1) ||
    (requiresHonestSign && !reprint && !allowPartial && shortage > 0) ||
    (!requiresHonestSign && totalWbLabels < 1)

  const dialogTitle = reprint
    ? 'Повторная печать'
    : requiresHonestSign
      ? 'Печать ЧЗ'
      : 'Печать ШК ВБ'

  return (
    <>
      <Dialog
        open={open}
        onClose={() => {
          if (!busy) {
            onClose()
          }
        }}
        maxWidth="sm"
        fullWidth
        data-testid="marking-print-dialog"
      >
        <DialogTitle>{dialogTitle}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 0.5 }}>
            {ctx ? (
              <Box data-testid="marking-print-header">
                <Typography variant="subtitle2">{ctx.productName}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {ctx.skuCode}
                  {ctx.documentNumber ? ` · ${ctx.documentNumber}` : ''}
                </Typography>
                <Typography variant="body2" data-testid="marking-print-qty">
                  {requiresHonestSign
                    ? reprint
                      ? `Выбрано для перепечатки: ${selectedReprintCodeIds.length} из ${ctx.qtyMarkingPrinted}`
                      : isCatalogSource
                        ? `К печати: ${catalogPrintQty} · Доступно в пуле: ${available}`
                        : `Нужно: ${qtyNeed} · Доступно в пуле: ${available}`
                    : `К упаковке: ${qtyNeed}`}
                </Typography>
              </Box>
            ) : null}

            {separateMode ? null : separateEnabled && !requiresHonestSign ? (
              <LabelSizeSelect
                value={wbLabelSize.id}
                onChange={setWbLabelSize}
                disabled={busy}
                scope="label"
                label="Размер ШК ВБ"
                testId="marking-print-label-size"
              />
            ) : separateEnabled && reprint ? (
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

            {shortage > 0 ? (
              <Alert severity="error" data-testid="marking-print-shortage-banner">
                Не хватает {shortage} из {qtyNeed} КМ
              </Alert>
            ) : null}

            {!reprint && shortage > 0 ? (
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

            {!reprint && !requiresHonestSign ? (
              <TextField
                size="small"
                label="Количество ШК ВБ"
                type="number"
                value={wbBarcodeQty}
                onChange={(e) =>
                  setWbBarcodeQty(Math.max(1, Math.min(999, Number(e.target.value) || 1)))
                }
                helperText={
                  packUnits > 1
                    ? `× ${packUnits} шт в упаковке → ${totalWbLabels} ШК ВБ`
                    : undefined
                }
                slotProps={{ htmlInput: { min: 1, max: 999 } }}
                data-testid="marking-print-wb-qty"
                sx={{ maxWidth: 280 }}
              />
            ) : null}

            {separateMode ? (
              <>
                {isCatalogSource ? (
                  <TextField
                    size="small"
                    label="Количество товаров"
                    type="number"
                    value={catalogPrintQty}
                    onChange={(e) =>
                      setCatalogPrintQty(Math.max(1, Math.min(999, Number(e.target.value) || 1)))
                    }
                    disabled={busy || sepCzDone}
                    slotProps={{ htmlInput: { min: 1, max: 999 } }}
                    data-testid="marking-print-catalog-qty"
                    sx={{ maxWidth: 220 }}
                  />
                ) : null}

                <Box data-testid="marking-print-separate-cz">
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Честный знак
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      label="ЧЗ на единицу"
                      type="number"
                      value={sepCzQty}
                      onChange={(e) =>
                        setSepCzQty(Math.max(1, Math.min(99, Number(e.target.value) || 1)))
                      }
                      disabled={busy || sepCzDone}
                      slotProps={{ htmlInput: { min: 1, max: 99 } }}
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
                    <Button
                      variant="contained"
                      disabled={busy || sepCzDone || canPrintCount < 1}
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
                      sx={{ mt: 0.5, display: 'block' }}
                      data-testid="marking-print-sep-cz-total"
                    >
                      К печати: {sepCzTotal} ЧЗ ({canPrintCount} ед. × {Math.max(1, sepCzQty)})
                    </Typography>
                  ) : null}
                </Box>

                <Box data-testid="marking-print-separate-wb">
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    ШК ВБ
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                    <TextField
                      size="small"
                      label="ШК ВБ на единицу"
                      type="number"
                      value={sepWbQty}
                      onChange={(e) =>
                        setSepWbQty(Math.max(1, Math.min(99, Number(e.target.value) || 1)))
                      }
                      disabled={busy || sepWbDone}
                      slotProps={{ htmlInput: { min: 1, max: 99 } }}
                      data-testid="marking-print-sep-wb-qty"
                      sx={{ width: 140 }}
                    />
                    <LabelSizeSelect
                      value={wbLabelSize.id}
                      onChange={setWbLabelSize}
                      disabled={busy || sepWbDone}
                      scope="label"
                      label="Размер ШК ВБ"
                      testId="marking-print-wb-label-size"
                    />
                    <Button
                      variant="contained"
                      disabled={busy || sepWbDone || sepWbTotal < 1}
                      onClick={() => void handleSeparateWbPrint()}
                      data-testid="marking-print-sep-wb-print"
                    >
                      {sepWbDone ? 'ШК напечатаны ✓' : 'Печать ШК ВБ'}
                    </Button>
                  </Stack>
                  {sepWbTotal > 0 ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 0.5, display: 'block' }}
                      data-testid="marking-print-sep-wb-total"
                    >
                      К печати: {sepWbTotal} ШК ВБ
                      {packUnits > 1 ? ` (× ${packUnits} шт в упаковке)` : ''}
                    </Typography>
                  ) : null}
                </Box>
              </>
            ) : null}

            {!reprint && requiresHonestSign && !separateMode ? (
              <>
                {isCatalogSource ? (
                  <TextField
                    size="small"
                    label="Количество товаров"
                    type="number"
                    value={catalogPrintQty}
                    onChange={(e) =>
                      setCatalogPrintQty(Math.max(1, Math.min(999, Number(e.target.value) || 1)))
                    }
                    slotProps={{ htmlInput: { min: 1, max: 999 } }}
                    data-testid="marking-print-catalog-qty"
                    sx={{ maxWidth: 220 }}
                  />
                ) : null}

                <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap' }}>
                  <TextField
                    size="small"
                    label="ЧЗ"
                    type="number"
                    value={czQty}
                    onChange={(e) => applyTapeCounts(Number(e.target.value) || 0, wbQty)}
                    slotProps={{ htmlInput: { min: 0, max: 99 } }}
                    data-testid="marking-print-cz-qty"
                    sx={{ width: 120 }}
                  />
                  <TextField
                    size="small"
                    label="ШК ВБ"
                    type="number"
                    value={wbQty}
                    onChange={(e) => applyTapeCounts(czQty, Number(e.target.value) || 0)}
                    slotProps={{ htmlInput: { min: 0, max: 99 } }}
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
                    Лента на одну единицу · {tapeOrder.length} блоков · {previewTapeCount} блоков на 3 ед.
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

                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <TextField
                    size="small"
                    label="Название шаблона"
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                    data-testid="marking-print-save-name"
                    sx={{ flex: 1 }}
                  />
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy || !saveName.trim()}
                    onClick={() => void handleSaveTemplate()}
                    data-testid="marking-print-save-template"
                  >
                    Сохранить
                  </Button>
                </Stack>
              </>
            ) : null}

            {reprint && requiresHonestSign ? (
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

            {reprint && requiresHonestSign && selectedReprintCodeIds.length > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К перепечатке: {selectedReprintCodeIds.length} КМ
              </Typography>
            ) : null}

            {!reprint && requiresHonestSign && !separateMode && canPrintCount > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {canPrintCount} ед. · {totalTapeCount} блоков в ленте
              </Typography>
            ) : null}

            {!reprint && !requiresHonestSign && totalWbLabels > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {totalWbLabels} ШК ВБ
              </Typography>
            ) : null}

            {error ? (
              <Alert severity="error" data-testid="marking-print-error">
                {error}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          {separateMode ? (
            <Button onClick={onClose} disabled={busy} data-testid="marking-print-separate-close">
              Закрыть
            </Button>
          ) : (
            <>
              <Button onClick={onClose} disabled={busy}>
                Отмена
              </Button>
              <Button
                variant="contained"
                disabled={printDisabled}
                onClick={() => void handlePrint()}
                data-testid="marking-print-confirm"
              >
                {reprint ? 'Перепечатать' : 'Печать'}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
      <Dialog
        open={chunkJob !== null}
        maxWidth="xs"
        fullWidth
        data-testid="marking-print-chunk-dialog"
      >
        <DialogTitle>Печать пачками</DialogTitle>
        <DialogContent>
          {chunkJob ? (
            <Stack spacing={1.5} sx={{ pt: 0.5 }}>
              <Typography variant="body2">
                Этикеток: {chunkJob.sections.length} · пачек: {chunkTotal} (по {PRINT_CHUNK_SIZE})
              </Typography>
              <Typography variant="body2" data-testid="marking-print-chunk-progress">
                Отправлено пачек: {chunkJob.printedChunks} из {chunkTotal}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Если лента кончилась во время печати — заправьте новую и нажмите «Повторить
                пачку», затем продолжайте.
              </Typography>
              {error ? (
                <Alert severity="error" data-testid="marking-print-chunk-error">
                  {error}
                </Alert>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={abortChunkJob} disabled={busy} data-testid="marking-print-chunk-abort">
            Прервать
          </Button>
          {chunkJob && chunkJob.printedChunks > 0 && chunkJob.printedChunks <= chunkTotal ? (
            <Button
              disabled={busy}
              onClick={() => void printChunk(chunkJob.printedChunks - 1)}
              data-testid="marking-print-chunk-repeat"
            >
              Повторить пачку {chunkJob.printedChunks}
            </Button>
          ) : null}
          {chunkJob && chunkJob.printedChunks < chunkTotal ? (
            <Button
              variant="contained"
              disabled={busy}
              onClick={() => void printChunk(chunkJob.printedChunks)}
              data-testid="marking-print-chunk-next"
            >
              Печатать пачку {chunkJob.printedChunks + 1}
            </Button>
          ) : (
            <Button
              variant="contained"
              disabled={busy}
              onClick={finishChunkJob}
              data-testid="marking-print-chunk-done"
            >
              Готово
            </Button>
          )}
        </DialogActions>
      </Dialog>
      <Snackbar
        open={toast !== null}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        message={toast ?? ''}
        data-testid="marking-print-toast"
      />
    </>
  )
}
