import { useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent } from 'react'
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
import { alpha } from '@mui/material/styles'
import { apiUrl } from '../../api'
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import {
  productDisplayMetaFromCatalog,
  type WbProductCatalogRow,
} from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  boxFillDialogContentSx,
  boxFillDialogPaperSx,
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
  const [localBoxLines, setLocalBoxLines] = useState<InboundBoxLine[]>(boxLines)
  const [lastScannedProductId, setLastScannedProductId] = useState<string | null>(null)
  const [draftQtyByProductId, setDraftQtyByProductId] = useState<Record<string, string>>({})
  const draftQtyRef = useRef(draftQtyByProductId)
  const scanQueueRef = useRef<Promise<void>>(Promise.resolve())

  const qtyInBoxByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of localBoxLines) {
      m.set(ln.product_id, ln.quantity)
    }
    return m
  }, [localBoxLines])

  useEffect(() => {
    setLocalBoxLines(boxLines)
  }, [boxLines])

  useEffect(() => {
    if (!open) {
      setScanBarcode('')
      setLastScannedProductId(null)
      setError(null)
      setDraftQtyByProductId({})
      return
    }
    const quantitiesFromParent = new Map<string, number>(
      boxLines.map((line) => [line.product_id, line.quantity]),
    )
    const next: Record<string, string> = {}
    for (const ln of requestLines) {
      next[ln.product_id] = String(quantitiesFromParent.get(ln.product_id) ?? 0)
    }
    setDraftQtyByProductId(next)
  }, [boxLines, open, requestLines])

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
      const scannedLine = (await res.json()) as InboundBoxLine
      setLocalBoxLines((current) => {
        const exists = current.some((line) => line.product_id === scannedLine.product_id)
        return exists
          ? current.map((line) => (line.product_id === scannedLine.product_id ? scannedLine : line))
          : [...current, scannedLine]
      })
      setDraftQtyByProductId((current) => ({
        ...current,
        [scannedLine.product_id]: String(scannedLine.quantity),
      }))
      setLastScannedProductId(scannedLine.product_id)
      setScanBarcode('')
      // Keep the parent document coherent, but do not make the next scan wait for it.
      void onUpdated().catch(() => undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setBusy(false)
    }
  }

  const enqueueScanIntoBox = (rawInput?: string): Promise<void> => {
    const next = scanQueueRef.current.then(
      () => scanIntoBox(rawInput),
      () => scanIntoBox(rawInput),
    )
    scanQueueRef.current = next.catch(() => undefined)
    return next
  }

  useBarcodeScanner({
    enabled: open && !readOnly,
    onScan: (code) => {
      setScanBarcode(code)
      void enqueueScanIntoBox(code)
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
                    void enqueueScanIntoBox()
                  }
                }}
                disabled={busy}
                fullWidth
                autoFocus
                slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-box-add-scan-input' } }}
              />
              <Button
                variant="contained"
                onClick={() => void enqueueScanIntoBox()}
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
                  <FfProductTableHeadCells showPrint={false} />
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
                  return (
                    <TableRow
                      key={ln.id}
                      data-testid={`ff-inbound-box-add-line-row-${ln.product_id}`}
                      sx={
                        lastScannedProductId === ln.product_id
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.success.main, 0.16),
                              boxShadow: (theme) =>
                                `inset 0 0 0 1px ${alpha(theme.palette.success.main, 0.6)}`,
                            }
                          : undefined
                      }
                    >
                      <FfProductLineCells
                        meta={displayMeta}
                        showPrint={false}
                        lineTestIdPrefix={`ff-inbound-box-add-product-${ln.product_id}`}
                        nameExtra={
                          displayMeta.wb_size ? (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              data-testid={`ff-inbound-box-add-size-${ln.product_id}`}
                              title={`Размер: ${displayMeta.wb_size}`}
                            >
                              Размер: {displayMeta.wb_size}
                            </Typography>
                          ) : null
                        }
                      />
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
                            onChange={(e) => {
                              const nextVal = e.target.value
                              draftQtyRef.current = {
                                ...draftQtyRef.current,
                                [ln.product_id]: nextVal,
                              }
                              setDraftQtyByProductId((prev) => ({
                                ...prev,
                                [ln.product_id]: nextVal,
                              }))
                            }}
                            slotProps={{
                              htmlInput: {
                                min: 0,
                                'data-testid': 'ff-inbound-box-add-manual-qty',
                                onBlur: (e: FocusEvent<HTMLInputElement>) =>
                                  void saveQty(ln.product_id, e.currentTarget.value),
                                onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault()
                                    void saveQty(ln.product_id, e.currentTarget.value)
                                  }
                                },
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
        <Button
          variant="contained"
          onClick={() => void handleDismiss()}
          disabled={busy}
          data-testid="ff-inbound-box-add-dismiss"
        >
          Готово
        </Button>
      </DialogActions>
    </Dialog>
  )
}
