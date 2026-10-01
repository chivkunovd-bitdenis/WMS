import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'

// WMS-433: переписка с AI-помощником. Контракт — backend/app/api/assistant.py.

export type AssistantMessageRow = {
  id: string
  message_text: string
  screen_title: string
  created_at: string
  answer_text: string | null
  answered_at: string | null
  backlog_number: string | null
  // true, пока ответа нет — в ленте это «Готовлю ответ» (R7, R22).
  waiting: boolean
}

export type AssistantSendBody = {
  // Генерируется один раз на попытку отправки и переиспользуется при повторе
  // после сбоя: сервер по нему не создаёт вторую строку (R21).
  client_message_id: string
  message_text: string
  screen_path: string
  screen_title: string
  screen_text: string
}

// Совпадает с MESSAGE_TEXT_MAX_CHARS на сервере.
export const ASSISTANT_MESSAGE_MAX_CHARS = 8000

const BAD_RESPONSE_SHAPE = 'неожиданный ответ сервера'

// WMS-433/R23: код отказа сервера, когда помощник выключен для тенанта
// (403, detail.code). Панель по нему не показывает ошибку, а убирает себя и
// прекращает опрос — например, если переменную переключили, пока окно открыто.
export const ASSISTANT_DISABLED_CODE = 'assistant_disabled'

export class AssistantDisabledError extends Error {
  constructor() {
    super('помощник выключен для вашей организации')
    this.name = 'AssistantDisabledError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

async function isAssistantDisabledResponse(res: Response): Promise<boolean> {
  if (res.status !== 403) {
    return false
  }
  try {
    // Тело читается с копии: оригинал ещё нужен describeFailure для текста.
    const data = (await res.clone().json()) as { detail?: unknown }
    const detail = data.detail
    if (detail === ASSISTANT_DISABLED_CODE) {
      return true
    }
    return isRecord(detail) && detail.code === ASSISTANT_DISABLED_CODE
  } catch {
    return false
  }
}

async function failureFromResponse(res: Response): Promise<Error> {
  if (await isAssistantDisabledResponse(res)) {
    return new AssistantDisabledError()
  }
  return new Error(await describeFailure(res))
}

// Ответ сервера проверяется по форме, а не берётся на веру: тело 200 без
// нужных полей (прокси, заглушка, чужой сервер) — это ошибка загрузки ленты,
// а не повод уронить каркас портала.
export function parseAssistantMessage(raw: unknown): AssistantMessageRow | null {
  if (!isRecord(raw) || typeof raw.id !== 'string' || typeof raw.message_text !== 'string') {
    return null
  }
  const answerText = typeof raw.answer_text === 'string' ? raw.answer_text : null
  return {
    id: raw.id,
    message_text: raw.message_text,
    screen_title: typeof raw.screen_title === 'string' ? raw.screen_title : '',
    created_at: typeof raw.created_at === 'string' ? raw.created_at : '',
    answer_text: answerText,
    answered_at: typeof raw.answered_at === 'string' ? raw.answered_at : null,
    backlog_number: typeof raw.backlog_number === 'string' ? raw.backlog_number : null,
    waiting: typeof raw.waiting === 'boolean' ? raw.waiting : answerText === null,
  }
}

export function parseAssistantConversation(body: unknown): AssistantMessageRow[] {
  if (!isRecord(body) || !Array.isArray(body.messages)) {
    throw new Error(BAD_RESPONSE_SHAPE)
  }
  const rows: AssistantMessageRow[] = []
  for (const item of body.messages) {
    const row = parseAssistantMessage(item)
    if (row === null) {
      throw new Error(BAD_RESPONSE_SHAPE)
    }
    rows.push(row)
  }
  return rows
}

async function readJsonBody(res: Response): Promise<unknown> {
  try {
    return (await res.json()) as unknown
  } catch {
    throw new Error(BAD_RESPONSE_SHAPE)
  }
}

export async function fetchAssistantConversation(
  token: string,
  signal?: AbortSignal,
): Promise<AssistantMessageRow[]> {
  const res = await fetch(apiUrl('/assistant/messages'), {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!res.ok) {
    throw await failureFromResponse(res)
  }
  return parseAssistantConversation(await readJsonBody(res))
}

export async function sendAssistantMessage(
  token: string,
  body: AssistantSendBody,
): Promise<AssistantMessageRow> {
  const res = await fetch(apiUrl('/assistant/messages'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw await failureFromResponse(res)
  }
  const row = parseAssistantMessage(await readJsonBody(res))
  if (row === null) {
    throw new Error(BAD_RESPONSE_SHAPE)
  }
  return row
}

// Причина сбоя одной строкой (R21). Ответ 5xx или ответ прокси без JSON —
// «сервер недоступен», а не HTML-простыня; ошибки 4xx — как их описал сервер.
async function describeFailure(res: Response): Promise<string> {
  if (res.status >= 500) {
    return 'сервер недоступен'
  }
  if (res.status === 401) {
    return 'войдите заново'
  }
  return await readApiErrorMessage(res)
}

// fetch бросает TypeError, когда до сервера не достучаться вовсе.
export function describeSendError(error: unknown): string {
  if (error instanceof TypeError) {
    return 'нет связи с сервером'
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return 'неизвестная ошибка'
}
