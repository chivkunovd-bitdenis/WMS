// Compact anchored document composer. Full history stays on the chat page.
import { useEffect, useState } from 'react'
import { Alert, Box, Button, Popover, Typography } from '@mui/material'
import { useLocation, useNavigate } from 'react-router-dom'
import { ChatComposer } from './ChatComposer'
import { ensureMainChat, type AttachedDocument, type ChatConversation } from './chatApi'

type Props = {
  anchorEl: HTMLElement | null
  open: boolean
  onClose: () => void
  token: string
  authHeaders: (token: string) => Record<string, string>
  currentUserId: string | null
  sellerId: string
  sellerName?: string
  attachedDocument?: AttachedDocument
}
export function ChatDialog({ anchorEl, open, onClose, token, authHeaders, sellerId, sellerName, attachedDocument }: Props) {
  const [conversation, setConversation] = useState<ChatConversation | null>(null)
  const [error, setError] = useState(false)
  const [sent, setSent] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  useEffect(() => {
    if (!open) return
    let active = true
    void ensureMainChat(token, authHeaders, sellerId).then((c) => { if (active) setConversation(c) })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [open, token, authHeaders, sellerId])
  const base = location.pathname.startsWith('/app/ff') ? '/app/ff' : location.pathname.startsWith('/app/seller') ? '/app/seller' : ''
  return <Popover open={open} anchorEl={anchorEl} onClose={onClose}
    onClick={(event) => event.stopPropagation()}
    onKeyDown={(event) => event.stopPropagation()}
    anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
    transformOrigin={{ vertical: 'top', horizontal: 'right' }}
    slotProps={{ paper: { sx: { width: 440, maxWidth: '95vw' } } }}>
    <Box sx={{ p: 1.5 }}>
      <Typography variant="subtitle2">{sellerName ?? 'Основной чат продавца'}</Typography>
      {attachedDocument && <Typography variant="caption">{attachedDocument.title}</Typography>}
      {error && <Alert severity="error">Не удалось открыть чат. Закройте форму и повторите.</Alert>}
      {sent && <Alert severity="success">Сообщение отправлено</Alert>}
    </Box>
    {conversation && <ChatComposer key={conversation.id} token={token} authHeaders={authHeaders}
      conversationId={conversation.id} attachedDocument={attachedDocument} autoFocus onSent={() => setSent(true)} />}
    <Button onClick={() => { navigate(`${base}/chat?seller_id=${sellerId}`); onClose() }}>Перейти в полный чат</Button>
  </Popover>
}
