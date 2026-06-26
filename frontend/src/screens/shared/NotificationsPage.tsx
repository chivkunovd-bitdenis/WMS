import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Typography,
} from '@mui/material'

import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  resolveNotificationLink,
  type NotificationRow,
} from '../../utils/notificationsApi'

type Props = {
  token: string
  portal: 'seller' | 'ff'
  testId?: string
}

const severityColor = {
  info: 'default',
  warning: 'warning',
  critical: 'error',
} as const

export function NotificationsPage({
  token,
  portal,
  testId = 'notifications-page',
}: Props) {
  const navigate = useNavigate()
  const [items, setItems] = useState<NotificationRow[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchNotifications(token, { limit: 100 })
      setItems(data.items)
      setUnreadCount(data.unread_count)
    } catch {
      setItems([])
      setUnreadCount(0)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const handleOpen = async (row: NotificationRow) => {
    if (!row.read_at) {
      try {
        await markNotificationRead(token, row.id)
        setUnreadCount((c) => Math.max(0, c - 1))
        setItems((prev) =>
          prev.map((x) =>
            x.id === row.id ? { ...x, read_at: new Date().toISOString() } : x,
          ),
        )
      } catch {
        /* navigate anyway */
      }
    }
    const target = resolveNotificationLink(row.link, portal)
    if (target) navigate(target)
  }

  const handleReadAll = async () => {
    setBusy(true)
    try {
      await markAllNotificationsRead(token)
      await load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box data-testid={testId}>
      <Stack direction="row" sx={{ mb: 2, justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5">Уведомления</Typography>
        {unreadCount > 0 ? (
          <Button
            variant="outlined"
            size="small"
            disabled={busy}
            data-testid="notifications-read-all"
            onClick={() => void handleReadAll()}
          >
            Прочитать все ({unreadCount})
          </Button>
        ) : null}
      </Stack>

      {loading ? (
        <Typography color="text.secondary">Загрузка…</Typography>
      ) : items.length === 0 ? (
        <Typography color="text.secondary">Нет уведомлений</Typography>
      ) : (
        <Stack spacing={1}>
          {items.map((row) => (
            <Paper
              key={row.id}
              variant="outlined"
              sx={{
                p: 2,
                cursor: row.link ? 'pointer' : 'default',
                bgcolor: row.read_at ? 'background.paper' : 'action.hover',
              }}
              data-testid={`notification-row-${row.id}`}
              onClick={() => void handleOpen(row)}
            >
              <Stack direction="row" spacing={1} sx={{ mb: 0.5, alignItems: 'center' }}>
                <Typography variant="subtitle2" sx={{ flex: 1 }}>
                  {row.title}
                </Typography>
                <Chip
                  size="small"
                  label={row.severity}
                  color={severityColor[row.severity]}
                  variant="outlined"
                />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {row.body}
              </Typography>
            </Paper>
          ))}
        </Stack>
      )}
    </Box>
  )
}
