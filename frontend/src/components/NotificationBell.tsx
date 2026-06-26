import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NotificationsNoneOutlinedIcon from '@mui/icons-material/NotificationsNoneOutlined'
import {
  Badge,
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Menu,
  Typography,
} from '@mui/material'

import type { AuthStoragePortal } from '../api'
import { getStoredToken } from '../api'
import {
  fetchNotifications,
  markNotificationRead,
  resolveNotificationLink,
  type NotificationRow,
} from '../utils/notificationsApi'

type Props = {
  portal: AuthStoragePortal
  notificationsPath: string
}

export function NotificationBell({ portal, notificationsPath }: Props) {
  const navigate = useNavigate()
  const token = getStoredToken(portal)
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)
  const [items, setItems] = useState<NotificationRow[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)

  const uiPortal = portal === 'seller' ? 'seller' : 'ff'

  const refresh = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const data = await fetchNotifications(token, { limit: 8 })
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
    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, 60_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const open = Boolean(anchorEl)

  const handleOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
    void refresh()
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleItemClick = async (row: NotificationRow) => {
    if (!token) return
    handleClose()
    try {
      if (!row.read_at) {
        await markNotificationRead(token, row.id)
        setUnreadCount((c) => Math.max(0, c - 1))
      }
    } catch {
      /* keep navigation even if mark-read fails */
    }
    const target = resolveNotificationLink(row.link, uiPortal)
    if (target) {
      navigate(target)
    }
  }

  if (!token) return null

  return (
    <>
      <IconButton
        color="inherit"
        aria-label="Уведомления"
        data-testid="notifications-bell"
        onClick={handleOpen}
      >
        <Badge
          badgeContent={unreadCount}
          color="error"
          max={99}
          invisible={unreadCount === 0}
          data-testid="notifications-badge"
        >
          <NotificationsNoneOutlinedIcon />
        </Badge>
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 360, maxWidth: '95vw' } } }}
        data-testid="notifications-menu"
      >
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle2">Уведомления</Typography>
        </Box>
        <Divider />
        {loading && items.length === 0 ? (
          <Box sx={{ px: 2, py: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Загрузка…
            </Typography>
          </Box>
        ) : null}
        {!loading && items.length === 0 ? (
          <Box sx={{ px: 2, py: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Нет уведомлений
            </Typography>
          </Box>
        ) : (
          <List dense disablePadding>
            {items.map((row) => (
              <ListItemButton
                key={row.id}
                onClick={() => void handleItemClick(row)}
                data-testid={`notification-item-${row.id}`}
                sx={{
                  bgcolor: row.read_at ? undefined : 'action.hover',
                }}
              >
                <ListItemText
                  primary={row.title}
                  secondary={row.body}
                  sx={{
                    '& .MuiListItemText-primary': {
                      fontWeight: row.read_at ? 400 : 600,
                      fontSize: 14,
                    },
                    '& .MuiListItemText-secondary': {
                      fontSize: 12,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    },
                  }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
        <Divider />
        <Box sx={{ p: 1, display: 'flex', justifyContent: 'center' }}>
          <Button
            size="small"
            data-testid="notifications-show-all"
            onClick={() => {
              handleClose()
              navigate(notificationsPath)
            }}
          >
            Показать все
          </Button>
        </Box>
      </Menu>
    </>
  )
}
