import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AssistantDisabledError,
  fetchAssistantConversation,
  sendAssistantMessage,
} from './assistantApi'

// WMS-433/R23: отказ «помощник выключен для тенанта» панель должна отличать
// от прочих сбоев — по нему она убирает себя, а не показывает ошибку.

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('assistantApi: отказ assistant_disabled', () => {
  it('GET /assistant/messages с 403 {code: assistant_disabled} → AssistantDisabledError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json(403, { detail: { code: 'assistant_disabled', message: 'Помощник ИИ выключен.' } }),
      ),
    )
    await expect(fetchAssistantConversation('t')).rejects.toBeInstanceOf(AssistantDisabledError)
  })

  it('POST /assistant/messages с 403 и плоским detail = assistant_disabled → AssistantDisabledError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(403, { detail: 'assistant_disabled' })))
    await expect(
      sendAssistantMessage('t', {
        client_message_id: 'c1',
        message_text: 'x',
        screen_path: '/',
        screen_title: '',
        screen_text: '',
      }),
    ).rejects.toBeInstanceOf(AssistantDisabledError)
  })

  it('403 с другим кодом — обычная ошибка с текстом сервера, не отказ помощника', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(403, { detail: 'forbidden' })))
    const error = await fetchAssistantConversation('t').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(Error)
    expect(error).not.toBeInstanceOf(AssistantDisabledError)
    expect((error as Error).message).toBe('forbidden')
  })

  it('5xx — «сервер недоступен», не отказ помощника', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })))
    const error = await fetchAssistantConversation('t').catch((e: unknown) => e)
    expect(error).not.toBeInstanceOf(AssistantDisabledError)
    expect((error as Error).message).toBe('сервер недоступен')
  })
})
