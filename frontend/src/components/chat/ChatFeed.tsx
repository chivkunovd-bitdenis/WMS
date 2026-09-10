// Message feed with authenticated files, document links and author editing.

import { memo, useMemo, useState } from 'react'
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material'
import { ChatAttachmentView } from './ChatAttachmentView'
import { AttachedDocCard } from './AttachedDocCard'
import { editMessage, type ChatMessage } from './chatApi'

type Props = {
  currentUserId: string | null
  messages: ChatMessage[]
  token: string
  authHeaders: (token: string) => Record<string, string>
  onChanged: (message: ChatMessage) => void
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
    })
  } catch {
    return iso
  }
}

export const ChatFeed = memo(function ChatFeed({ currentUserId, messages, token, authHeaders, onChanged }: Props) {
  const [editing, setEditing] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    if (!editing || busy) return
    setBusy(true); setError(null)
    try { onChanged(await editMessage(token, authHeaders, editing, text)); setEditing(null) }
    catch { setError('Не удалось сохранить. Текст правки сохранён, повторите.') }
    finally { setBusy(false) }
  }
  const rows = useMemo(() => messages, [messages])
  if (rows.length === 0) {
    return (
      <Box sx={{ px: 3, py: 6, textAlign: 'center' }}>
        <Typography color="text.secondary">Сообщений пока нет.</Typography>
      </Box>
    )
  }
  return (
    <Stack spacing={1.25} sx={{ p: 2 }}>
      {rows.map((message) => {
        const mine = currentUserId !== null && message.author_user_id === currentUserId
        return (
          <Box
            key={message.id}
            sx={{
              display: 'flex',
              justifyContent: mine ? 'flex-end' : 'flex-start',
            }}
            data-testid="chat-message-row"
            data-mine={mine ? 'true' : 'false'}
          >
            <Box
              sx={{
                maxWidth: '78%',
                bgcolor: mine ? 'primary.light' : 'grey.100',
                color: mine ? 'primary.contrastText' : 'text.primary',
                borderRadius: 2,
                px: 1.5,
                py: 1,
              }}
            >
              <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>{message.author_label}</Typography>
              {message.attached_document ? (
                <Box sx={{ mb: message.text ? 0.75 : 0 }}>
                  <AttachedDocCard document={message.attached_document} />
                </Box>
              ) : null}
              {message.text ? (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {message.text}
                </Typography>
              ) : null}
              <Stack spacing={1} sx={{ mt: 1 }}>
                {message.attachments.map((attachment) => <ChatAttachmentView key={attachment.id}
                  attachment={attachment} token={token} authHeaders={authHeaders} />)}
              </Stack>
              {editing === message.id ? <Box>
                {error && <Alert severity="error">{error}</Alert>}
                <TextField multiline fullWidth value={text} disabled={busy}
                  onChange={(event) => setText(event.target.value)} label="Текст сообщения" />
                <Button disabled={busy || !text.trim()} onClick={() => void save()}>Сохранить</Button>
                <Button disabled={busy} onClick={() => setEditing(null)}>Отмена</Button>
              </Box> : mine && <Button size="small" color="inherit"
                onClick={() => { setEditing(message.id); setText(message.text); setError(null) }}>Изменить</Button>}
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mt: 0.5,
                  opacity: 0.75,
                  textAlign: 'right',
                }}
              >
                {formatTime(message.created_at)}
                {message.edited_at ? ' · изменено' : ''}
              </Typography>
            </Box>
          </Box>
        )
      })}
    </Stack>
  )
})
