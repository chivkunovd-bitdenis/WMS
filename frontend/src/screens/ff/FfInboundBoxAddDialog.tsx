import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import {
  productDisplayMetaFromCatalog,
  resolveProductPrimaryBarcode,
  type WbProductCatalogRow,
} from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  boxFillDialogContentSx,
  boxFillDialogPaperSx,
  boxFillProductCellSx,
  boxFillQtyCellSx,
  boxFillTableScrollSx,
} from './boxFillDialogLayout'
import { scanErrorMessageRu } from './inboundReceivingHelpers'

type InboundBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type RequestLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
}

type Props = {
  open: boolean
  onClose: () => void
  requestId: string
  boxId: string
  boxLabel: string
  readOnly: boolean
  token: string
  requestLines: RequestLine[]
  boxLines: InboundBoxLine[]
  catalogById: Map<string, WbProductCatalogRow>
  onUpdated: () => Promise<void>
}

export function FfInboundBoxAddDialog({
  open,
  onClose,
  requestId,
  boxId,
  boxLabel,
  readOnly,
  token,
  requestLines,
  boxLines,
  catalogById,
  onUpdated,
}: Props) {
  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanBarcode, setScanBarcode] = useState('')
  const [draftQtyByProductId, setDraftQtyByProductId] = useState<Record<string, string>>({})
  const draftQtyRef = useRef(draftQtyByProductId)

  const qtyInBoxByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of boxLines) {
      m.set(ln.product_id, ln.quantity)
    }
    return m
  }, [boxLines])

  useEffect(() => {
    if (!open) {
      setScanBarcode('')
      setError(null)
      setDraftQtyByProductId({})
      return
    }
    const next: Record<string, string> = {}
    for (const ln of requestLines) {
      next[ln.product_id] = String(qtyInBoxByProductId.get(ln.product_id) ?? 0)
    }
    setDraftQtyByProductId(next)
  }, [open, qtyInBoxByProductId, requestLines])

  useEffect(() => {
    draftQtyRef.current = draftQtyByProductId
  }, [draftQtyByProductId])

  const saveQty = useCallback(
    async (productId: string, rawOverride?: string) => {
      if (readOnly) {
        return
      }
      const raw = rawOverride ?? draftQtyRef.current[productId] ?? '0'
      const qty = Math.floor(Number(raw))
      if (!Number.isFinite(qty) || qty < 0) {
        setError('Укажите целое количество ≥ 0.')
        return
      }
      const current = qtyInBoxByProductId.get(productId) ?? 0
      if (qty === current) {
        return
      }
      setBusy(true)
      setError(null)
      try {
        const res = await fetch(
          apiUrl(
            `/operations/inbound-intake-requests/${requestId}/boxes/${boxId}/lines/${productId}`,
          ),
          {
            method: 'PUT',
            headers: authHeaders,
            body: JSON.stringify({ quantity: qty }),
          },
        )
        if (!res.ok) {
          setError(scanErrorMessageRu(await readApiErrorMessage(res)))
          return
        }
        await onUpdated()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, boxId, onUpdated, qtyInBoxByProductId, readOnly, requestId],
  )

  const flushPendingQty = useCallback(async () => {
    if (readOnly) {
      return
    }
    for (const ln of requestLines) {
      await saveQty(ln.product_id)
    }
  }, [readOnly, requestLines, saveQty])

  const handleDismiss = async () => {
    await flushPendingQty()
    await onUpdated()
    onClose()
  }

  const scanIntoBox = async (rawInput?: string) => {
    if (readOnly) {
      return
    }
    const raw = (rawInput ?? scanBarcode).trim()
    if (!raw) {
      setError('Введите штрихкод.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/${boxId}/scan`),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ barcode: raw }),
        },
      )
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      setScanBarcode('')
      await onUpdated()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setBusy(false)
    }
  }

  useBarcodeScanner({
    enabled: open && !readOnly,
    onScan: (code) => {
      setScanBarcode(code)
      void scanIntoBox(code)
    },
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      fullWidth
      data-testid="ff-inbound-box-add-dialog"
      slotProps={{ paper: { sx: boxFillDialogPaperSx } }}
    >
      <DialogTitle component="div" sx={{ pr: 6, flexShrink: 0 }} data-testid="ff-inbound-box-add-title">
        <Typography component="span" variant="h6" sx={{ display: 'block', fontWeight: 700 }}>
          Наполнить короб
        </Typography>
        <Typography
          variant="body2"
          sx={{ fontWeight: 700, mt: 0.5 }}
          data-testid="ff-inbound-box-add-box-label"
        >
          {boxLabel}
        </Typography>
        <IconButton
          aria-label="Скрыть окно"
          onClick={onClose}
          sx={{ position: 'absolute', right: 8, top: 8 }}
          data-testid="ff-inbound-box-add-close"
        >
          <CloseOutlined />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={boxFillDialogContentSx}>
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0 }}>
          {readOnly ? (
            <Alert severity="info">Приёмка завершена — состав короба только для просмотра.</Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="ff-inbound-box-add-error">
              {error}
            </Alert>
          ) : null}

          {!readOnly ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexShrink: 0 }}>
              <TextField
                size="small"
                label="Штрихкод товара"
                value={scanBarcode}
                onChange={(e) => setScanBarcode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void scanIntoBox()
                  }
                }}
                disabled={busy}
                fullWidth
                autoFocus
                slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-box-add-scan-input' } }}
              />
              <Button
                variant="contained"
                onClick={() => void scanIntoBox()}
                disabled={busy || !scanBarcode.trim()}
                data-testid="ff-inbound-box-add-scan-submit"
                sx={{ flexShrink: 0 }}
              >
                Скан
              </Button>
            </Stack>
          ) : null}

          <Box sx={boxFillTableScrollSx}>
            <Table size="small" stickyHeader data-testid="ff-inbound-box-add-table">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 56, px: 1 }}>Фото</TableCell>
                  <TableCell sx={{ minWidth: 180 }}>Товар</TableCell>
                  <TableCell align="right" sx={{ width: 80, whiteSpace: 'nowrap', px: 1 }}>
                    Заявлено
                  </TableCell>
                  <TableCell align="right" sx={boxFillQtyCellSx}>
                    В коробе
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {requestLines.map((ln) => {
                  const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                  const barcode = resolveProductPrimaryBarcode(displayMeta)
                  return (
                    <TableRow
                      key={ln.id}
                      data-testid={`ff-inbound-box-add-line-row-${ln.product_id}`}
                    >
                      <TableCell sx={{ px: 1, verticalAlign: 'top' }}>
                        <ProductPhotoThumb
                          src={displayMeta.wb_primary_image_url}
                          alt={displayMeta.product_name}
                          testId={`ff-inbound-box-add-product-${ln.product_id}-photo`}
                        />
                      </TableCell>
                      <TableCell sx={boxFillProductCellSx}>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 700 }}
                          data-testid={`ff-inbound-box-add-product-${ln.product_id}-sku`}
                          title={displayMeta.sku_code}
                        >
                          {displayMeta.sku_code}
                        </Typography>
                        <Typography
                          variant="body2"
                          data-testid={`ff-inbound-box-add-product-${ln.product_id}-name`}
                          title={displayMeta.product_name}
                        >
                          {displayMeta.product_name}
                        </Typography>
                        {displayMeta.wb_size ? (
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            data-testid={`ff-inbound-box-add-size-${ln.product_id}`}
                            title={`Размер: ${displayMeta.wb_size}`}
                          >
                            Размер: {displayMeta.wb_size}
                          </Typography>
                        ) : null}
                        {barcode ? (
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            title={`ШК: ${barcode}`}
                          >
                            ШК: {barcode}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right" sx={{ px: 1, verticalAlign: 'top' }}>
                        {ln.expected_qty}
                      </TableCell>
                      <TableCell align="right" sx={boxFillQtyCellSx}>
                        {readOnly ? (
                          <Typography variant="body2" data-testid="ff-inbound-box-add-qty">
                            {qtyInBoxByProductId.get(ln.product_id) ?? 0}
                          </Typography>
                        ) : (
                          <TextField
                            type="number"
                            size="small"
                            value={draftQtyByProductId[ln.product_id] ?? '0'}
                            onChange={(e) =>
                              setDraftQtyByProductId((prev) => ({
                                ...prev,
                                [ln.product_id]: e.target.value,
                              }))
                            }
                            onBlur={(e) =>
                              void saveQty(ln.product_id, (e.target as HTMLInputElement).value)
                            }
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                void saveQty(ln.product_id, (e.target as HTMLInputElement).value)
                              }
                            }}
                            slotProps={{
                              htmlInput: {
                                min: 0,
                                'data-testid': 'ff-inbound-box-add-manual-qty',
                              },
                            }}
                            sx={{ width: 72 }}
                            disabled={busy}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexShrink: 0 }}>
        <Button onClick={() => void handleDismiss()} disabled={busy} data-testid="ff-inbound-box-add-dismiss">
          Скрыть окно
        </Button>
      </DialogActions>
    </Dialog>
  )
}
