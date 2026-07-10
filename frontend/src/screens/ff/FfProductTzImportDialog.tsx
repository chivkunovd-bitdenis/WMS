import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import CloudUploadOutlined from '@mui/icons-material/CloudUploadOutlined'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { createLatestRequestSequence } from '../../utils/latestRequestSequence'

type SellerRow = { id: string; name: string }

type PreviewRow = {
  row: number
  vendor_article: string | null
  size: string | null
  barcode: string | null
  name: string
  sku_code: string
  packaging_instructions: string | null
  declared_quantity: number | null
  action: 'create' | 'update' | 'skip' | 'error'
  product_id: string | null
  error_code: string | null
  error_message: string | null
}

type PreviewResponse = {
  sheet_name: string
  rows: PreviewRow[]
  errors: { row: number; barcode: string | null; code: string; message: string }[]
  summary: {
    total: number
    create_count: number
    update_count: number
    skip_count: number
    error_count: number
    declared_total: number
  }
}

type ApplyResponse = {
  created_count: number
  updated_count: number
  skipped_count: number
  product_ids: string[]
  added_quantity: number
  movement_count: number
  already_applied: boolean
}

type Props = {
  open: boolean
  token: string
  sellers: SellerRow[]
  defaultSellerId?: string | null
  onClose: () => void
  onApplied: (message: string) => void | Promise<void>
}

async function readImportError(res: Response): Promise<string> {
  try {
    const text = await res.text()
    const data = text ? (JSON.parse(text) as { detail?: unknown }) : {}
    const d = data.detail
    if (typeof d === 'object' && d !== null && !Array.isArray(d) && 'message' in d) {
      return String((d as { message?: string }).message ?? 'Ошибка импорта')
    }
    return await readApiErrorMessage(new Response(text, { status: res.status, headers: res.headers }))
  } catch {
    return `Ошибка ${res.status}`
  }
}

