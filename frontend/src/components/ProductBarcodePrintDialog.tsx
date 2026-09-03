import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  TextField,
  Typography,
} from '@mui/material'
import {
  DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS,
  type ProductLabelPrintOptions,
} from '../utils/productLabelText'
import { printProductThermalLabels } from '../utils/printProductThermalLabel'
import { resolvePackUnits, resolveWbBarcodeLabelCount } from '../utils/productBarcodePrint'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { resolveLabelSize, loadLabelSizeId, type LabelSize } from '../utils/labelSize'
import { resolvePrintTemplate } from '../utils/printTemplate'
import { LabelSizeSelect } from './LabelSizeSelect'
import { MarkingLabelPreview } from './MarkingLabelPreview'

type Props = {
  open: boolean
  meta: ProductLineDisplayMeta | null
  onClose: () => void
  /** Токен и товар нужны, чтобы подтянуть состав этикетки, закреплённый за
   *  продавцом: без них печать из каталога жила по своим галочкам и расходилась
   *  с тем, что печатает склад. */
  token?: string
  productId?: string
}

export function ProductBarcodePrintDialog({ open, meta, onClose, token, productId }: Props) {
  const [qty, setQty] = useState('1')
  const [error, setError] = useState<string | null>(null)
  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId()))
  const [printOptions, setPrintOptions] = useState<ProductLabelPrintOptions>(
    DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS,
  )

  const hasComposition = Boolean(meta?.wb_composition?.trim())

  useEffect(() => {
    if (open) {
      setQty('1')
      setError(null)
      setPrintOptions({
        includeComposition: Boolean(meta?.wb_composition?.trim()),
      })
      // Состав, закреплённый за продавцом, важнее локальных галочек: этикетка
      // должна быть одинаковой везде, где её печатают.
      if (token && productId) {
        void (async () => {
          try {
            const template = await resolvePrintTemplate(token, { productId })
            const saved = template.layout.label_options
            if (saved) {
              setPrintOptions({
                includeSize: saved.include_size,
                includeColor: saved.include_color,
                includeBrand: saved.include_brand,
                includeComposition:
                  saved.include_composition && Boolean(meta?.wb_composition?.trim()),
              })
            }
          } catch {
            // Настройка не загрузилась — печатаем по галочкам на форме, как
            // печатали раньше. Ронять печать из-за этого нельзя.
          }
        })()
      }
    }
  }, [open, meta?.sku_code, meta?.wb_composition, token, productId])

  const barcode = meta ? resolveProductPrimaryBarcode(meta) : ''
  const packUnits = useMemo(
    () =>
      meta
        ? resolvePackUnits({
            units_in_pack: meta.units_in_pack,
            packaging_instructions: meta.packaging_instructions,
          })
        : 1,
    [meta?.units_in_pack, meta?.packaging_instructions],
  )
  const qtyMultiplier = Number(qty)
  const totalLabels =
    Number.isFinite(qtyMultiplier) && qtyMultiplier >= 1
      ? resolveWbBarcodeLabelCount(Math.floor(qtyMultiplier), packUnits)
      : 0

  const previewProductLabel = useMemo(() => {
    if (!meta || !barcode) {
      return null
    }
    return {
      product_name: meta.product_name,
      sku_code: meta.sku_code,
      wb_vendor_code: meta.wb_vendor_code,
      wb_size: meta.wb_size,
      wb_color: meta.wb_color,
      wb_brand: meta.wb_brand,
      wb_composition: meta.wb_composition,
      seller_name: meta.seller_name,
      barcode,
    }
  }, [meta, barcode])

  const handlePrint = () => {
    if (!meta || !barcode) {
      setError('У товара нет штрихкода WB.')
      return
    }
    const n = Number(qty)
    if (!Number.isFinite(n) || n < 1 || n > 999) {
      setError('Укажите количество от 1 до 999.')
      return
    }
    setError(null)
    try {
      const labelsToPrint = resolveWbBarcodeLabelCount(Math.floor(n), packUnits)
      printProductThermalLabels(
        {
          product_name: meta.product_name,
          sku_code: meta.sku_code,
          wb_vendor_code: meta.wb_vendor_code,
          wb_size: meta.wb_size,
          wb_color: meta.wb_color,
          wb_brand: meta.wb_brand,
          wb_composition: meta.wb_composition,
          seller_name: meta.seller_name,
          barcode,
        },
        labelsToPrint,
        printOptions,
        labelSize,
      )
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетки.')
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xs"
      data-testid="ff-product-label-print-dialog"
    >
      <DialogTitle>
        Печать этикетки {labelSize.widthMm}×{labelSize.heightMm}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Этикетка WB: штрихкод, селлер, название, артикул, цвет, бренд и по выбору — состав.
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          <LabelSizeSelect
            value={labelSize.id}
            onChange={setLabelSize}
            testId="ff-product-label-size"
          />
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          <MarkingLabelPreview
            variant="product"
            productLabel={previewProductLabel}
            size={labelSize}
            unitsToShow={Math.max(1, totalLabels || 1)}
            totalUnits={Math.max(1, totalLabels || 1)}
            printOptions={printOptions}
            testId="ff-product-label-preview"
          />
        </Box>

        <FormGroup row sx={{ justifyContent: 'center', gap: 1, mb: 2 }} data-testid="ff-product-label-fields">
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={printOptions.includeComposition}
                disabled={!hasComposition}
                onChange={(_, checked) =>
                  setPrintOptions((prev) => ({ ...prev, includeComposition: checked }))
                }
                data-testid="ff-product-label-include-composition"
              />
            }
            label="Состав"
          />
        </FormGroup>

        <TextField
          label="Количество ШК ВБ"
          type="number"
          fullWidth
          size="small"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          helperText={
            packUnits > 1
              ? `× ${packUnits} шт в упаковке → ${totalLabels > 0 ? totalLabels : '—'} этикеток`
              : undefined
          }
          slotProps={{
            htmlInput: { min: 1, max: 999, 'data-testid': 'ff-product-label-qty' },
          }}
        />
        {packUnits > 1 && totalLabels > 0 ? (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.5 }}
            data-testid="ff-product-label-total"
          >
            К печати: {totalLabels} этикеток
          </Typography>
        ) : null}
        {error ? (
          <Typography variant="body2" color="error" sx={{ mt: 1 }} data-testid="ff-product-label-error">
            {error}
          </Typography>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="ff-product-label-cancel">
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={handlePrint}
          disabled={!barcode}
          data-testid="ff-product-label-print"
        >
          Печать
        </Button>
      </DialogActions>
    </Dialog>
  )
}
