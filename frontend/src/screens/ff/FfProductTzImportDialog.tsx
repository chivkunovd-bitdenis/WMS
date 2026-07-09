import { useEffect, useMemo, useState } from 'react'
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

type SellerRow = { id: string; name: string }

type PreviewRow = {
  row: number
  vendor_article: string | null
  size: string | null
  barcode: string | null
  name: string
  sku_code: string
  packaging_instructions: string | null
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
  }
}

type ApplyResponse = {
  created_count: number
  updated_count: number
  skipped_count: number
  product_ids: string[]
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

  useEffect(() => {
    if (open) {
      setSellerId(defaultSellerId ?? '')
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
    if (!sellerId) {
      setError('Выберите селлера.')
      return
    }
    setBusy(true)
    setError(null)
    setPreview(null)
    try {
      const fd = new FormData()
      fd.append('seller_id', sellerId)
      fd.append('file', nextFile)
      const res = await fetch(apiUrl('/products/import-tz/preview'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        setError(await readImportError(res))
        return
      }
      setPreview((await res.json()) as PreviewResponse)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось разобрать файл.')
    } finally {
      setBusy(false)
    }
  }

  async function runApply() {
    if (!file || !sellerId || !canApply) return
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('seller_id', sellerId)
      fd.append('ignore_errors', ignoreErrors ? 'true' : 'false')
      fd.append('file', file)
      const res = await fetch(apiUrl('/products/import-tz/apply'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        setError(await readImportError(res))
        return
      }
      const body = (await res.json()) as ApplyResponse
      const msg = `Создано: ${body.created_count}, обновлено: ${body.updated_count}, пропущено: ${body.skipped_count}`
      reset()
      await onApplied(msg)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить импорт.')
    } finally {
      setBusy(false)
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
              onChange={(e) => {
                setSellerId(String(e.target.value))
                setPreview(null)
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
                const f = e.target.files?.[0] ?? null
                e.target.value = ''
                setFile(f)
                if (f) void runPreview(f)
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
                {preview.summary.update_count}, ошибок {preview.summary.error_count}
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
        <Button onClick={handleClose} disabled={busy}>
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
