import { Fragment, useMemo } from 'react'
import { Box, Chip, Divider, Stack, Typography } from '@mui/material'
import type { Conversation, Message } from '../types'
import { useStore } from '../state/store'
import { MessageBubble } from './MessageBubble'
import { visibleMessagesForActor } from '../state/selectors'
import { EmptyState } from '../common/EmptyState'
import { fmtDayLabel } from '../utils/format'

export function MessageList({ conversation, orderedIds }: { conversation: Conversation; orderedIds: string[] }) {
  const { data, currentActor, ui } = useStore()

  const messages = useMemo(() => {
    const out: Message[] = []
    for (const id of orderedIds) {
      const m = data.messages.get(id)
      if (!m) continue
      out.push(m)
    }
    return visibleMessagesForActor(out, currentActor).filter((m) => !m.threadRootId)
  }, [orderedIds, data.messages, currentActor])

  if (messages.length === 0) {
    return (
      <EmptyState
        title="Пока пусто"
        description="Первое сообщение начнёт этот канал. Селлеру придёт уведомление, а канал появится у него в инбоксе."
      />
    )
  }

  const items: React.ReactNode[] = []
  let lastDay = ''
  let placedUnread = false

  for (const m of messages) {
    const day = fmtDayLabel(m.createdAt)
    if (day !== lastDay) {
      items.push(
        <Divider key={`day-${m.id}`} sx={{ my: 2 }}>
          <Chip label={day} size="small" sx={{ fontWeight: 700, bgcolor: 'background.paper' }} />
        </Divider>,
      )
      lastDay = day
    }
    if (!placedUnread && conversation.unreadIds.includes(m.id) && currentActor.role !== 'seller') {
      items.push(
        <Box key={`unread-${m.id}`} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, my: 1.5 }}>
          <Divider sx={{ flex: 1, borderColor: 'primary.main' }} />
          <Typography variant="caption" sx={{ fontWeight: 700, color: 'primary.main', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Новые сообщения
          </Typography>
          <Divider sx={{ flex: 1, borderColor: 'primary.main' }} />
        </Box>,
      )
      placedUnread = true
    }

    items.push(
      <Fragment key={m.id}>
        <MessageBubble message={m} conversation={conversation} isFlash={ui.flashMessageId === m.id} />
      </Fragment>,
    )
  }

  return <Stack spacing={0.25}>{items}</Stack>
}
