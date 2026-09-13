import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import ChatBubbleOutlineRoundedIcon from '@mui/icons-material/ChatBubbleOutlineRounded'
import {
  Box,
  Button,
  CircularProgress,
  Divider,
  Paper,
  TextField,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'

import { getStoredToken } from '../../api'
import {
  ASSISTANT_MESSAGE_MAX_CHARS,
  describeSendError,
  fetchAssistantConversation,
  sendAssistantMessage,
  type AssistantMessageRow,
} from '../../utils/assistantApi'
import { collectAssistantScreenContext } from '../../utils/assistantScreenContext'

// WMS-433: окно AI-помощника в правом нижнем углу портала ФФ (R1–R7, R11,
// R20–R22). Живёт в каркасе AuthedAppLayout вне маршрутов, поэтому переходы
// по меню его не трогают; открыто/закрыто и компактно/развёрнуто — в
// localStorage (удобство конкретного браузера), сама переписка — на сервере.
//
// Слои (R2, решение аналитика 4.3): кнопка и окно рисуются порталом в body в
// одном слое с диалогами MUI (zIndex.modal), поэтому кто выше — решает порядок
// в DOM. Как только открывается полноэкранный документ, контейнер окна
// переносится в конец body и оказывается над документом: с него можно писать
// помощнику. Малый диалог с затемнением, открытый позже, попадает в body после
// контейнера и ложится поверх окна: окно затемнено, ввод не принимает, диалог
// не перекрывает. После закрытия диалога окно в прежнем состоянии.

const OPEN_KEY = 'wms_assistant_open'
const EXPANDED_KEY = 'wms_assistant_expanded'
// Пока последнее сообщение ждёт ответа, лента опрашивается раз в 3 секунды
// (вебсокетов в проекте нет). Когда всё отвечено или окно закрыто — тишина.
const POLL_INTERVAL_MS = 3000
// Тот же предел, что у сервера (list_conversation): в окне последние 500
// обращений (R5, решение аналитика 4.3) — применяется и к локальным добавлениям.
const CONVERSATION_LIMIT = 500
// Строка-«призрак»: показывается сразу при отправке, до ответа сервера (R7).
const PENDING_ID_PREFIX = 'pending-'

// Геометрия: кнопка в углу остаётся видна при открытом окне, чтобы повторное
// нажатие закрывало его (R2). Окно встаёт над кнопкой.
const EDGE_GAP = 24
const BUTTON_HEIGHT = 40
const WINDOW_BOTTOM = EDGE_GAP + BUTTON_HEIGHT + 12
const APP_BAR_HEIGHT = 64
const FF_DRAWER_WIDTH = 260
// Компактное окно: 560 px, но не выше 264 px от верха окна браузера — ниже
// этой линии шапка и панель действий полноэкранного документа («Печать
// накладной», «Сохранить», «Закрыть» заканчиваются на 257 px) остаются
// видны и нажимаемы на любом размере от 1366×768 (решение аналитика, C7).
// При 900 px высоты укладываются все 560, при 768 — остаётся 428.
const COMPACT_HEIGHT = 560
const COMPACT_TOP_MIN = 264

// Корни диалогов MUI — прямые дети body (Portal по умолчанию), полноэкранный
// узнаётся по классу бумаги — тот же признак, что в сборе контекста экрана.
const DIALOG_ROOT_SELECTOR = 'body > .MuiDialog-root'
const FULLSCREEN_PAPER_SELECTOR = '.MuiDialog-paperFullScreen'

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function writeFlag(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? '1' : '0')
  } catch {
    /* localStorage недоступен — окно просто не запомнит состояние */
  }
}

function newClientMessageId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

type SendAttempt = { id: string; text: string }

// Контейнер портала в body. Создаётся один раз на время жизни панели и
// убирается вместе с ней: при выходе из портала каркас размонтируется.
function useBodyContainer(): HTMLDivElement | null {
  const [container] = useState<HTMLDivElement | null>(() =>
    typeof document === 'undefined' ? null : document.createElement('div'),
  )
  useEffect(() => {
    if (!container) return
    container.dataset.testid = 'assistant-root'
    document.body.appendChild(container)
    return () => {
      container.remove()
    }
  }, [container])
  return container
}

