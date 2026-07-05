import { useCallback, useEffect, useMemo, useState } from 'react'
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
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import CloudUploadOutlined from '@mui/icons-material/CloudUploadOutlined'
import { apiUrl } from '../api'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

export type BoxImportPreviewLine = {
  barcode: string
  product_id: string | null
  sku_code: string | null
  product_name: string | null
  quantity: number
}

export type BoxImportPreviewBox = {
  address: string
  lines: BoxImportPreviewLine[]
  total_qty: number
}

export type BoxImportRowError = {
  row: number
  barcode: string | null
  code: string
  message: string
}

export type BoxImportPreviewResponse = {
  boxes: BoxImportPreviewBox[]
  errors: BoxImportRowError[]
  summary: {
    boxes_count: number
    positions: number
    total_units: number
    error_count: number
  }
}

const FILE_FORMAT_ERROR_CODES = new Set([
  'unsupported_file_type',
  'missing_column',
  'empty_file',
])

export function boxImportErrorMessageRu(code: string, fallback: string): string {
  if (code === 'unsupported_file_type') {
    return 'Поддерживаются только файлы Excel (.xlsx) формата «Штрих-код комбайн».'
  }
  if (code === 'missing_column') {
    return fallback.includes('missing_column') || fallback.includes('Адрес')
      ? fallback
      : 'В файле нет обязательного столбца. Нужны: Штрих-код, Кол-во, Адрес.'
  }
  if (code === 'empty_file') {
    return 'Файл пустой — нет строк с данными.'
  }
  if (code === 'barcode_not_found') {
    return fallback
  }
  if (code === 'invalid_quantity') {
    return fallback
  }
  return fallback
}

async function readBoxImportApiError(res: Response): Promise<{ message: string; code: string | null }> {
  try {
    const text = await res.text()
    const data = text ? (JSON.parse(text) as { detail?: unknown }) : {}
    const d = data.detail
    if (typeof d === 'object' && d !== null && !Array.isArray(d) && 'code' in d) {
      const code = String((d as { code?: string }).code ?? '')
      const message = String((d as { message?: string }).message ?? code)
      return { code: code || null, message: boxImportErrorMessageRu(code, message) }
    }
    const message = await readApiErrorMessage(
      new Response(text, { status: res.status, headers: res.headers }),
    )
    return { code: null, message }
  } catch {
    return { code: null, message: `Ошибка ${res.status}` }
  }
}

type Props = {
  open: boolean
  token: string
  requestId: string
  /** Без trailing slash, напр. `/operations/inbound-intake-requests/{id}/import-boxes` */
  importBasePath: string
  testIdPrefix: string
  mpBoxPreset?: string
  onClose: () => void
  onApplied: (message: string) => void | Promise<void>
}