export function FfProductTzImportDialog({
  open,
  token,
  sellers,
  defaultSellerId,
  onClose,
  onApplied,
}: Props) {
  const [sellerId, setSellerId] = useState(defaultSellerId ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ignoreErrors, setIgnoreErrors] = useState(false)
  const previewRequests = useRef(createLatestRequestSequence())
  const applyRequests = useRef(createLatestRequestSequence())

  useEffect(() => {
    previewRequests.current.invalidate()
    applyRequests.current.invalidate()
    if (open) {
      setSellerId(defaultSellerId ?? '')
      setFile(null)
      setPreview(null)
      setBusy(false)
      setError(null)
    }
  }, [open, defaultSellerId])

  const canApply = useMemo(() => {
    if (!preview) return false
    if (preview.summary.create_count + preview.summary.update_count === 0) return false
    if (preview.summary.error_count > 0 && !ignoreErrors) return false
    return true
  }, [ignoreErrors, preview])

  function reset() {
    previewRequests.current.invalidate()
    applyRequests.current.invalidate()
    setFile(null)
    setPreview(null)
    setError(null)
    setBusy(false)
    setIgnoreErrors(false)
    setSellerId(defaultSellerId ?? '')
  }

  function handleClose() {
    if (busy) return
    reset()
    onClose()
  }

  async function runPreview(nextFile: File) {
    const previewRequestId = previewRequests.current.next()
    const previewSellerId = sellerId
    if (!previewSellerId) {
      setError('Выберите селлера.')
      return
    }
    setBusy(true)
    setError(null)
    setPreview(null)
    try {
      const fd = new FormData()
      fd.append('seller_id', previewSellerId)
      fd.append('file', nextFile)
      const res = await fetch(apiUrl('/products/import-tz/preview'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!previewRequests.current.isLatest(previewRequestId)) {
        return
      }
      if (!res.ok) {
        const message = await readImportError(res)
        if (previewRequests.current.isLatest(previewRequestId)) {
          setError(message)
        }
        return
      }
      const nextPreview = (await res.json()) as PreviewResponse
      if (previewRequests.current.isLatest(previewRequestId)) {
        setPreview(nextPreview)
      }
    } catch (e) {
      if (previewRequests.current.isLatest(previewRequestId)) {
        setError(e instanceof Error ? e.message : 'Не удалось разобрать файл.')
      }
    } finally {
      if (previewRequests.current.isLatest(previewRequestId)) {
        setBusy(false)
      }
    }
  }

  async function runApply() {
    if (!file || !sellerId || !canApply) return
    const applyRequestId = applyRequests.current.next()
    const applyFile = file
    const applySellerId = sellerId
    const applyIgnoreErrors = ignoreErrors
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('seller_id', applySellerId)
      fd.append('ignore_errors', applyIgnoreErrors ? 'true' : 'false')
      fd.append('file', applyFile)
      const res = await fetch(apiUrl('/products/import-tz/apply'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!applyRequests.current.isLatest(applyRequestId)) {
        return
      }
      if (!res.ok) {
        const message = await readImportError(res)
        if (applyRequests.current.isLatest(applyRequestId)) {
          setError(message)
        }
        return
      }
      const body = (await res.json()) as ApplyResponse
      if (!applyRequests.current.isLatest(applyRequestId)) {
        return
      }
      const msg = body.already_applied
        ? 'Этот файл уже применён. Остатки повторно не добавлены.'
        : `Создано: ${body.created_count}, обновлено: ${body.updated_count}, добавлено в сортировку: ${body.added_quantity}, движений: ${body.movement_count}, пропущено: ${body.skipped_count}`
      await onApplied(msg)
      if (!applyRequests.current.isLatest(applyRequestId)) {
        return
      }
      reset()
      onClose()
    } catch (e) {
      if (applyRequests.current.isLatest(applyRequestId)) {
        setError(e instanceof Error ? e.message : 'Не удалось применить импорт.')
      }
    } finally {
      if (applyRequests.current.isLatest(applyRequestId)) {
        setBusy(false)
      }
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md" data-testid="ff-tz-import-dialog">
      <DialogTitle>Загрузить товары из Excel (ТЗ)</DialogTitle>
      <DialogContent sx={{ maxHeight: '70vh', overflow: 'auto' }}>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="ff-tz-import-error">
              {error}
            </Alert>
          ) : null}
          <FormControl fullWidth size="small" required>
            <InputLabel id="ff-tz-import-seller-label">Селлер</InputLabel>
            <Select
              labelId="ff-tz-import-seller-label"
              label="Селлер"
              value={sellerId}
              disabled={busy}
              onChange={(e) => {
                previewRequests.current.invalidate()
                applyRequests.current.invalidate()
                setSellerId(String(e.target.value))
                setFile(null)
                setPreview(null)
                setBusy(false)
              }}
              data-testid="ff-tz-import-seller"
            >
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            component="label"
            variant="outlined"
            startIcon={<CloudUploadOutlined />}
            disabled={busy || !sellerId}
            data-testid="ff-tz-import-file"
          >
            Выбрать .xlsx
            <input
              hidden
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => {
                applyRequests.current.invalidate()
                const f = e.target.files?.[0] ?? null
                e.target.value = ''
                setFile(f)
                if (f) {
                  void runPreview(f)
                } else {
                  previewRequests.current.invalidate()
                  setPreview(null)
                  setBusy(false)
                }
              }}
            />
          </Button>
          {file ? (
            <Typography variant="body2" color="text.secondary">
              Файл: {file.name}
            </Typography>
          ) : null}
          {busy ? <CircularProgress size={22} data-testid="ff-tz-import-loading" /> : null}
          {preview ? (
            <Box>
              <Typography variant="body2" sx={{ mb: 1 }} data-testid="ff-tz-import-summary">
                Лист «{preview.sheet_name}»: создать {preview.summary.create_count}, обновить{' '}
                {preview.summary.update_count}, заявлено {preview.summary.declared_total}, ошибок{' '}
                {preview.summary.error_count}
              </Typography>
              {preview.summary.error_count > 0 ? (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={ignoreErrors}
                      onChange={(e) => setIgnoreErrors(e.target.checked)}
                      data-testid="ff-tz-import-ignore-errors"
                    />
                  }
                  label="Игнорировать строки с ошибками"
                />
              ) : null}
              <Table size="small" data-testid="ff-tz-import-preview-table">
                <TableHead>
                  <TableRow>
                    <TableCell>Строка</TableCell>
                    <TableCell>Артикул</TableCell>
                    <TableCell>Размер</TableCell>
                    <TableCell>ШК</TableCell>
                    <TableCell>SKU</TableCell>
                    <TableCell align="right">Заявлено</TableCell>
                    <TableCell>Действие</TableCell>
                    <TableCell>ТЗ</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.rows.slice(0, 80).map((r) => (
                    <TableRow key={`${r.row}-${r.barcode ?? ''}`}>
                      <TableCell>{r.row}</TableCell>
                      <TableCell>{r.vendor_article ?? '—'}</TableCell>
                      <TableCell>{r.size ?? '—'}</TableCell>
                      <TableCell>{r.barcode ?? '—'}</TableCell>
                      <TableCell>{r.sku_code || '—'}</TableCell>
                      <TableCell align="right">{r.declared_quantity ?? '—'}</TableCell>
                      <TableCell>
                        {r.action === 'error' ? r.error_message || r.error_code : r.action}
                      </TableCell>
                      <TableCell sx={{ maxWidth: 220 }}>
                        {r.packaging_instructions
                          ? r.packaging_instructions.slice(0, 80) +
                            (r.packaging_instructions.length > 80 ? '…' : '')
                          : 'нет'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {preview.rows.length > 80 ? (
                <Typography variant="caption" color="text.secondary">
                  Показаны первые 80 из {preview.rows.length} строк.
                </Typography>
              ) : null}
            </Box>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy} data-testid="ff-tz-import-cancel">
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={!canApply || busy}
          onClick={() => void runApply()}
          data-testid="ff-tz-import-apply"
        >
          Применить
        </Button>
      </DialogActions>
    </Dialog>
  )
}
