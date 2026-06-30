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
  Radio,
  RadioGroup,
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
import { printMarkingCodeTape } from '../utils/printMarkingCodeLabel'
import type { ProductThermalLabelData } from '../utils/printProductThermalLabel'
import { resolvePackUnits, resolveWbBarcodeLabelCount } from '../utils/productBarcodePrint'

type PrintedCodeOption = {
  id: string
  cis_masked: string
  status: string
}

/** Fixed layout for non-ЧЗ: one WB barcode label per unit, no constructor. */
const NON_HONEST_SIGN_LABEL_LAYOUT: PrintLayout = {
  units: [{ block: 'label', copies: 1 }],
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
  const [selectedReprintCodeId, setSelectedReprintCodeId] = useState('')
  const [reprintCodesLoading, setReprintCodesLoading] = useState(false)

  const requiresHonestSign = ctx?.requiresHonestSign ?? true
  const isCatalogSource = ctx?.source === 'catalog' || !ctx?.lineId

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
    setSelectedReprintCodeId('')
    setReprintCodesLoading(false)
    setDragTapeIndex(null)
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
          setSelectedReprintCodeId(codes[0]?.id ?? '')
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
    ? selectedReprintCodeId
      ? 1
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
  const totalWbLabels = resolveWbBarcodeLabelCount(wbBarcodeQty, packUnits)
  const available = ctx?.markingAvailable ?? 0
  const shortage = requiresHonestSign && !reprint && available < qtyNeed ? qtyNeed - available : 0
  const canPrintCount = reprint
    ? selectedReprintCodeId
      ? 1
      : 0
    : requiresHonestSign
      ? allowPartial
        ? Math.min(available, qtyNeed)
        : available >= qtyNeed
          ? qtyNeed
          : 0
      : wbBarcodeQty

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

  const printLabelOnlyTape = async () => {
    if (!ctx || wbBarcodeQty < 1 || totalWbLabels < 1) {
      return
    }
    const units = Array.from({ length: totalWbLabels }, (_, index) => ({
      cis: `label-only-${index + 1}`,
      productLabel: ctx.productLabel ?? null,
    }))
    await printMarkingCodeTape(units, NON_HONEST_SIGN_LABEL_LAYOUT, ctx.productLabel)
    ctx.onPrinted()
    onClose()
  }

  const printCatalogTape = async () => {
    if (!ctx || canPrintCount < 1) {
      return
    }
    const res = await fetch(apiUrl(`/operations/marking-codes/products/${ctx.productId}/codes`), {
      headers: { Authorization: `Bearer ${ctx.token}` },
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    const rows = (await res.json()) as { cis_code: string; status: string }[]
    const available = rows.filter((r) => r.status === 'available').map((r) => r.cis_code)
    if (available.length < canPrintCount) {
      throw new Error(`Не хватает ${canPrintCount - available.length} КМ в пуле.`)
    }
    const codes = available.slice(0, canPrintCount)
    await printMarkingCodeTape(
      codes.map((cis) => ({
        cis,
        productLabel: ctx.productLabel ?? null,
      })),
      layout,
      ctx.productLabel,
    )
    ctx.onPrinted()
    onClose()
  }

  const handlePrint = async () => {
    if (!ctx) {
      return
    }
    if (!requiresHonestSign) {
      onBusyChange(true)
      setError(null)
      try {
        await printLabelOnlyTape()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетки.')
      } finally {
        onBusyChange(false)
      }
      return
    }
    if (isCatalogSource && !reprint) {
      onBusyChange(true)
      setError(null)
      try {
        await printCatalogTape()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось напечатать ЧЗ.')
      } finally {
        onBusyChange(false)
      }
      return
    }
    if (!ctx.lineId) {
      setError('Нет строки упаковки для печати КМ.')
      return
    }
    onBusyChange(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/packaging-lines/${ctx.lineId}/print`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${ctx.token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            layout_json: layout,
            allow_partial: allowPartial,
            reprint,
            ...(reprint && selectedReprintCodeId
              ? { code_ids: [selectedReprintCodeId] }
              : {}),
          }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as {
        codes: string[]
        duplicate_copies: number
        quantity: number
        shortage: number | null
        layout: PrintLayout
      }
      if (data.quantity < 1) {
        setError(
          data.shortage
            ? `Не хватает ${data.shortage} КМ в пуле.`
            : 'Нет доступных КМ для печати.',
        )
        return
      }
      await printMarkingCodeTape(
        data.codes.map((cis) => ({
          cis,
          productLabel: ctx.productLabel ?? null,
        })),
        data.layout ?? layout,
        ctx.productLabel,
      )
      ctx.onPrinted()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать ЧЗ.')
    } finally {
      onBusyChange(false)
    }
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
    (reprint && requiresHonestSign && (reprintCodesLoading || !selectedReprintCodeId)) ||
    (!reprint && qtyNeed < 1) ||
    (requiresHonestSign && !reprint && available < 1) ||
    (requiresHonestSign && !reprint && !allowPartial && shortage > 0) ||
    (!requiresHonestSign && wbBarcodeQty < 1)

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
                      ? `Выбрано для перепечатки: ${selectedReprintCodeId ? 1 : 0} из ${ctx.qtyMarkingPrinted}`
                      : isCatalogSource
                        ? `К печати: ${catalogPrintQty} · Доступно в пуле: ${available}`
                        : `Нужно: ${qtyNeed} · Доступно в пуле: ${available}`
                    : `К упаковке: ${qtyNeed}`}
                </Typography>
              </Box>
            ) : null}

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

            {!reprint && requiresHonestSign ? (
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
                <RadioGroup
                  value={selectedReprintCodeId}
                  onChange={(e) => setSelectedReprintCodeId(e.target.value)}
                  data-testid="marking-reprint-pick-list"
                >
                  {reprintCodes.map((code) => (
                    <FormControlLabel
                      key={code.id}
                      value={code.id}
                      control={
                        <Radio
                          size="small"
                          data-testid={`marking-reprint-pick-${code.id}`}
                        />
                      }
                      label={code.cis_masked}
                    />
                  ))}
                </RadioGroup>
              )
            ) : null}

            {reprint && requiresHonestSign && selectedReprintCodeId ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К перепечатке: 1 КМ
              </Typography>
            ) : null}

            {!reprint && requiresHonestSign && canPrintCount > 0 ? (
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
