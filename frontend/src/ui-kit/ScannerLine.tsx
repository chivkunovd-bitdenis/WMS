import { Alert, Stack, TextField, Typography } from '@mui/material'
import { useEffect, useRef, useState } from 'react'

// Канон R-25: экран, который слушает сканер, обязан об этом говорить.
// Работающий, но молчащий слушатель равен отсутствующей функции — так и вышло
// с приёмкой, где сканирование было, а заказчик спрашивал, где оно.
export function ScannerLine({
  active,
  expects,
  onWake,
  testId,
}: {
  active: boolean
  expects: string
  /** Вернуть фокус в поле по нажатию на плашку. */
  onWake?: () => void
  testId?: string
}) {
  return (
    <Stack
      direction="row"
      spacing={1}
      data-testid={testId}
      data-scanner-active={active ? 'true' : 'false'}
      onClick={active ? undefined : onWake}
      sx={{
        alignItems: 'center',
        alignSelf: 'flex-start',
        px: 1.5,
        py: 0.75,
        mb: 2,
        borderRadius: 2.5,
        cursor: active || !onWake ? 'default' : 'pointer',
        backgroundColor: active ? 'rgba(27, 107, 69, 0.10)' : 'rgba(180, 35, 24, 0.10)',
        color: active ? '#14603D' : '#9B1C14',
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {active
          ? `Сканер активен — ${expects}`
          : 'Сканер не слушает — нажмите сюда и пикайте снова'}
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
/** Быстрее этого человек не печатает: символ сканера. */
const BURST_CHAR_MS = 50
/** Столько подряд быстрых символов — уже очередь, а не случайность. */
const BURST_MIN_CHARS = 3
/** Пауза после очереди: код закончился. */
const BURST_IDLE_MS = 120

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
  /**
   * Значение поля. Не передан — поле НЕуправляемое, и это правильный режим
   * для сканера.
   *
   * ⛔ Управляемое поле на тяжёлом экране теряет символы. React рисует
   * родителя раньше ребёнка, и пока перерисовываются сотни строк документа,
   * поле получает на коммите СТАРОЕ значение. Сканер к этому моменту вбил уже
   * половину кода — и половина стирается. Оператор видит в строке «46» и
   * дальше ничего, хотя пикнул полный штрихкод. Ровно это и происходило на
   * пересчёте из 480 строк 02.09.2026.
   *
   * Неуправляемое поле держит правду в DOM: перерисовка его не трогает.
   */
  value?: string
  onChange?: (value: string) => void
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
  // Слушает ли поле прямо сейчас. Плашка обязана показывать это честно.
  //
  // Раньше в ней стояло литеральное `active`, то есть «Сканер активен» горело
  // всегда. Оператор трогал любое другое поле — комментарий, поиск, количество
  // в строке, — фокус уходил, и «клавиатурный» сканер начинал печатать штрихкод
  // туда. Ни счёта, ни находки, ни следа в базе; на экране при этом зелёным
  // написано, что сканер работает. Это и есть «сканер сканит, система ничё не
  // делает»: проверено руками на прод-документе — код 4630452735395 уехал в
  // поле «Комментарий», плашка осталась зелёной.
  const [listening, setListening] = useState(false)

  // Слушаем фокус на всём документе, а не только blur своего поля.
  //
  // Одного onBlur мало: фокус может вообще ни разу не побывать в поле — тогда
  // blur не случится, и плашка так и останется зелёной, обещая работу, которой
  // нет. А сканер в это время печатает штрихкод туда, где стоит курсор.
  useEffect(() => {
    const sync = () => setListening(document.activeElement === inputRef.current)
    sync()
    document.addEventListener('focusin', sync)
    document.addEventListener('focusout', sync)
    return () => {
      document.removeEventListener('focusin', sync)
      document.removeEventListener('focusout', sync)
    }
  }, [])

  // Сканер, который не шлёт Enter.
  //
  // «Клавиатурный» сканер настраивается суффиксом, и суффикс этот сплошь и
  // рядом не выставлен: код печатается в поле и там остаётся. Экран ждал
  // Enter, не получал его и молчал — со стороны это ровно «сканер сканит,
  // система ничё не делает». Проверено 02.09.2026: тот же сканер печатает
  // штрихкод в адресную строку браузера и не отправляет её.
  //
  // Поэтому пачку символов узнаём по темпу. Сканер вбивает код за десятки
  // миллисекунд на символ, человек — за сотни. Если символы шли очередью и
  // очередь оборвалась паузой, это законченный код: обрабатываем сами.
  // Ручной ввод под правило не попадает — там интервалы длинные.
  const burstRef = useRef<{ timer: number | null; last: number; fast: number }>({
    timer: null,
    last: 0,
    fast: 0,
  })

  const clearInput = () => {
    // Неуправляемое поле React не чистит — чистим сами, иначе следующий пик
    // приклеится к предыдущему коду.
    if (value === undefined && inputRef.current) inputRef.current.value = ''
  }

  const submit = (code: string) => {
    const trimmed = code.trim()
    if (!trimmed) return
    burstRef.current.fast = 0
    clearInput()
    onScan(trimmed)
  }

  const noteKeystroke = (next: string) => {
    const state = burstRef.current
    const now = Date.now()
    const gap = now - state.last
    state.last = now
    // Символы, пришедшие быстрее человека. Считаем их, чтобы не сработать на
    // ручном вводе и на вставке одним куском.
    if (gap <= BURST_CHAR_MS) state.fast += 1
    else state.fast = 0
    if (state.timer !== null) window.clearTimeout(state.timer)
    if (state.fast < BURST_MIN_CHARS) return
    state.timer = window.setTimeout(() => {
      state.timer = null
      // Значение читаем из поля: последний символ мог не доехать до состояния.
      submit(inputRef.current?.value ?? next)
    }, BURST_IDLE_MS)
  }

  useEffect(
    () => () => {
      if (burstRef.current.timer !== null) window.clearTimeout(burstRef.current.timer)
    },
    [],
  )

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
      <ScannerLine
        active={listening || busy}
        expects={expects}
        onWake={() => {
          ownsFocusRef.current = true
          inputRef.current?.focus({ preventScroll: true })
        }}
        testId={testId ? `${testId}-line` : undefined}
      />
      <TextField
        inputRef={inputRef}
        size="small"
        fullWidth
        {...(value === undefined ? {} : { value })}
        disabled={busy}
        onChange={(event) => {
          onChange?.(event.target.value)
          noteKeystroke(event.target.value)
        }}
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
          submit(code)
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return
          // Enter пришёл — отложенная отправка по паузе больше не нужна.
          if (burstRef.current.timer !== null) {
            window.clearTimeout(burstRef.current.timer)
            burstRef.current.timer = null
          }
          burstRef.current.fast = 0
          // Значение берём из самого поля, а не из состояния React. «Клавиатурный»
          // сканер печатает символы и жмёт Enter быстрее, чем происходит
          // перерисовка, и последний символ штрихкода при чтении из состояния
          // терялся бы молча — а молча потерянный символ на складе означает
          // «короб не нашёлся», и оператор пикает второй раз, не понимая почему.
          const code = (event.target as HTMLInputElement).value.trim()
          if (!code) return
          event.preventDefault()
          submit(code)
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
