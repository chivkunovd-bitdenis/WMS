import { Box, Chip, IconButton, Stack, Toolbar, Tooltip, Typography, Badge } from '@mui/material'
import { Row } from '../common/Row'
import SearchIcon from '@mui/icons-material/SearchOutlined'
import NotificationsIcon from '@mui/icons-material/NotificationsOutlined'
import TuneIcon from '@mui/icons-material/TuneOutlined'
import InboxIcon from '@mui/icons-material/InboxOutlined'
import BuildIcon from '@mui/icons-material/HandymanOutlined'
import { useStore } from '../state/store'
import { readableRole } from '../state/selectors'
import { PersonaAvatar } from '../common/PersonaAvatar'

export function TopBar() {
  const { ui, currentActor, data, dispatch, navigate } = useStore()

  const unreadNotifs = data.notifications.filter((n) => !n.read).length
  const portal = currentActor.role === 'seller' ? 'seller' : 'ff'

  return (
    <Box
      sx={(t) => ({
        bgcolor: 'background.paper',
        borderBottom: '1px solid',
        borderColor: 'divider',
        zIndex: t.zIndex.appBar,
      })}
      data-testid="chat-topbar"
    >
      <Toolbar sx={{ gap: 2, minHeight: 60, px: { xs: 2, md: 3 } }}>
        <Row align="center" spacing={1.5} sx={{ minWidth: 0, flex: 1 }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: 2.5,
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              display: 'grid',
              placeItems: 'center',
              fontWeight: 900,
              fontSize: 15,
              letterSpacing: '0.02em',
            }}
          >
            КВ
          </Box>
          <Stack sx={{ minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ lineHeight: 1.1, fontWeight: 800 }} noWrap>
              Короб ВМС · Чат
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }} noWrap>
              Портал {portal === 'seller' ? 'селлера' : 'фулфилмента'} · демонстрационный макет WMS-399
            </Typography>
          </Stack>
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label="Локальный демо"
            sx={{ ml: 1, fontWeight: 700, borderStyle: 'dashed' }}
          />
        </Row>
        <Row align="center" spacing={0.5}>
          <Tooltip title="Инбокс">
            <IconButton onClick={() => navigate('#/inbox')} aria-label="Инбокс">
              <InboxIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Поиск по каналам">
            <IconButton onClick={() => navigate('#/search')} aria-label="Поиск">
              <SearchIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Уведомления">
            <IconButton onClick={() => navigate('#/notifications')} aria-label="Уведомления">
              <Badge color="error" badgeContent={unreadNotifs} max={20} overlap="circular">
                <NotificationsIcon />
              </Badge>
            </IconButton>
          </Tooltip>
          <Tooltip title="Настройки уведомлений">
            <IconButton onClick={() => navigate('#/prefs')} aria-label="Настройки">
              <TuneIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Демо-состояния: сменить роль, ширину экрана и включить принудительные сбои">
            <IconButton
              onClick={() => dispatch({ type: 'toggle_demo_menu', open: !ui.showDemoMenu })}
              aria-label="Демо-состояния"
              color={ui.showDemoMenu ? 'primary' : 'default'}
            >
              <BuildIcon />
            </IconButton>
          </Tooltip>
          <Box sx={{ pl: 1, ml: 1, borderLeft: '1px solid', borderColor: 'divider' }}>
            <Row align="center" spacing={1}>
              <PersonaAvatar actor={currentActor} size={34} />
              <Stack sx={{ display: { xs: 'none', md: 'flex' } }}>
                <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
                  {currentActor.name}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {readableRole(currentActor.role)}
                  {currentActor.title ? ` · ${currentActor.title}` : ''}
                </Typography>
              </Stack>
            </Row>
          </Box>
        </Row>
      </Toolbar>
    </Box>
  )
}
