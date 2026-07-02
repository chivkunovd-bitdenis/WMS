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
  PRODUCT_LABEL_REVIEW_FOOTER,
  productLabelDetailLines,
  resolveProductLabelArticle,
  normalizeProductLabelName,
  type ProductLabelPrintOptions,
} from '../utils/productLabelText'
import { printProductThermalLabels } from '../utils/printProductThermalLabel'
import { resolvePackUnits, resolveWbBarcodeLabelCount } from '../utils/productBarcodePrint'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'
import { resolveLabelSize, loadLabelSizeId, type LabelSize } from '../utils/labelSize'
import { LabelSizeSelect } from './LabelSizeSelect'

type Props = {
  open: boolean
  meta: ProductLineDisplayMeta | null
  onClose: () => void
}

export function ProductBarcodePrintDialog({ open, meta, onClose }: Props) {
  const [qty, setQty] = useState('1')
  const [error, setError] = useState<string | null>(null)
  const [labelSize, setLabelSize] = useState<LabelSize>(() => resolveLabelSize(loadLabelSizeId()))
  const [printOptions, setPrintOptions] = useState<ProductLabelPrintOptions>(
    DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS,
  )

  const hasSize = Boolean(meta?.wb_size?.trim())
  const hasComposition = Boolean(meta?.wb_composition?.trim())

  useEffect(() => {
    if (open) {
      setQty('1')
      setError(null)
      setPrintOptions({
        includeSize: Boolean(meta?.wb_size?.trim()),
        includeComposition: Boolean(meta?.wb_composition?.trim()),
      })
    }
  }, [open, meta?.sku_code, meta?.wb_size, meta?.wb_composition])

  const barcode = meta ? resolveProductPrimaryBarcode(meta) : ''
  const article = meta ? resolveProductLabelArticle(meta) : ''
  const name = meta ? normalizeProductLabelName(meta.product_name) : ''
  const sellerName = meta?.seller_name?.trim() ?? ''
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
  const detailLines = useMemo(
    () => (meta ? productLabelDetailLines(meta, printOptions) : []),
    [meta, printOptions],
  )

  const previewBarcodeUrl = useMemo(() => {
    if (!barcode) {
      return ''
    }
    try {
      return renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
    } catch {
      return ''
    }
  }, [barcode])

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
          Этикетка WB: штрихкод, селлер, название, артикул, цвет, бренд и по выбору — размер и состав.
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          <LabelSizeSelect
            value={labelSize.id}
            onChange={setLabelSize}
            testId="ff-product-label-size"
          />
        </Box>

        <Box
          data-testid="ff-product-label-preview"
          sx={{
            width: 232,
            height: Math.round((232 * labelSize.heightMm) / labelSize.widthMm),
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            bgcolor: '#fff',
            color: '#111',
            p: '6px 7px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            fontFamily: 'Arial, Helvetica, sans-serif',
            mx: 'auto',
            mb: 2,
          }}
        >
          <Box sx={{ flex: '0 0 auto', mb: '3px' }}>
            {previewBarcodeUrl ? (
              <Box
                component="img"
                src={previewBarcodeUrl}
                alt="barcode"
                sx={{ width: '100%', maxHeight: 40, objectFit: 'contain', display: 'block' }}
              />
            ) : null}
            <Typography
              variant="caption"
              sx={{
                display: 'block',
                textAlign: 'center',
                letterSpacing: '0.04em',
                fontSize: 9,
                lineHeight: 1.1,
                fontFamily: 'Arial, Helvetica, sans-serif',
              }}
            >
              {barcode || '—'}
            </Typography>
          </Box>

          <Box sx={{ flex: 1, minHeight: 0, fontSize: 9, lineHeight: 1.2, overflow: 'hidden' }}>
            {sellerName ? (
              <Box
                sx={{
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  mb: '1px',
                }}
                title={sellerName}
              >
                {sellerName}
              </Box>
            ) : null}
            <Box
              sx={{
                fontSize: 9.5,
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                wordBreak: 'break-word',
                mb: '1px',
              }}
              title={name || meta?.product_name}
            >
              {name || '—'}
            </Box>
            <Box>Артикул: {article || '—'}</Box>
            {detailLines.map((line) => (
              <Box
                key={line}
                sx={
                  line.startsWith('Состав:')
                    ? {
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                        wordBreak: 'break-word',
                      }
                    : undefined
                }
              >
                {line}
              </Box>
            ))}
          </Box>

          <Typography variant="caption" sx={{ fontSize: 8.5, lineHeight: 1.15, mt: '2px' }}>
            {PRODUCT_LABEL_REVIEW_FOOTER}
          </Typography>
        </Box>

        <FormGroup row sx={{ justifyContent: 'center', gap: 1, mb: 2 }} data-testid="ff-product-label-fields">
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={printOptions.includeSize}
                disabled={!hasSize}
                onChange={(_, checked) =>
                  setPrintOptions((prev) => ({ ...prev, includeSize: checked }))
                }
                data-testid="ff-product-label-include-size"
              />
            }
            label="Размер"
          />
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