export function BoxImportDialog({
  open,
  token,
  requestId: _requestId,
  importBasePath,
  testIdPrefix,
  mpBoxPreset,
  onClose,
  onApplied,
}: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<BoxImportPreviewResponse | null>(null)
  const [fileFormatError, setFileFormatError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ignoreErrors, setIgnoreErrors] = useState(false)
  const [parseBusy, setParseBusy] = useState(false)
  const [applyBusy, setApplyBusy] = useState(false)

  const reset = useCallback(() => {
    setFile(null)
    setPreview(null)
    setFileFormatError(null)
    setError(null)
    setIgnoreErrors(false)
    setParseBusy(false)
    setApplyBusy(false)
  }, [])

  useEffect(() => {
    if (!open) {
      reset()
    }
  }, [open, reset])

  const rowErrors = preview?.errors ?? []
  const hasRowErrors = rowErrors.length > 0
  const resolvableUnits = useMemo(() => {
    if (!preview) {
      return 0
    }
    return preview.boxes.reduce(
      (sum, box) =>
        sum + box.lines.filter((ln) => ln.product_id != null).reduce((s, ln) => s + ln.quantity, 0),
      0,
    )
  }, [preview])

  const canApply =
    file != null &&
    preview != null &&
    fileFormatError == null &&
    resolvableUnits > 0 &&
    (!hasRowErrors || ignoreErrors)

  const runPreview = async (picked: File) => {
    setParseBusy(true)
    setError(null)
    setFileFormatError(null)
    setPreview(null)
    try {
      const form = new FormData()
      form.append('file', picked)
      const res = await fetch(apiUrl(`${importBasePath}/preview`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) {
        const parsed = await readBoxImportApiError(res)
        if (parsed.code && FILE_FORMAT_ERROR_CODES.has(parsed.code)) {
          setFileFormatError(parsed.message)
        } else {
          setError(parsed.message)
        }
        return
      }
      const data = (await res.json()) as BoxImportPreviewResponse
      setPreview(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось разобрать файл.')
    } finally {
      setParseBusy(false)
    }
  }

  const onPickFile = (picked: FileList | null) => {
    const next = picked?.[0]
    if (!next) {
      return
    }
    setFile(next)
    setIgnoreErrors(false)
    void runPreview(next)
  }

  const apply = async () => {
    if (!file || !canApply) {
      return
    }
    setApplyBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('ignore_errors', ignoreErrors ? 'true' : 'false')
      if (mpBoxPreset) {
        form.append('box_preset', mpBoxPreset)
      }
      const res = await fetch(apiUrl(`${importBasePath}/apply`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) {
        const parsed = await readBoxImportApiError(res)
        setError(parsed.message)
        return
      }
      const data = (await res.json()) as {
        boxes_created: number
        summary: BoxImportPreviewResponse['summary']
        errors: BoxImportRowError[]
      }
      const skipped = data.errors.length
      const msg =
        skipped > 0
          ? `Загружено ${data.boxes_created} коробов, ${data.summary.total_units} ед.; пропущено строк: ${skipped}`
          : `Загружено ${data.boxes_created} коробов, ${data.summary.positions} позиций`
      await onApplied(msg)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить короба.')
    } finally {
      setApplyBusy(false)
    }
  }

  const busy = parseBusy || applyBusy

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="md"
      fullWidth
      data-testid={`${testIdPrefix}-dialog`}
    >
      <DialogTitle>Загрузить по накладной</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Файл Excel (.xlsx) из «Штрих-код комбайн»: колонки Штрих-код, Кол-во, Адрес. Каждый
            адрес — отдельный короб; существующие короба не изменяются.
          </Typography>
          <Button
            component="label"
            variant="outlined"
            startIcon={parseBusy ? <CircularProgress size={18} /> : <CloudUploadOutlined />}
            disabled={busy}
            data-testid={`${testIdPrefix}-file-input`}
          >
            {file ? file.name : 'Выбрать файл .xlsx'}
            <input
              type="file"
              hidden
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => {
                onPickFile(e.target.files)
                e.target.value = ''
              }}
            />
          </Button>
          {fileFormatError ? (
            <Alert severity="error" data-testid={`${testIdPrefix}-format-error`}>
              {fileFormatError}
            </Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
              {error}
            </Alert>
          ) : null}
          {preview ? (
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Сводка
              </Typography>
              <Typography variant="body2" data-testid={`${testIdPrefix}-summary`}>
                Коробов: {preview.summary.boxes_count} · Позиций: {preview.summary.positions} ·
                Единиц: {preview.summary.total_units}
                {preview.summary.error_count > 0
                  ? ` · Ошибок строк: ${preview.summary.error_count}`
                  : ''}
              </Typography>
            </Paper>
          ) : null}
          {preview && preview.boxes.length > 0 ? (
            <Table size="small" data-testid={`${testIdPrefix}-boxes-table`}>
              <TableHead>
                <TableRow>
                  <TableCell>Короб</TableCell>
                  <TableCell>Штрих-код</TableCell>
                  <TableCell>Товар</TableCell>
                  <TableCell align="right">Кол-во</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {preview.boxes.flatMap((box) =>
                  box.lines.map((line, idx) => (
                    <TableRow
                      key={`${box.address}-${line.barcode}-${idx}`}
                      sx={
                        line.product_id == null
                          ? { bgcolor: 'error.50' }
                          : undefined
                      }
                    >
                      <TableCell>{box.address}</TableCell>
                      <TableCell>{line.barcode}</TableCell>
                      <TableCell>
                        {line.product_id
                          ? `${line.sku_code ?? ''} ${line.product_name ?? ''}`.trim()
                          : '— не найден'}
                      </TableCell>
                      <TableCell align="right">{line.quantity}</TableCell>
                    </TableRow>
                  )),
                )}
              </TableBody>
            </Table>
          ) : null}
          {hasRowErrors ? (
            <Box data-testid={`${testIdPrefix}-row-errors`}>
              <Typography variant="subtitle2" color="error" sx={{ mb: 0.5 }}>
                Ошибки строк
              </Typography>
              <Stack spacing={0.5}>
                {rowErrors.map((err, i) => (
                  <Typography key={`${err.code}-${err.row}-${i}`} variant="body2" color="error">
                    {err.message}
                    {err.row > 0 ? ` (строка ${err.row})` : ''}
                  </Typography>
                ))}
              </Stack>
              <FormControlLabel
                sx={{ mt: 1 }}
                control={
                  <Checkbox
                    checked={ignoreErrors}
                    onChange={(e) => setIgnoreErrors(e.target.checked)}
                    data-testid={`${testIdPrefix}-ignore-errors`}
                  />
                }
                label="Загрузить без нераспознанных строк"
              />
            </Box>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy} data-testid={`${testIdPrefix}-cancel`}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={!canApply || busy}
          onClick={() => void apply()}
          data-testid={`${testIdPrefix}-apply`}
        >
          {applyBusy ? 'Загрузка…' : 'Загрузить'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
