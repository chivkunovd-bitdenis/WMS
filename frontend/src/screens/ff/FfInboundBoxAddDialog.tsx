import { useCallback, useEffect, useMemo, useState } from 'react'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import EditOutlined from '@mui/icons-material/EditOutlined'
import {
  Alert,
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
  boxClosed: boolean
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
  boxClosed,
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
  const [manualEditProductId, setManualEditProductId] = useState<string | null>(null)
  const [manualDraftByProductId, setManualDraftByProductId] = useState<Record<string, string>>({})

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
      setManualEditProductId(null)
      setManualDraftByProductId({})
    }
  }, [open])

  const scanIntoBox = async () => {
    if (boxClosed) {
      return
    }
    const raw = scanBarcode.trim()
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

  const saveManualQty = useCallback(
    async (productId: string) => {
      if (boxClosed) {
        return
      }
      const raw = manualDraftByProductId[productId] ?? '0'
      const qty = Math.floor(Number(raw))
      if (!Number.isFinite(qty) || qty < 0) {
        setError('Укажите целое количество ≥ 0.')
        return
      }
      const current = qtyInBoxByProductId.get(productId) ?? 0
      if (qty === current) {
        setManualEditProductId(null)
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
        setManualEditProductId(null)
        await onUpdated()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, boxClosed, boxId, manualDraftByProductId, onUpdated, qtyInBoxByProductId, requestId],
  )

  const closeBox = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/${boxId}/close`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      await onUpdated()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось закрыть короб.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="ff-inbound-box-add-dialog"
      slotProps={{ paper: { sx: { maxHeight: 'calc(100vh - 48px)' } } }}
    >
      <DialogTitle component="div" sx={{ pr: 6 }} data-testid="ff-inbound-box-add-title">
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
      <DialogContent dividers sx={{ overflowY: 'auto' }}>
        <Stack spacing={2}>
          {boxClosed ? (
            <Alert severity="info">Короб завершён — добавление недоступно.</Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="ff-inbound-box-add-error">
              {error}
            </Alert>
          ) : null}

          {!boxClosed ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
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

          <Table size="small" data-testid="ff-inbound-box-add-table">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 52, px: 1 }}>Фото</TableCell>
                <TableCell sx={{ minWidth: 0 }}>Товар</TableCell>
                <TableCell align="right" sx={{ width: 76, whiteSpace: 'nowrap', px: 1 }}>
                  Заявлено
                </TableCell>
                <TableCell align="right" sx={{ width: 96, whiteSpace: 'nowrap', px: 1 }}>
                  В коробе
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {requestLines.map((ln) => {
                const inBox = qtyInBoxByProductId.get(ln.product_id) ?? 0
                const manualOpen = manualEditProductId === ln.product_id
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
                    <TableCell sx={{ minWidth: 0, verticalAlign: 'top' }}>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 700, wordBreak: 'break-word' }}
                        data-testid={`ff-inbound-box-add-product-${ln.product_id}-sku`}
                      >
                        {displayMeta.sku_code}
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{ wordBreak: 'break-word' }}
                        data-testid={`ff-inbound-box-add-product-${ln.product_id}-name`}
                      >
                        {displayMeta.product_name}
                      </Typography>
                      {displayMeta.wb_size ? (
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ display: 'block' }}
                          data-testid={`ff-inbound-box-add-size-${ln.product_id}`}
                        >
                          Размер: {displayMeta.wb_size}
                        </Typography>
                      ) : null}
                      {barcode ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          ШК: {barcode}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right" sx={{ px: 1, verticalAlign: 'top' }}>
                      {ln.expected_qty}
                    </TableCell>
                    <TableCell align="right" sx={{ px: 1, verticalAlign: 'top' }}>
                      <Stack
                        direction="row"
                        spacing={0.5}
                        sx={{ justifyContent: 'flex-end', alignItems: 'center' }}
                      >
                        {manualOpen && !boxClosed ? (
                          <TextField
                            type="number"
                            size="small"
                            value={manualDraftByProductId[ln.product_id] ?? String(inBox)}
                            onChange={(e) =>
                              setManualDraftByProductId((prev) => ({
                                ...prev,
                                [ln.product_id]: e.target.value,
                              }))
                            }
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                void saveManualQty(ln.product_id)
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
                        ) : (
                          <Typography variant="body2" data-testid="ff-inbound-box-add-qty">
                            {inBox}
                          </Typography>
                        )}
                        {!boxClosed ? (
                          <IconButton
                            size="small"
                            aria-label="Править количество"
                            disabled={busy}
                            onClick={() => {
                              if (manualOpen) {
                                void saveManualQty(ln.product_id)
                                return
                              }
                              setManualEditProductId(ln.product_id)
                              setManualDraftByProductId((prev) => ({
                                ...prev,
                                [ln.product_id]: String(inBox),
                              }))
                            }}
                            data-testid="ff-inbound-box-add-manual-edit"
                          >
                            <EditOutlined fontSize="small" />
                          </IconButton>
                        ) : null}
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Stack>
      </DialogContent>
      {!boxClosed ? (
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>
            Скрыть окно
          </Button>
          <Button
            variant="outlined"
            onClick={() => void closeBox()}
            disabled={busy}
            data-testid="ff-inbound-box-add-close-box"
          >
            Завершить короб
          </Button>
        </DialogActions>
      ) : null}
    </Dialog>
  )
}