// Ставит контейнер окна на нужное место среди корней диалогов в body — и при
// монтировании (диалог мог быть открыт раньше панели), и при каждом изменении:
// сразу после последнего полноэкранного документа (окно над документом, но
// под малыми диалогами, открытыми поверх него); если полноэкранного нет —
// перед первым диалогом (окно под любым малым диалогом). Узел двигается
// только когда стоит не там, где нужно: перенос сбрасывает фокус.
function placeAssistantContainer(container: HTMLElement): void {
  const roots = Array.from(document.querySelectorAll<HTMLElement>(DIALOG_ROOT_SELECTOR))
  let lastFullscreen: HTMLElement | null = null
  for (const root of roots) {
    if (root.querySelector(FULLSCREEN_PAPER_SELECTOR)) {
      lastFullscreen = root
    }
  }
  if (lastFullscreen) {
    if (lastFullscreen.nextElementSibling !== container) {
      lastFullscreen.after(container)
    }
    return
  }
  const first = roots[0]
  if (!first) return
  const containerBeforeFirst = Boolean(
    container.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING,
  )
  if (!containerBeforeFirst) {
    first.before(container)
  }
}

function usePlaceAmongDialogs(container: HTMLDivElement | null): void {
  useEffect(() => {
    if (!container) return
    const place = () => placeAssistantContainer(container)
    place()
    const observer = new MutationObserver(place)
    observer.observe(document.body, { childList: true })
    return () => observer.disconnect()
  }, [container])
}

function applyConversationLimit(rows: AssistantMessageRow[]): AssistantMessageRow[] {
  return rows.length > CONVERSATION_LIMIT ? rows.slice(-CONVERSATION_LIMIT) : rows
}

// Слияние снимка сервера с лентой. Сервер — источник истины по составу и
// порядку; локальные строки (отправленные и «призраки») дописываются в конец
// только если снимок начат раньше их появления — тогда они заведомо новее
// всего в снимке, и порядок не нарушается. Снимок, начатый после локального
// изменения, полный: он применяется целиком, локальные id забываются.
// Простая замена стирала бы только что отправленное сообщение устаревшим GET.
function mergeConversation(
  server: AssistantMessageRow[],
  local: AssistantMessageRow[],
  localOnlyIds: Set<string>,
  snapshotPredatesLocalChanges: boolean,
): AssistantMessageRow[] {
  if (!snapshotPredatesLocalChanges) {
    localOnlyIds.clear()
    return applyConversationLimit(server)
  }
  const serverIds = new Set(server.map((row) => row.id))
  const extras = local.filter((row) => localOnlyIds.has(row.id) && !serverIds.has(row.id))
  return applyConversationLimit([...server, ...extras])
}

// Любая ошибка панели не должна гасить экран оператора: при сбое остаётся
// только кнопка в углу, нажатие пробует поднять панель заново.
class AssistantErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  componentDidCatch(error: unknown): void {
    console.error('[assistant] панель помощника отключена из-за ошибки', error)
  }

  render(): ReactNode {
    if (!this.state.failed) {
      return this.props.children
    }
    return (
      <Button
        type="button"
        variant="contained"
        startIcon={<ChatBubbleOutlineRoundedIcon />}
        onClick={() => this.setState({ failed: false })}
        aria-label="Помощник"
        data-testid="assistant-toggle"
        data-failed="1"
        sx={{ ...cornerButtonSx, zIndex: (theme) => theme.zIndex.modal }}
      >
        Помощник
      </Button>
    )
  }
}

export function AssistantPanel() {
  return (
    <AssistantErrorBoundary>
      <AssistantPanelBody />
    </AssistantErrorBoundary>
  )
}

