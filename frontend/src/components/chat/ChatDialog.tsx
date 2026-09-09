// Compact chat dialog opened from a document page.
//
// The dialog materialises the main chat for the passed seller (idempotent on
// the server), loads the last messages and lets the FF operator type a note
// attached to the current document. Reuses ChatComposer + ChatFeed so the
// full-screen ChatScreen and this dialog stay in lockstep.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { ChatComposer } from './ChatComposer'
import { ChatFeed } from './ChatFeed'
import {
  ensureMainChat,
  listMessages,
  type AttachedDocument,
  type ChatConversation,
  type ChatMessage,
} from './chatApi'

type Props = {
  open: boolean
  onClose: () => void
  token: string
  authHeaders: (token: string) => Record<string, string>
  currentUserId: string | null
  sellerId: string
  sellerName?: string
  attachedDocument?: AttachedDocument
}

export function ChatDialog({
  open,
  onClose,
  token,
  authHeaders,
  currentUserId,
  sellerId,
  sellerName,
  attachedDocument,
}: Props) {
  const [conversation, setConversation] = useState<ChatConversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const title = useMemo(
    () => (sellerName ? `Чат с ${sellerName}` : 'Чат с продавцом'),
    [sellerName],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const conv = await ensureMainChat(token, authHeaders, sellerId)
      const items = await listMessages(token, authHeaders, conv.id)
      setConversation(conv)
      setMessages(items)
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setLoading(false)
    }
  }, [authHeaders, sellerId, token])

  useEffect(() => {
    if (!open) return
    void load()
  }, [load, open])

  const handleSent = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      slotProps={{
        paper: { sx: { height: '80vh', display: 'flex', flexDirection: 'column' } },
      }}
    >
      <DialogTitle sx={{ pr: 6 }}>
        {title}
        <IconButton
          aria-label="Закрыть"
          onClick={onClose}
          sx={{ position: 'absolute', right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent
        sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 0, overflow: 'hidden' }}
      >
        {error ? (
          <Alert severity="error" sx={{ m: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
        <Box sx={{ flex: 1, overflowY: 'auto', bgcolor: 'grey.50' }}>
          {loading && messages.length === 0 ? (
            <Stack sx={{ py: 4, alignItems: 'center' }}>
              <CircularProgress size={24} />
            </Stack>
          ) : (
            <ChatFeed currentUserId={currentUserId} messages={messages} />
          )}
        </Box>
        {attachedDocument ? (
          <Box sx={{ px: 2, py: 1, borderTop: 1, borderColor: 'divider', bgcolor: '#fafafa' }}>
            <Typography variant="caption" color="text.secondary">
              К сообщению прикреплён документ: {attachedDocument.title}
            </Typography>
          </Box>
        ) : null}
        {conversation ? (
          <ChatComposer
            token={token}
            authHeaders={authHeaders}
            conversationId={conversation.id}
            attachedDocument={attachedDocument}
            autoFocus
            onSent={handleSent}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
