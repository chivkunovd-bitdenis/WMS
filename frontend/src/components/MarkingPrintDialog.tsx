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
  IconButton,
  MenuItem,
  Radio,
  RadioGroup,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import DeleteOutlined from '@mui/icons-material/DeleteOutlined'
import { apiUrl } from '../api'
import {
  MARKING_PRINT_PRESETS,
  applyLabelsPerProductToLayout,
  buildTapePreviewUnits,
  cloneLayout,
  countTapeBlocks,
  type PrintPresetId,
} from '../utils/markingPrintPresets'
import { createPrintTemplate, resolvePrintTemplate, type PrintLayout } from '../utils/printTemplate'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'
import { printMarkingCodeTape } from '../utils/printMarkingCodeLabel'
import type { ProductThermalLabelData } from '../utils/printProductThermalLabel'
import { resolvePackUnits, resolveWbBarcodeLabelCount } from '../utils/productBarcodePrint'

/** Fixed layout for non-ЧЗ: one WB barcode label per unit, no constructor. */
const NON_HONEST_SIGN_LABEL_LAYOUT: PrintLayout = {
  units: [{ block: 'label', copies: 1 }],
}

export type MarkingPrintContext = {
  token: string
  lineId: string
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
  const [presetId, setPresetId] = useState<PrintPresetId>('pairs')
  const [layout, setLayout] = useState<PrintLayout>(MARKING_PRINT_PRESETS[0].layout)
  const [allowPartial, setAllowPartial] = useState(false)
  const [labelsPerProduct, setLabelsPerProduct] = useState(1)
  const [wbBarcodeQty, setWbBarcodeQty] = useState(1)
  const [saveName, setSaveName] = useState('')
  const [toast, setToast] = useState<string | null>(null)

  const requiresHonestSign = ctx?.requiresHonestSign ?? true

  useEffect(() => {
    if (!open || !ctx) {
      return
    }
    setError(null)
    setAllowPartial(false)
    setLabelsPerProduct(1)
    setSaveName('')
    setWbBarcodeQty(1)
    if (!requiresHonestSign) {
      setLayout(cloneLayout(NON_HONEST_SIGN_LABEL_LAYOUT))
      return
    }
    const defaultPresetId: PrintPresetId = 'pairs'
    setPresetId(defaultPresetId)
    const defaultPreset =
      MARKING_PRINT_PRESETS.find((preset) => preset.id === defaultPresetId) ?? MARKING_PRINT_PRESETS[0]
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
          setPresetId(matched.id)
          setLayout(cloneLayout(matched.layout))
        } else {
          setPresetId('custom')
          setLayout(cloneLayout(template.layout))
        }
      } catch {
        setPresetId(defaultPresetId)
        setLayout(cloneLayout(defaultPreset.layout))
      }
    })()
  }, [open, ctx, requiresHonestSign, reprint])

  const qtyNeed = reprint ? (ctx?.qtyMarkingPrinted ?? 0) : (ctx?.qtyNeedPack ?? 0)
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
    ? qtyNeed
    : requiresHonestSign
      ? allowPartial
        ? Math.min(available, qtyNeed)
        : available >= qtyNeed
          ? qtyNeed
          : 0
      : wbBarcodeQty

  const previewUnits = useMemo(() => buildTapePreviewUnits(layout, 3), [layout])
  const previewTapeCount = useMemo(
    () => countTapeBlocks(3, layout, labelsPerProduct),
    [layout, labelsPerProduct],
  )
  const totalTapeCount = useMemo(
    () => countTapeBlocks(canPrintCount, layout, labelsPerProduct),
    [canPrintCount, layout, labelsPerProduct],
  )

  const applyPreset = (id: PrintPresetId) => {
    setPresetId(id)
    const preset = MARKING_PRINT_PRESETS.find((p) => p.id === id)
    if (preset) {
      setLayout(cloneLayout(preset.layout))
    }
  }

  const updateUnit = (index: number, patch: Partial<PrintLayout['units'][number]>) => {
    setLayout((prev) => ({
      units: prev.units.map((unit, i) => (i === index ? { ...unit, ...patch } : unit)),
    }))
    setPresetId('custom')
  }

  const moveUnit = (index: number, direction: -1 | 1) => {
    setLayout((prev) => {
      const next = [...prev.units]
      const target = index + direction
      if (target < 0 || target >= next.length) {
        return prev
      }
      const tmp = next[index]
      next[index] = next[target]
      next[target] = tmp
      return { units: next }
    })
    setPresetId('custom')
  }

  const removeUnit = (index: number) => {
    setLayout((prev) => ({
      units: prev.units.filter((_, i) => i !== index),
    }))
    setPresetId('custom')
  }

  const addUnit = (block: 'label' | 'cz') => {
    if (!requiresHonestSign && block === 'cz') {
      return
    }
    setLayout((prev) => ({
      units: [...prev.units, { block, copies: 1 }],
    }))
    setPresetId('custom')
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
            ? `Не хватает ${data.shortage} кодов ЧЗ в пуле.`
            : 'Нет доступных кодов для печати.',
        )
        return
      }
      await printMarkingCodeTape(
        data.codes.map((cis) => ({
          cis,
          productLabel: ctx.productLabel ?? null,
        })),
        applyLabelsPerProductToLayout(data.layout ?? layout, labelsPerProduct),
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
    qtyNeed < 1 ||
    (requiresHonestSign && !reprint && available < 1) ||
    (requiresHonestSign && !reprint && !allowPartial && shortage > 0) ||
    (!requiresHonestSign && wbBarcodeQty < 1)

  const dialogTitle = reprint
    ? 'Повторная печать'
    : requiresHonestSign
      ? 'Печать ЧЗ'
      : 'Печать этикеток'

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
                    ? `Нужно: ${qtyNeed} · Доступно в пуле: ${available}`
                    : `К упаковке: ${qtyNeed}`}
                </Typography>
              </Box>
            ) : null}

            {shortage > 0 ? (
              <Alert severity="error" data-testid="marking-print-shortage-banner">
                Не хватает {shortage} из {qtyNeed} кодов
              </Alert>
            ) : null}

            {!reprint && shortage > 0 ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
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
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setToast('Запрос селлеру отправим в следующей версии')}
                  data-testid="marking-print-request-seller"
                >
                  Запросить у селлера
                </Button>
              </Stack>
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
                    ? `× ${packUnits} шт в упаковке → ${totalWbLabels} этикеток`
                    : undefined
                }
                slotProps={{ htmlInput: { min: 1, max: 999 } }}
                data-testid="marking-print-wb-qty"
                sx={{ maxWidth: 280 }}
              />
            ) : null}

            {!reprint && requiresHonestSign ? (
              <>
                <TextField
                  size="small"
                  label="Этикеток на каждый товар"
                  type="number"
                  value={labelsPerProduct}
                  onChange={(e) =>
                    setLabelsPerProduct(Math.max(1, Math.min(99, Number(e.target.value) || 1)))
                  }
                  slotProps={{ htmlInput: { min: 1, max: 99 } }}
                  data-testid="marking-print-labels-per-product"
                  sx={{ maxWidth: 220 }}
                />

                <RadioGroup
                  value={presetId}
                  onChange={(e) => applyPreset(e.target.value as PrintPresetId)}
                >
                  {MARKING_PRINT_PRESETS.map((preset) => (
                    <FormControlLabel
                      key={preset.id}
                      value={preset.id}
                      control={<Radio size="small" data-testid={`marking-print-preset-${preset.id}`} />}
                      label={preset.label}
                    />
                  ))}
                </RadioGroup>

                {presetId === 'custom' ? (
                  <Stack spacing={1} data-testid="marking-print-custom-builder">
                    {layout.units.map((unit, index) => (
                      <Stack
                        key={`${unit.block}-${index}`}
                        direction="row"
                        spacing={1}
                        sx={{ alignItems: 'center' }}
                      >
                        <TextField
                          select
                          size="small"
                          label="Блок"
                          value={unit.block}
                          onChange={(e) =>
                            updateUnit(index, { block: e.target.value as 'label' | 'cz' })
                          }
                          sx={{ minWidth: 120 }}
                        >
                          <MenuItem value="cz">ЧЗ</MenuItem>
                          <MenuItem value="label">Этикетка</MenuItem>
                        </TextField>
                        <TextField
                          size="small"
                          label="Копий"
                          type="number"
                          value={unit.copies}
                          onChange={(e) =>
                            updateUnit(index, {
                              copies: Math.max(1, Math.min(10, Number(e.target.value) || 1)),
                            })
                          }
                          slotProps={{ htmlInput: { min: 1, max: 10 } }}
                          sx={{ width: 88 }}
                        />
                        <IconButton
                          size="small"
                          aria-label="Выше"
                          onClick={() => moveUnit(index, -1)}
                          disabled={index === 0}
                        >
                          <ArrowUpwardIcon fontSize="small" />
                        </IconButton>
                        <IconButton
                          size="small"
                          aria-label="Ниже"
                          onClick={() => moveUnit(index, 1)}
                          disabled={index === layout.units.length - 1}
                        >
                          <ArrowDownwardIcon fontSize="small" />
                        </IconButton>
                        <IconButton
                          size="small"
                          aria-label="Удалить"
                          onClick={() => removeUnit(index)}
                          disabled={layout.units.length <= 1}
                        >
                          <DeleteOutlined fontSize="small" />
                        </IconButton>
                      </Stack>
                    ))}
                    <Stack direction="row" spacing={1}>
                      <Button size="small" startIcon={<AddIcon />} onClick={() => addUnit('cz')}>
                        ЧЗ
                      </Button>
                      <Button size="small" startIcon={<AddIcon />} onClick={() => addUnit('label')}>
                        Этикетка
                      </Button>
                    </Stack>
                  </Stack>
                ) : null}

                <Box data-testid="marking-print-preview">
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mb: 0.5, display: 'block' }}
                    data-testid="marking-print-preview-tape-count"
                  >
                    Предпросмотр ленты (один код на единицу) · {previewTapeCount} этикеток на 3 ед.
                  </Typography>
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
                        (код {unit.codeHint})
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

            {reprint ? (
              <Typography variant="body2">
                Будет повторно отправлено на печать {qtyNeed} код(ов).
              </Typography>
            ) : null}

            {!reprint && requiresHonestSign && canPrintCount > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {canPrintCount} ед. · {totalTapeCount} этикеток в ленте
              </Typography>
            ) : null}

            {!reprint && !requiresHonestSign && totalWbLabels > 0 ? (
              <Typography variant="body2" data-testid="marking-print-will-print">
                К печати: {totalWbLabels} этикеток
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