function AssistantPanelBody() {
  const token = getStoredToken('fulfillment')
  const [open, setOpen] = useState<boolean>(() => readFlag(OPEN_KEY))
  const [expanded, setExpanded] = useState<boolean>(() => readFlag(EXPANDED_KEY))
  const [messages, setMessages] = useState<AssistantMessageRow[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  // Последняя попытка отправки: тот же текст → тот же client_message_id,
  // чтобы повтор после потери ответа не создал дубль (R21).
  const attemptRef = useRef<SendAttempt | null>(null)
  // Строки, добавленные локально («призраки» и только что отправленные), и
  // номер загрузки, последней начатой к моменту их добавления: снимки с
  // номером не больше этого начаты раньше и строк содержать не могут.
  const localOnlyIdsRef = useRef<Set<string>>(new Set())
  const localChangeSeqRef = useRef(0)
  // Номера начатой и применённой загрузок: ответ применяется, если он новее
  // уже применённого (а не последнего начатого — иначе при GET дольше
  // интервала опроса ни один ответ не применился бы). Пока загрузка в пути,
  // новая не начинается: тик опроса пропускается, а запрос открытия окна
  // запоминается и выполняется по завершении текущей. Закрытие окна и
  // размонтирование отменяют загрузку в пути — её ответ не применяется.
  const loadSeqRef = useRef(0)
  const appliedSeqRef = useRef(0)
  const loadInFlightRef = useRef(false)
  const reloadRequestedRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const openRef = useRef(open)
  openRef.current = open
  // После размонтирования панели продолжения запросов (ответ на отправку,
  // завершение загрузки, отложенный перечит) ничего не делают: ни состояния,
  // ни новых запросов. Отправку не отменяем — сервер мог уже сохранить строку.
  const mountedRef = useRef(true)
  const sendingRef = useRef(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const container = useBodyContainer()
  usePlaceAmongDialogs(container)

  // requestReload: если загрузка уже в пути, выполнить ещё одну по её
  // завершении. Ставится открытием окна (снимок нужен свежий), но не тиком
  // опроса — иначе при медленном GET за готовым ответом шёл бы лишний запрос.
  const refresh = useCallback(
    async function load(options?: { silent?: boolean; requestReload?: boolean }): Promise<void> {
      if (!token || !mountedRef.current) return
      if (loadInFlightRef.current) {
        if (options?.requestReload) reloadRequestedRef.current = true
        return
      }
      loadInFlightRef.current = true
      const controller = new AbortController()
      abortRef.current = controller
      const seq = ++loadSeqRef.current
      try {
        const rows = await fetchAssistantConversation(token, controller.signal)
        if (!mountedRef.current || controller.signal.aborted || seq <= appliedSeqRef.current) return
        appliedSeqRef.current = seq
        const predatesLocalChanges = seq <= localChangeSeqRef.current
        setMessages((current) =>
          mergeConversation(rows, current, localOnlyIdsRef.current, predatesLocalChanges),
        )
        setLoadError(null)
      } catch (error) {
        if (!mountedRef.current || controller.signal.aborted || seq <= appliedSeqRef.current) return
        if (!options?.silent) {
          setLoadError(`Не удалось загрузить переписку: ${describeSendError(error)}`)
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        if (mountedRef.current) {
          loadInFlightRef.current = false
          if (!controller.signal.aborted) setLoaded(true)
          if (reloadRequestedRef.current) {
            reloadRequestedRef.current = false
            if (openRef.current) void load()
          }
        }
      }
    },
    [token],
  )

  // Закрыли окно — загрузка в пути отменяется (её снимок устарел бы к
  // следующему открытию). Локальные строки при этом не забываются: их снимет
  // только снимок, начатый после отправки. Размонтирование отменяет загрузку
  // и сбрасывает всё, что могло бы запустить новый запрос.
  useEffect(() => {
    if (!open) abortRef.current?.abort()
  }, [open])
  useEffect(() => {
    mountedRef.current = true
    const localOnlyIds = localOnlyIdsRef.current
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
      abortRef.current = null
      reloadRequestedRef.current = false
      loadInFlightRef.current = false
      localOnlyIds.clear()
    }
  }, [])

  // Открыли окно (в том числе после F5 с сохранённым «открыто») — подтянуть ленту.
  useEffect(() => {
    if (!open) return
    void refresh({ requestReload: true })
  }, [open, refresh])

  const hasWaiting = messages.some((m) => m.waiting)

  useEffect(() => {
    if (!open || !hasWaiting) return
    const timer = window.setInterval(() => {
      // Пока отправка в пути, снимок сервера не нужен: «призрак» уже в ленте,
      // а его серверная строка появится из ответа на отправку.
      if (document.hidden || sendingRef.current) return
      void refresh()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [open, hasWaiting, refresh])

  // Лента всегда показывает конец переписки.
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, open, expanded])

  const toggleOpen = () => {
    setOpen((current) => {
      writeFlag(OPEN_KEY, !current)
      return !current
    })
  }

  const setExpandedPersist = (value: boolean) => {
    writeFlag(EXPANDED_KEY, value)
    setExpanded(value)
  }

  const closeWindow = () => {
    writeFlag(OPEN_KEY, false)
    setOpen(false)
  }

  const send = async () => {
    if (!token) return
    const text = draft.trim()
    if (!text || sending) return
    const previous = attemptRef.current
    const attempt: SendAttempt =
      previous && previous.text === text ? previous : { id: newClientMessageId(), text }
    attemptRef.current = attempt
    const context = collectAssistantScreenContext()
    // R7: сообщение сразу в ленте, ниже «Готовлю ответ» — ещё до ответа сервера.
    const pendingId = `${PENDING_ID_PREFIX}${attempt.id}`
    const pending: AssistantMessageRow = {
      id: pendingId,
      message_text: text,
      screen_title: context.screen_title,
      created_at: '',
      answer_text: null,
      answered_at: null,
      backlog_number: null,
      waiting: true,
    }
    localOnlyIdsRef.current.add(pendingId)
    localChangeSeqRef.current = loadSeqRef.current
    // Без обрезки: если отправка не удастся, «призрак» уйдёт, и лента вернётся
    // ровно к прежним строкам. Предел применяется при замене на серверную строку.
    setMessages((current) => [...current, pending])
    setDraft('')
    setSending(true)
    sendingRef.current = true
    setSendError(null)
    try {
      const row = await sendAssistantMessage(token, {
        client_message_id: attempt.id,
        message_text: text,
        ...context,
      })
      if (!mountedRef.current) return
      attemptRef.current = null
      localOnlyIdsRef.current.delete(pendingId)
      localOnlyIdsRef.current.add(row.id)
      localChangeSeqRef.current = loadSeqRef.current
      setMessages((current) => {
        const withoutPending = current.filter((m) => m.id !== pendingId)
        return withoutPending.some((m) => m.id === row.id)
          ? withoutPending
          : applyConversationLimit([...withoutPending, row])
      })
    } catch (error) {
      if (!mountedRef.current) return
      // R21: «призрак» убирается, текст возвращается в поле, причина одной
      // строкой; повтор той же кнопкой уходит с тем же client_message_id.
      localOnlyIdsRef.current.delete(pendingId)
      setMessages((current) => current.filter((m) => m.id !== pendingId))
      setDraft((current) => (current.trim() ? current : text))
      setSendError(`Не отправлено: ${describeSendError(error)}`)
      // Пока «призрак» был в ленте, снимок сервера мог обрезать её начало —
      // один тихий перечит возвращает ровно серверные строки.
      void refresh({ silent: true, requestReload: true })
    } finally {
      sendingRef.current = false
      if (mountedRef.current) setSending(false)
    }
  }

  if (!token || !container) {
    return null
  }

  // Тот же слой, что у диалогов: выше/ниже решает порядок в DOM (см. шапку файла).
  const zIndex = (theme: { zIndex: { modal: number } }) => theme.zIndex.modal

  return createPortal(
    <>
      <Button
        type="button"
        variant="contained"
        startIcon={<ChatBubbleOutlineRoundedIcon />}
        onClick={toggleOpen}
        aria-label="Помощник"
        aria-expanded={open}
        data-testid="assistant-toggle"
        sx={{ ...cornerButtonSx, zIndex }}
      >
        Помощник
      </Button>

      {open ? (
        <Paper
          elevation={8}
          role="region"
          aria-label="Помощник"
          data-testid="assistant-window"
          data-expanded={expanded ? '1' : '0'}
          sx={{
            position: 'fixed',
            zIndex,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            right: EDGE_GAP,
            bottom: WINDOW_BOTTOM,
            ...(expanded
              ? {
                  top: APP_BAR_HEIGHT + EDGE_GAP,
                  left: FF_DRAWER_WIDTH + EDGE_GAP,
                }
              : {
                  width: 400,
                  maxWidth: `calc(100vw - ${EDGE_GAP * 2}px)`,
                  height: COMPACT_HEIGHT,
                  maxHeight: `calc(100vh - ${COMPACT_TOP_MIN + WINDOW_BOTTOM}px)`,
                }),
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              px: 2,
              py: 1,
            }}
          >
            <Typography variant="subtitle1" sx={{ flex: 1, fontWeight: 700 }}>
              Помощник
            </Typography>
            {expanded ? (
              <Button
                type="button"
                size="small"
                onClick={() => setExpandedPersist(false)}
                data-testid="assistant-collapse"
              >
                Свернуть
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  size="small"
                  onClick={() => setExpandedPersist(true)}
                  data-testid="assistant-expand"
                >
                  Развернуть
                </Button>
                <Button type="button" size="small" onClick={closeWindow} data-testid="assistant-close">
                  Свернуть
                </Button>
              </>
            )}
          </Box>
          <Divider />

          <Box
            ref={listRef}
            data-testid="assistant-messages"
            sx={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              overflowX: 'hidden',
              px: 2,
              py: 1.5,
              display: 'flex',
              flexDirection: 'column',
              gap: 1.5,
            }}
          >
            {loadError ? (
              <Typography variant="body2" color="error" data-testid="assistant-load-error">
                {loadError}
              </Typography>
            ) : null}
            {loaded && !loadError && messages.length === 0 ? (
              <Typography variant="body2" color="text.secondary" data-testid="assistant-empty">
                Сообщений пока нет.
              </Typography>
            ) : null}
            {messages.map((m) => (
              <Box key={m.id} sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Box sx={{ alignSelf: 'flex-end', maxWidth: '85%', minWidth: 0 }}>
                  <Paper
                    variant="outlined"
                    data-testid={`assistant-message-${m.id}`}
                    sx={(theme) => ({
                      px: 1.5,
                      py: 1,
                      bgcolor: alpha(theme.palette.primary.main, 0.08),
                      borderColor: alpha(theme.palette.primary.main, 0.2),
                    })}
                  >
                    <Typography variant="body2" sx={messageTextSx}>
                      {m.message_text}
                    </Typography>
                  </Paper>
                  {m.screen_title ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      component="div"
                      sx={{ mt: 0.25, textAlign: 'right', ...messageTextSx }}
                      data-testid={`assistant-screen-${m.id}`}
                    >
                      Экран: {m.screen_title}
                    </Typography>
                  ) : null}
                </Box>
                {m.answer_text ? (
                  <Box sx={{ alignSelf: 'flex-start', maxWidth: '85%', minWidth: 0 }}>
                    <Paper
                      variant="outlined"
                      data-testid={`assistant-answer-${m.id}`}
                      sx={{ px: 1.5, py: 1 }}
                    >
                      <Typography variant="body2" sx={messageTextSx}>
                        {m.answer_text}
                      </Typography>
                    </Paper>
                    {m.backlog_number ? (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        component="div"
                        sx={{ mt: 0.25 }}
                        data-testid={`assistant-backlog-${m.id}`}
                      >
                        Задача {m.backlog_number}
                      </Typography>
                    ) : null}
                  </Box>
                ) : m.waiting ? (
                  <Box
                    sx={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 1 }}
                    data-testid={`assistant-waiting-${m.id}`}
                  >
                    <CircularProgress size={14} />
                    <Typography variant="body2" color="text.secondary">
                      Готовлю ответ
                    </Typography>
                  </Box>
                ) : null}
              </Box>
            ))}
          </Box>

          <Divider />
          <Box sx={{ px: 2, py: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
            {sendError ? (
              <Typography variant="body2" color="error" sx={messageTextSx} data-testid="assistant-send-error">
                {sendError}
              </Typography>
            ) : null}
            <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
              <TextField
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  // Enter — отправить, Shift+Enter — перенос строки.
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    void send()
                  }
                }}
                placeholder="Напишите, что нужно"
                multiline
                minRows={1}
                maxRows={expanded ? 8 : 4}
                fullWidth
                disabled={sending}
                slotProps={{
                  htmlInput: {
                    maxLength: ASSISTANT_MESSAGE_MAX_CHARS,
                    'data-testid': 'assistant-input',
                  },
                }}
              />
              <Button
                type="button"
                variant="contained"
                size="small"
                onClick={() => void send()}
                disabled={sending || !draft.trim()}
                data-testid="assistant-send"
                sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                Отправить
              </Button>
            </Box>
          </Box>
        </Paper>
      ) : null}
    </>,
    container,
  )
}

const cornerButtonSx = {
  position: 'fixed',
  right: EDGE_GAP,
  bottom: EDGE_GAP,
  height: BUTTON_HEIGHT,
  borderRadius: 999,
  px: 2,
  boxShadow: 6,
} as const

// Длинные сообщения и названия товаров переносятся, горизонтальной прокрутки нет (C20).
const messageTextSx = {
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
} as const
