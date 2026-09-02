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
  // Держал ли фокус сам сканер. Только по этому признаку поле имеет право
  // забрать фокус обратно.
  //
  // Проверять `document.activeElement` в момент эффекта оказалось недостаточно.
  // Оператор набирает количество в строке товара, экран сохраняет введённое,
  // строка перерисовывается — и поле количества на мгновение теряет фокус.
  // В этот зазор `activeElement` равен `body`, прошлая проверка считала, что
  // никто не печатает, и курсор выпрыгивал в сканер. При медленном вводе зазора
  // не возникало, при быстром и у настоящего сканера-клавиатуры — всегда.
  const ownsFocusRef = useRef(true)

  useEffect(() => {
    if (busy) return
    if (!ownsFocusRef.current) return
    // preventScroll обязателен. Обычный focus() подтягивает поле в кадр, а на
    // длинном документе поле стоит вверху страницы: после каждого пика экран
    // прыгал с той строки, куда его только что увёл скан, обратно наверх. Два
    // скролла дрались за кадр, и оператор видел телепортацию вместо ответа.
    inputRef.current?.focus({ preventScroll: true })
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
        onFocus={() => {
          ownsFocusRef.current = true
        }}
        onBlur={(event) => {
          // Пока идёт запрос, поле выключено и теряет фокус само — это не уход
          // оператора в другое поле, и право вернуть фокус сохраняем.
          if (busy) return
          ownsFocusRef.current = false
          // Уход фокуса с непустым значением — тот же сигнал, что и Enter
          // (§Ж-02): штрихкод, набранный или вставленный и оставленный в поле,
          // должен обработаться, а не молча остаться нетронутым. Значение
          // читаем из самого DOM-узла по той же причине, что и в onKeyDown —
          // не гонимся за React-состоянием, которое к этому моменту могло не
          // успеть перерисоваться.
          const code = event.target.value.trim()
          if (!code) return
          onScan(code)
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return
          // Значение берём из самого поля, а не из состояния React. «Клавиатурный»
          // сканер печатает символы и жмёт Enter быстрее, чем происходит
          // перерисовка, и последний символ штрихкода при чтении из состояния
          // терялся бы молча — а молча потерянный символ на складе означает
          // «короб не нашёлся», и оператор пикает второй раз, не понимая почему.
          const code = (event.target as HTMLInputElement).value.trim()
          if (!code) return
          event.preventDefault()
          onScan(code)
        }}
        placeholder={`Пикните ${expects}`}
        error={Boolean(error)}
        helperText={error ?? notice ?? undefined}
        slotProps={{ htmlInput: { 'data-testid': testId, 'aria-label': `Сканер: ${expects}` } }}
      />
      {/* Программе чтения нужно услышать результат пика: она не видит подсветку строки.
          Пиксели записаны строками намеренно: в MUI `sx` число не больше единицы для
          width/height означает долю, то есть `width: 1` — это 100%, а не один пиксель,
          и скрытый блок уводит страницу вбок. */}
      <Stack
        role="status"
        aria-live="polite"
        sx={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          overflow: 'hidden',
          clip: 'rect(0 0 0 0)',
          whiteSpace: 'nowrap',
        }}
      >
        <Typography variant="body2">{error ?? notice ?? ''}</Typography>
      </Stack>
      {busy ? <Alert severity="info" sx={{ mt: 1 }}>Ищем…</Alert> : null}
    </Stack>
  )
}
