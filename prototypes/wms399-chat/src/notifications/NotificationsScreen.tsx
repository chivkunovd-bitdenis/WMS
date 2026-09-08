import { useMemo } from 'react'
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import MarkChatReadIcon from '@mui/icons-material/MarkChatReadOutlined'
import MailIcon from '@mui/icons-material/MailOutlineOutlined'
import { useStore } from '../state/store'
import { EmptyState } from '../common/EmptyState'
import { Row } from '../common/Row'
import { PersonaAvatar } from '../common/PersonaAvatar'
import { conversationAccessible, visibleMessagesForActor } from '../state/selectors'
import { fmtRelative } from '../utils/format'
import type { NotificationEntry, NotificationKind } from '../types'

const KIND_LABELS: Record<NotificationKind, string> = {
  mention: 'Упоминание',
  shared_message: 'Новое сообщение',
  followup_assigned: 'Требуется ответ',
  thread_reply: 'Ответ в обсуждении',
  system: 'Системное',
}

const KIND_COLORS: Record<NotificationKind, string> = {
  mention: '#4c1d95',
  shared_message: '#334155',
  followup_assigned: '#c2410c',
  thread_reply: '#0f766e',
  system: '#475569',
}

export function NotificationsScreen() {
  const { data, dispatchData, actions, actorById, currentActor, notificationPrefs } = useStore()

  const visibleForRole = (n: NotificationEntry): boolean => {
    const conv = data.conversations.get(n.conversationId)
    if (!conv) return false
    if (!conversationAccessible(conv, currentActor)) return false
    const msgs = (data.messagesByConversation.get(conv.id) ?? [])
      .map((id) => data.messages.get(id))
      .filter((m): m is NonNullable<typeof m> => Boolean(m))
    const visible = visibleMessagesForActor(msgs, currentActor)
    return visible.some((m) => m.id === n.messageId)
  }

  const notifications = useMemo(() => data.notifications.filter(visibleForRole), [data.notifications, data.conversations, data.messages, data.messagesByConversation, currentActor])

  const unreadCount = notifications.filter((n) => !n.read).length

  const noPush = notificationPrefs.pushPermission !== 'granted' && notificationPrefs.pushEnabled

  return (
    <Stack sx={{ maxWidth: 780, mx: 'auto', gap: 2 }} data-testid="notifications-screen">
      <Row align="center" spacing={1}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" sx={{ fontWeight: 800 }}>
            Уведомления
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Центр событий вашей роли. Демо не отправляет реальные push и email.
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          startIcon={<MarkChatReadIcon />}
          disabled={unreadCount === 0}
          onClick={() => dispatchData({ type: 'notif_read_all' })}
        >
          Отметить всё прочитанным
        </Button>
      </Row>

      {noPush ? (
        <Alert severity="warning">
          Push включён в настройках, но браузер их не разрешил. Мы этого не скрываем — реальные push не пойдут, пока не разрешите в браузере.
        </Alert>
      ) : null}
      {notificationPrefs.digest !== 'off' ? (
        <Alert severity="info" icon={<MailIcon />}>
          Digest включён: сводка по непрочитанному будет уходить {notificationPrefs.digest === 'hourly' ? 'раз в час' : 'раз в день'}. Прототип email не шлёт.
        </Alert>
      ) : null}

      {notifications.length === 0 ? (
        <EmptyState
          title="Ничего нового"
          description="Здесь появляются упоминания, ответы на ваши сообщения и события каналов, где вы участник."
        />
      ) : (
        <Stack spacing={1}>
          {notifications.map((n) => {
            const actor = actorById.get(n.actorId)
            const conv = data.conversations.get(n.conversationId)
            return (
              <Paper
                key={n.id}
                variant="outlined"
                sx={(t) => ({
                  p: 1.5,
                  cursor: 'pointer',
                  transition: 'background 120ms',
                  borderColor: n.read ? 'divider' : t.palette.primary.light,
                  bgcolor: n.read ? 'background.paper' : t.palette.primary.light + '14',
                  '&:hover': { bgcolor: t.palette.action.hover },
                })}
                onClick={() => {
                  if (!n.read) dispatchData({ type: 'notif_read', id: n.id })
                  actions.openConversation(n.conversationId, { flashMessageId: n.messageId })
                }}
              >
                <Row align="flex-start" spacing={1.25}>
                  {actor ? <PersonaAvatar actor={actor} size={40} /> : null}
                  <Stack sx={{ flex: 1, minWidth: 0 }} spacing={0.5}>
                    <Row align="center" spacing={0.75}>
                      <Chip
                        size="small"
                        label={KIND_LABELS[n.kind]}
                        sx={{ bgcolor: KIND_COLORS[n.kind], color: '#fff', fontWeight: 700, height: 20 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        {conv?.title} · {fmtRelative(n.createdAt)}
                      </Typography>
                    </Row>
                    <Typography variant="body2" sx={{ fontWeight: n.read ? 500 : 700 }}>
                      {actor?.name ?? '—'}: {n.preview}
                    </Typography>
                  </Stack>
                  {!n.read ? (
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: 'primary.main', mt: 1 }} />
                  ) : null}
                </Row>
              </Paper>
            )
          })}
        </Stack>
      )}
    </Stack>
  )
}
