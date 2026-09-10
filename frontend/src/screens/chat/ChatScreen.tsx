import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Alert, Box, Button, List, ListItemButton, ListItemText, Paper, Typography } from '@mui/material'
import { ChatComposer } from '../../components/chat/ChatComposer'
import { ChatFeed } from '../../components/chat/ChatFeed'
import { ExtraChatCreateDialog } from '../../components/chat/ExtraChatCreateDialog'
import { ChatParticipants } from '../../components/chat/ChatParticipants'
import { ChatApiError, listConversations, listMessages, type ChatConversation, type ChatMessage } from '../../components/chat/chatApi'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  currentUserId: string | null
  sellers: { id: string; name: string }[]
  isFulfillmentAdmin?: boolean
}
export function ChatScreen({ token, authHeaders, currentUserId, sellers, isFulfillmentAdmin = false }: Props) {
  const [params] = useSearchParams()
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [membersOpen, setMembersOpen] = useState(false)
  const [olderBusy, setOlderBusy] = useState(false)
  const selectedRef = useRef(selectedId)
  selectedRef.current = selectedId
  const desiredSeller = params.get('seller_id')
  const loadConversations = useCallback(async () => {
    try {
      const rows = await listConversations(token, authHeaders)
      setConversations(rows)
      setSelectedId((id) => id && rows.some((r) => r.id === id) ? id :
        (rows.find((r) => r.kind === 'main' && r.seller_id === desiredSeller) ?? rows[0])?.id ?? null)
    } catch { setError('Не удалось загрузить чаты. Повторите обновление.') }
  }, [token, authHeaders, desiredSeller])
  useEffect(() => { void loadConversations() }, [loadConversations])
  useEffect(() => {
    if (!selectedId) return
    let active = true
    setMessages([]); setError(null)
    const load = async () => {
      try {
        const items = await listMessages(token, authHeaders, selectedId)
        if (active) setError(null)
        if (active) setMessages((old) => {
          const map = new Map(old.map((m) => [m.id, m]))
          items.forEach((m) => map.set(m.id, m))
          return Array.from(map.values()).sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
        })
      } catch (exc) { if (active) {
        if (exc instanceof ChatApiError && [401, 403, 404].includes(exc.status)) setMessages([])
        setError('Не удалось прочитать чат. Проверьте соединение и доступ.')
      } }
    }
    void load()
    const timer = window.setInterval(() => void load(), 4000)
    return () => { active = false; window.clearInterval(timer) }
  }, [selectedId, token, authHeaders])
  const changed = useCallback((msg: ChatMessage) => {
    if (msg.conversation_id !== selectedRef.current) return
    setMessages((rows) => [...rows.filter((r) => r.id !== msg.id), msg]
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)))
  }, [])
  // Лента без управления прокруткой открывалась на самом старом из последних
  // 200 сообщений, а только что отправленное уходило за нижний край. Держимся
  // низа, пока оператор сам не ушёл читать историю вверх.
  const feed = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  useEffect(() => { stickToBottom.current = true }, [selectedId])
  useEffect(() => {
    const node = feed.current
    if (node && stickToBottom.current) node.scrollTop = node.scrollHeight
  }, [messages, selectedId])
  const selected = conversations.find((r) => r.id === selectedId)
  const label = (c: ChatConversation) => c.title ?? sellers.find((s) => s.id === c.seller_id)?.name ?? 'Основной чат'
  const older = async () => {
    if (!selectedId || !messages.length || olderBusy) return
    const id = selectedId
    setOlderBusy(true)
    try {
      const rows = await listMessages(token, authHeaders, id, messages[0].id)
      if (selectedRef.current === id) rows.forEach(changed)
    } catch { setError('Не удалось загрузить предыдущие сообщения.') }
    finally { setOlderBusy(false) }
  }
  return <Box sx={{ display: 'flex', height: 'calc(100vh - 110px)', gap: 1, p: 1 }}>
    <Paper variant="outlined" sx={{ width: { xs: 170, md: 280 }, overflowY: 'auto' }}>
      <Typography variant="h6" sx={{ p: 1 }}>Чаты</Typography>
      <List>{conversations.map((c) => <ListItemButton key={c.id} selected={c.id === selectedId}
        onClick={() => { setMessages([]); setSelectedId(c.id) }}>
        <ListItemText primary={label(c)} secondary={c.kind === 'main' ? 'Основной чат' : 'Дополнительный чат'} />
      </ListItemButton>)}</List>
      {isFulfillmentAdmin && <Button onClick={() => setCreateOpen(true)}>Новый чат</Button>}
      <Button onClick={() => void loadConversations()}>Обновить список</Button>
    </Paper>
    <Paper variant="outlined" sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {error && <Alert severity="error">{error}</Alert>}
      {selected ? <>
        <Box sx={{ p: 1.5, borderBottom: 1, borderColor: 'divider' }}>
          <Typography variant="h6">{label(selected)}</Typography>
          {isFulfillmentAdmin && selected.kind === 'extra' && <Button onClick={() => setMembersOpen(true)}>Участники</Button>}
        </Box>
        <Box ref={feed} sx={{ flex: 1, overflowY: 'auto' }}
          onScroll={(event) => {
            const node = event.currentTarget
            stickToBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80
          }}>
          {messages.length > 0 && <Button disabled={olderBusy} onClick={() => void older()}>Предыдущие сообщения</Button>}
          <ChatFeed key={selected.id} token={token} authHeaders={authHeaders} currentUserId={currentUserId}
            messages={messages} onChanged={changed} />
        </Box>
        <ChatComposer key={selected.id} token={token} authHeaders={authHeaders} conversationId={selected.id} onSent={changed} />
        {membersOpen && <ChatParticipants token={token} authHeaders={authHeaders} conversation={selected}
          onClose={() => setMembersOpen(false)} />}
      </> : <Typography sx={{ p: 3 }}>Выберите чат.</Typography>}
    </Paper>
    {isFulfillmentAdmin && <ExtraChatCreateDialog open={createOpen} onClose={() => setCreateOpen(false)} token={token}
      authHeaders={authHeaders} sellers={sellers} onCreated={(c) => { setConversations((rows) => [...rows, c]); setSelectedId(c.id) }} />}
  </Box>
}
