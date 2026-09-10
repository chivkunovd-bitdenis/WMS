// Chat REST client for WMS-397/WMS-399.
//
// All endpoints live under /operations/chat and reuse the same auth headers
// as the rest of the FF portal. The client returns typed rows so screens
// don't repeat the /operations/chat path template in fifteen places.

import { apiUrl } from '../../api'

export type ChatConversation = {
  id: string
  tenant_id: string
  seller_id: string
  kind: 'main' | 'extra'
  title: string | null
  created_at: string
  updated_at: string
}

export type ChatAttachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  is_image: boolean
  created_at: string
}

export type AttachedDocument = {
  kind: string
  id: string
  title: string
  seller_id: string
  seller_name?: string
}

export type ChatMessage = {
  id: string
  conversation_id: string
  author_user_id: string
  author_label: string
  client_message_id: string
  text: string
  attached_document: AttachedDocument | null
  attachments: ChatAttachment[]
  edited_at: string | null
  deleted_at: string | null
  created_at: string
}

type HeaderFn = (token: string) => Record<string, string>

export class ChatApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new ChatApiError(response.status, `chat_api_${response.status}:${text.slice(0, 200)}`)
  }
  return (await response.json()) as T
}

export async function listConversations(
  token: string,
  authHeaders: HeaderFn,
): Promise<ChatConversation[]> {
  const response = await fetch(apiUrl('/operations/chat/conversations'), {
    headers: { ...authHeaders(token) },
  })
  const body = await jsonOrThrow<{ items: ChatConversation[] }>(response)
  return body.items
}

export async function ensureMainChat(
  token: string,
  authHeaders: HeaderFn,
  sellerId?: string,
): Promise<ChatConversation> {
  const query = sellerId ? `?seller_id=${encodeURIComponent(sellerId)}` : ''
  const response = await fetch(apiUrl(`/operations/chat/conversations/main${query}`), {
    headers: { ...authHeaders(token) },
  })
  return await jsonOrThrow<ChatConversation>(response)
}

export async function createExtraChat(
  token: string,
  authHeaders: HeaderFn,
  input: { seller_id: string; title: string; participant_user_ids?: string[] },
): Promise<ChatConversation> {
  const response = await fetch(apiUrl('/operations/chat/conversations/extra'), {
    method: 'POST',
    headers: {
      ...authHeaders(token),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      seller_id: input.seller_id,
      title: input.title,
      participant_user_ids: input.participant_user_ids ?? [],
    }),
  })
  return await jsonOrThrow<ChatConversation>(response)
}

export async function listMessages(
  token: string,
  authHeaders: HeaderFn,
  conversationId: string,
  before?: string,
): Promise<ChatMessage[]> {
  const response = await fetch(
    apiUrl(`/operations/chat/conversations/${conversationId}/messages${before ? `?before=${before}` : ''}`),
    { headers: { ...authHeaders(token) } },
  )
  const body = await jsonOrThrow<{ items: ChatMessage[] }>(response)
  return body.items
}

export type SendMessageInput = {
  clientMessageId: string
  text: string
  attachmentIds?: string[]
  attachedDocument?: AttachedDocument
}

export async function sendMessage(
  token: string,
  authHeaders: HeaderFn,
  conversationId: string,
  input: SendMessageInput,
): Promise<ChatMessage> {
  const body: Record<string, unknown> = {
    client_message_id: input.clientMessageId,
    text: input.text,
    attachment_ids: input.attachmentIds ?? [],
  }
  if (input.attachedDocument) {
    body.attached_document = input.attachedDocument
  }
  const response = await fetch(
    apiUrl(`/operations/chat/conversations/${conversationId}/messages`),
    {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    },
  )
  return await jsonOrThrow<ChatMessage>(response)
}

export async function editMessage(
  token: string,
  authHeaders: HeaderFn,
  messageId: string,
  text: string,
): Promise<ChatMessage> {
  const response = await fetch(apiUrl(`/operations/chat/messages/${messageId}`), {
    method: 'PATCH',
    headers: {
      ...authHeaders(token),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text }),
  })
  return await jsonOrThrow<ChatMessage>(response)
}

export async function uploadAttachment(
  token: string,
  authHeaders: HeaderFn,
  conversationId: string,
  file: File | Blob,
  filename: string,
  isImage?: boolean,
): Promise<ChatAttachment> {
  const form = new FormData()
  form.append('file', file, filename)
  if (isImage !== undefined) {
    form.append('is_image', String(isImage))
  }
  const response = await fetch(
    apiUrl(`/operations/chat/conversations/${conversationId}/attachments`),
    {
      method: 'POST',
      headers: { ...authHeaders(token) },
      body: form,
    },
  )
  return await jsonOrThrow<ChatAttachment>(response)
}

export function attachmentContentUrl(attachmentId: string): string {
  return apiUrl(`/operations/chat/attachments/${attachmentId}/content`)
}

// Small helper so callers don't hand-roll uuid-ish tokens.
export function makeClientMessageId(): string {
  const rand = Math.random().toString(36).slice(2, 10)
  return `cli-${Date.now().toString(36)}-${rand}`
}
