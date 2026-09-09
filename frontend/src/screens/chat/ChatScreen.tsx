// Full chat screen for the FF portal — WMS-397.
//
// Lists conversations on the left, opens the selected one in a right pane
// with ChatFeed + ChatComposer. Sellers see only their conversations
// (the API enforces that); FF admins see the whole tenant, sorted with
// main chats first.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { ChatComposer } from '../../components/chat/ChatComposer'
import { ChatFeed } from '../../components/chat/ChatFeed'
import { ExtraChatCreateDialog } from '../../components/chat/ExtraChatCreateDialog'
import {
  listConversations,
  listMessages,
  type ChatConversation,
  type ChatMessage,
} from '../../components/chat/chatApi'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  currentUserId: string | null
  sellers: SellerRow[]
  // WMS-397/399 gap 3: only FF admins may spin up an extra chat, so the
  // "Новый чат" button hides for everyone else. The backend enforces the
  // same rule (require_fulfillment_admin on POST /conversations/extra), so
  // this flag is a UX affordance, not an access boundary.
  isFulfillmentAdmin?: boolean
}

function sellerLabel(sellers: SellerRow[], sellerId: string): string {
  const row = sellers.find((item) => item.id === sellerId)
  return row?.name ?? sellerId.slice(0, 8)
}

export function ChatScreen({
  token,
  authHeaders,
  currentUserId,
  sellers,
  isFulfillmentAdmin = false,
}: Props) {
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const loadConversations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await listConversations(token, authHeaders)
      setConversations(rows)
      if (rows.length > 0 && selectedId === null) {
        setSelectedId(rows[0].id)
      }
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setLoading(false)
    }
  }, [authHeaders, selectedId, token])

  const loadMessages = useCallback(
    async (conversationId: string) => {
      try {
        const items = await listMessages(token, authHeaders, conversationId)
        setMessages(items)
      } catch (exc) {
        setError((exc as Error).message)
      }
    },
    [authHeaders, token],
  )

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  useEffect(() => {
    if (selectedId) void loadMessages(selectedId)
  }, [loadMessages, selectedId])

  const selected = useMemo(
    () => conversations.find((row) => row.id === selectedId) ?? null,
    [conversations, selectedId],
  )

  const handleSent = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 96px)', gap: 2, p: 2 }}>
      <Paper variant="outlined" sx={{ width: 320, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Typography variant="h6">Чаты</Typography>
          <Typography variant="caption" color="text.secondary">
            Основной чат каждого продавца создаётся при первом обращении.
          </Typography>
        </Box>
        {error ? (
          <Alert severity="error" sx={{ m: 1 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
        {loading && conversations.length === 0 ? (
          <Stack sx={{ py: 4, alignItems: 'center' }}>
            <CircularProgress size={20} />
          </Stack>
        ) : (
          <List sx={{ overflowY: 'auto', flex: 1, py: 0 }} data-testid="chat-conversation-list">
            {conversations.map((conv) => (
              <ListItemButton
                key={conv.id}
                selected={conv.id === selectedId}
                onClick={() => setSelectedId(conv.id)}
                data-testid="chat-conversation-row"
              >
                <ListItemText
                  primary={conv.title ?? sellerLabel(sellers, conv.seller_id)}
                  secondary={conv.kind === 'main' ? 'Основной чат' : sellerLabel(sellers, conv.seller_id)}
                />
              </ListItemButton>
            ))}
          </List>
        )}
        <Box sx={{ p: 1, borderTop: 1, borderColor: 'divider' }}>
          {isFulfillmentAdmin ? (
            <Button
              size="small"
              fullWidth
              variant="contained"
              onClick={() => setCreateOpen(true)}
              data-testid="chat-extra-create-open"
              sx={{ mb: 1 }}
            >
              Новый чат
            </Button>
          ) : null}
          <Button size="small" fullWidth onClick={() => void loadConversations()}>
            Обновить список
          </Button>
        </Box>
      </Paper>

      {isFulfillmentAdmin ? (
        <ExtraChatCreateDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          token={token}
          authHeaders={authHeaders}
          sellers={sellers}
          onCreated={(conv) => {
            setConversations((prev) => [conv, ...prev.filter((row) => row.id !== conv.id)])
            setSelectedId(conv.id)
          }}
        />
      ) : null}

      <Paper
        variant="outlined"
        sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}
      >
        {selected ? (
          <>
            <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
              <Typography variant="subtitle1">
                {selected.title ?? sellerLabel(sellers, selected.seller_id)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {selected.kind === 'main' ? 'Основной чат' : 'Дополнительный чат'} ·{' '}
                {sellerLabel(sellers, selected.seller_id)}
              </Typography>
            </Box>
            <Box sx={{ flex: 1, overflowY: 'auto', bgcolor: 'grey.50' }}>
              <ChatFeed currentUserId={currentUserId} messages={messages} />
            </Box>
            <ChatComposer
              token={token}
              authHeaders={authHeaders}
              conversationId={selected.id}
              onSent={handleSent}
            />
          </>
        ) : (
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography color="text.secondary">
              Выберите чат в списке слева или откройте его со страницы документа.
            </Typography>
          </Box>
        )}
      </Paper>
    </Box>
  )
}
