import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material'
import {
  PRODUCT_LABEL_REVIEW_FOOTER,
  productLabelDetailLines,
  resolveProductLabelArticle,
  truncateProductLabelName,
} from '../utils/productLabelText'
import { printProductThermalLabels } from '../utils/printProductThermalLabel'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'

type Props = {
  open: boolean
  meta: ProductLineDisplayMeta | null
  onClose: () => void
}

export function ProductBarcodePrintDialog({ open, meta, onClose }: Props) {
  const [qty, setQty] = useState('1')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setQty('1')
      setError(null)
    }
  }, [open, meta?.sku_code])

  const barcode = meta ? resolveProductPrimaryBarcode(meta) : ''
  const article = meta ? resolveProductLabelArticle(meta) : ''
  const name = meta ? truncateProductLabelName(meta.product_name) : ''
  const sellerName = meta?.seller_name?.trim() ?? ''
  const detailLines = meta ? productLabelDetailLines(meta) : []

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
      printProductThermalLabels(
        {
          product_name: meta.product_name,
          sku_code: meta.sku_code,
          wb_vendor_code: meta.wb_vendor_code,
          wb_color: meta.wb_color,
          wb_brand: meta.wb_brand,
          seller_name: meta.seller_name,
          barcode,
        },
        Math.floor(n),
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
      <DialogTitle>Печать этикетки 58×40</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Этикетка WB: штрихкод, селлер, название, артикул, цвет, бренд и призыв оставить отзыв.
        </Typography>

        <Box
          data-testid="ff-product-label-preview"
          sx={{
            width: 232,
            height: 160,
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
                mb: '1px',
              }}
              title={meta?.product_name}
            >
              {name || '—'}
            </Box>
            <Box>Артикул: {article || '—'}</Box>
            {detailLines.map((line) => (
              <Box key={line}>{line}</Box>
            ))}
          </Box>

          <Typography variant="caption" sx={{ fontSize: 8.5, lineHeight: 1.15, mt: '2px' }}>
            {PRODUCT_LABEL_REVIEW_FOOTER}
          </Typography>
        </Box>

        <TextField
          label="Количество этикеток"
          type="number"
          fullWidth
          size="small"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          slotProps={{
            htmlInput: { min: 1, max: 999, 'data-testid': 'ff-product-label-qty' },
          }}
        />
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
