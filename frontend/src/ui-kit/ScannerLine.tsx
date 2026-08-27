import { Alert, Stack, TextField, Typography } from '@mui/material'
import { useEffect, useRef } from 'react'

// Канон R-25: экран, который слушает сканер, обязан об этом говорить.
// Работающий, но молчащий слушатель равен отсутствующей функции — так и вышло
// с приёмкой, где сканирование было, а заказчик спрашивал, где оно.
export function ScannerLine({
  active,
  expects,
  testId,
}: {
  active: boolean
  expects: string
  testId?: string
}) {
  return (
    <Stack
      direction="row"
      spacing={1}
      data-testid={testId}
      sx={{
        alignItems: 'center',
        alignSelf: 'flex-start',
        px: 1.5,
        py: 0.75,
        mb: 2,
        borderRadius: 2.5,
        backgroundColor: active ? 'rgba(27, 107, 69, 0.10)' : 'rgba(15, 23, 42, 0.06)',
        color: active ? '#14603D' : 'text.secondary',
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {active ? `Сканер активен — ${expects}` : 'Сканер не слушает этот экран'}
      </Typography>
    </Stack>
  )
}

/**
 * Поле под «клавиатурный» сканер: он просто печатает символы и жмёт Enter.
 *
 * Канон R-26: сканер тупой. Он отдаёт строку и ничего не решает — что делать с
 * найденным, знает экран. Поле само возвращает себе фокус после каждого пика,
 * иначе второй короб уезжает мимо в никуда, и оператор об этом не узнаёт.
 */
export function ScannerField({
  value,
  onChange,
  onScan,
  expects,
  busy = false,
  error,
  notice,
  testId,
}: {
  value: string
  onChange: (value: string) => void
  onScan: (code: string) => void
  expects: string
  busy?: boolean
  error?: string | null
  /** Что нашлось прошлым пиком — на языке склада, без кодов. */
  notice?: string | null
  testId?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!busy) {
      inputRef.current?.focus()
    }
  }, [busy, notice, error])

  return (
    <Stack>
      <ScannerLine active expects={expects} testId={testId ? `${testId}-line` : undefined} />
      <TextField
        inputRef={inputRef}
        size="small"
        fullWidth
        value={value}
        disabled={busy}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return
          const code = value.trim()
          if (!code) return
          event.preventDefault()
          onScan(code)
        }}
        placeholder={`Пикните ${expects}`}
        error={Boolean(error)}
        helperText={error ?? notice ?? undefined}
        slotProps={{ htmlInput: { 'data-testid': testId, 'aria-label': `Сканер: ${expects}` } }}
      />
      {/* Программе чтения нужно услышать результат пика: она не видит подсветку строки. */}
      <Stack role="status" aria-live="polite" sx={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
        <Typography variant="body2">{error ?? notice ?? ''}</Typography>
      </Stack>
      {busy ? <Alert severity="info" sx={{ mt: 1 }}>Ищем…</Alert> : null}
    </Stack>
  )
}
