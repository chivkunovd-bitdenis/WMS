import { useMemo, useRef, useState } from 'react'
import { Box, Button, Chip, Divider, IconButton, Stack, TextField, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import SendIcon from '@mui/icons-material/SendRounded'
import { useStore } from '../state/store'
import { EmptyState } from '../common/EmptyState'
import { MessageBubble } from './MessageBubble'
import { visibleMessagesForActor } from '../state/selectors'
import { Row } from '../common/Row'
import type { Conversation } from '../types'

export function ThreadPanel({ conversation }: { conversation: Conversation }) {
  const { ui, dispatch, data, currentActor, actions } = useStore()
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const [text, setText] = useState('')

  const rootId = ui.openThreadRootId
  const root = rootId ? data.messages.get(rootId) : null

  const items = useMemo(() => {
    if (!root) return []
    const ids = data.messagesByConversation.get(conversation.id) ?? []
    const list = ids
      .map((id) => data.messages.get(id))
      .filter((m): m is NonNullable<typeof m> => Boolean(m))
      .filter((m) => m.threadRootId === root.id)
    return visibleMessagesForActor(list, currentActor)
  }, [root, data.messages, data.messagesByConversation, conversation.id, currentActor])

  if (!root) {
    return <EmptyState title="Обсуждение не выбрано" description="Нажмите на «Обсуждение» под сообщением, чтобы открыть ветку здесь." />
  }

  const rootVisible = currentActor.role !== 'seller' || root.visibility === 'shared'

  if (!rootVisible) {
    return <EmptyState title="Нет доступа к обсуждению" description="Корневое сообщение — внутренняя заметка склада." />
  }

  const send = () => {
    if (!text.trim()) return
    actions.sendMessage(conversation.id, {
      text,
      visibility: root.visibility,
      attachments: [],
      threadRootId: root.id,
    })
    setText('')
  }

  return (
    <Stack sx={{ height: '100%' }}>
      <Row align="center" spacing={1} sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Chip size="small" color="primary" label="Обсуждение" />
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          Ветка от {new Date(root.createdAt).toLocaleString('ru-RU')}
        </Typography>
        <IconButton size="small" aria-label="Закрыть" onClick={() => dispatch({ type: 'open_thread', rootId: null })}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Row>
      <Box sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider', bgcolor: (t) => t.palette.action.hover }}>
        <MessageBubble message={root} conversation={conversation} isThread />
      </Box>
      <Divider />
      <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', p: 1.5 }}>
        {items.length === 0 ? (
          <EmptyState title="Пусто" description="Первый ответ откроет ветку. Она наследует видимость от корня, случайно на «внутреннюю» переключиться нельзя." />
        ) : (
          <Stack spacing={0}>
            {items.map((m) => (
              <MessageBubble key={m.id} message={m} conversation={conversation} isThread />
            ))}
          </Stack>
        )}
      </Box>
      <Stack sx={{ p: 1.25, borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }} spacing={1}>
        <TextField
          inputRef={inputRef}
          multiline
          minRows={2}
          maxRows={5}
          placeholder="Ответ в обсуждении…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <Stack direction="row" spacing={1}>
          <Chip
            size="small"
            label={root.visibility === 'internal' ? 'Внутренняя ветка' : 'Селлеру видна'}
            sx={{
              bgcolor: root.visibility === 'internal' ? 'warning.main' : 'primary.main',
              color: root.visibility === 'internal' ? 'warning.contrastText' : 'primary.contrastText',
              fontWeight: 700,
            }}
          />
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="contained" endIcon={<SendIcon />} disabled={!text.trim()} onClick={send}>
            Ответить
          </Button>
        </Stack>
      </Stack>
    </Stack>
  )
}
