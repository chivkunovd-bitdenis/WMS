import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AppBar,
  Box,
  Button as MuiButton,
  CssBaseline,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'

import { WmsBrandMark } from '../components/WmsBrandMark'
import { NotificationBell } from '../components/NotificationBell'
import type { FfPermissions } from '../utils/ffPermissions'
import { canAccessFfBlock, isFulfillmentAdminRole } from '../utils/ffPermissions'

type Props = {
  children: ReactNode
  onLogout: () => void
  title?: string
  subtitle?: string
  userLabel?: string
  userRoleLabel?: string
  portal: 'seller' | 'ff'
  meRole?: string
  ffPermissions?: FfPermissions | null
  addressStorageEnabled?: boolean
}

export function AuthedAppLayout({
  children,
  onLogout,
  userLabel,
  userRoleLabel,
  portal,
  meRole = '',
  ffPermissions = null,
  addressStorageEnabled = true,
}: Props) {
  const base = portal === 'seller' ? '/app/seller' : '/app/ff'
  if (portal === 'seller') {
    const drawerWidth = 240
    return (
      <Box sx={{ display: 'flex', minHeight: '100vh' }} data-testid="app-frame">
        <CssBaseline />
        <AppBar
          position="fixed"
          color="inherit"
          elevation={0}
          sx={{
            zIndex: (t) => t.zIndex.drawer + 1,
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
          data-testid="app-topbar"
        >
          <Toolbar sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
              <WmsBrandMark size={44} portal="seller" />
              <Typography variant="h5" noWrap sx={{ fontWeight: 900, letterSpacing: 0 }}>
                Короб ВМС
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {userLabel ? (
                <Box data-testid="topbar-user" sx={{ color: 'text.secondary', fontSize: 14 }}>
                  <span data-testid="user-email">{userLabel}</span>
                  {userRoleLabel ? <span> · {userRoleLabel}</span> : null}
                </Box>
              ) : null}
              <NotificationBell portal="seller" notificationsPath={`${base}/notifications`} />
              <MuiButton
                type="button"
                variant="outlined"
                size="small"
                data-testid="logout"
                onClick={onLogout}
              >
                Выйти
              </MuiButton>
            </Box>
          </Toolbar>
        </AppBar>

        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: {
              width: drawerWidth,
              boxSizing: 'border-box',
              borderRight: '1px solid',
              borderColor: 'divider',
              backgroundImage: 'none',
            },
          }}
          data-testid="app-sidebar"
        >
          <Toolbar />
          <Box sx={{ p: 1 }}>
            <List dense aria-label="Разделы">
              <ListItemButton
                component={NavLink}
                to={`${base}/documents`}
                data-testid="nav-seller-documents"
              >
                <ListItemText primary="Документы" />
              </ListItemButton>
              <ListItemButton
                component={NavLink}
                to={`${base}/products`}
                data-testid="nav-seller-products"
              >
                <ListItemText primary="Товары" />
              </ListItemButton>
              <ListItemButton
                component={NavLink}
                to={`${base}/settings`}
                data-testid="nav-seller-settings"
              >
                <ListItemText primary="Настройки" />
              </ListItemButton>
            </List>
          </Box>
        </Drawer>

        <Box component="main" sx={{ flexGrow: 1, p: 3 }} data-testid="app-content">
          <Toolbar />
          {children}
        </Box>
      </Box>
    )
  }
  const ffDrawerWidth = 260
  const isAdmin = isFulfillmentAdminRole(meRole)
  const can = (block: keyof FfPermissions) => canAccessFfBlock(meRole, ffPermissions, block)
  const canMpShipments = isAdmin || can('mp_shipments')
  const canPackaging = isAdmin || can('packaging')
  const canCatalogCells = isAdmin || can('cells') || can('inventory')
  const canStorage = isAdmin || can('inventory')
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }} data-testid="app-frame">
      <CssBaseline />
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
        data-testid="app-topbar"
      >
        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
            <WmsBrandMark size={48} />
            <Typography variant="h5" noWrap sx={{ fontWeight: 900, letterSpacing: 0 }}>
              Короб ВМС
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {userLabel ? (
              <Box data-testid="topbar-user" sx={{ color: 'text.secondary', fontSize: 14 }}>
                <span data-testid="user-email">{userLabel}</span>
                {userRoleLabel ? <span> · {userRoleLabel}</span> : null}
              </Box>
            ) : null}
            <NotificationBell portal="fulfillment" notificationsPath={`${base}/notifications`} />
            <MuiButton
              type="button"
              variant="outlined"
              size="small"
              data-testid="logout"
              onClick={onLogout}
            >
              Выйти
            </MuiButton>
          </Box>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: ffDrawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: {
            width: ffDrawerWidth,
            boxSizing: 'border-box',
            borderRight: '1px solid',
            borderColor: 'divider',
            backgroundImage: 'none',
          },
        }}
        data-testid="app-sidebar"
      >
        <Toolbar />
        <Box sx={{ p: 1, display: 'flex', flexDirection: 'column', height: 'calc(100% - 64px)' }}>
          <List dense aria-label="Разделы ФФ">
            {can('reception') ? (
              <>
                <ListItemButton component={NavLink} to={`${base}/reception`} data-testid="nav-ff-reception" data-task-id="NAV-01">
                  <ListItemText primary="Приёмка на FF" />
                </ListItemButton>
                <ListItemButton component={NavLink} to={`${base}/sorting`} data-testid="nav-ff-sorting" data-task-id="NAV-01">
                  <ListItemText primary="Сортировка" />
                </ListItemButton>
              </>
            ) : null}
            {canPackaging ? (
              <ListItemButton component={NavLink} to={`${base}/fbs`} data-testid="nav-ff-fbs" data-task-id="NAV-01">
                <ListItemText primary="FBS" />
              </ListItemButton>
            ) : null}
            {canMpShipments ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/mp-shipments`}
                data-testid="nav-ff-mp-shipments"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Отгрузки" />
              </ListItemButton>
            ) : null}
            {canCatalogCells && (addressStorageEnabled || !isAdmin) ? (
              <ListItemButton component={NavLink} to={addressStorageEnabled ? '/app/catalog' : `${base}/products`} data-testid="nav-catalog" data-task-id="NAV-01">
                <ListItemText primary={addressStorageEnabled ? (isAdmin ? 'Ячейки' : 'Каталог и ячейки') : 'Каталог'} />
              </ListItemButton>
            ) : null}
            {isAdmin || can('inventory') ? (
              <ListItemButton component={NavLink} to={`${base}/reports`} data-testid="nav-ff-reports" data-task-id="NAV-01">
                <ListItemText primary="Отчёты" />
              </ListItemButton>
            ) : null}
            {canStorage ? (
              <ListItemButton component={NavLink} to={`${base}/inventory`} data-testid="nav-ff-storage" data-task-id="NAV-01">
                <ListItemText primary="Хранение" />
              </ListItemButton>
            ) : null}
            {/* Новые экраны. Без ссылок сюда до них нельзя было добраться иначе
                как набрав адрес руками — то есть для оператора их не было. */}
            {canCatalogCells && addressStorageEnabled ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/warehouse-map`}
                data-testid="nav-ff-warehouse-map"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Карта склада" />
              </ListItemButton>
            ) : null}
            {canCatalogCells && addressStorageEnabled ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/sorting-objects`}
                data-testid="nav-ff-sorting-objects"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Раскладка" />
              </ListItemButton>
            ) : null}
            {canStorage ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/stocktaking`}
                data-testid="nav-ff-stocktaking"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Инвентаризация" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/fbs-stock`}
                data-testid="nav-ff-fbs-stock"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Остатки FBS" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/sellers`} data-testid="nav-sellers" data-task-id="NAV-01">
                <ListItemText primary="Селлеры" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/products`} data-testid="nav-ff-products" data-task-id="NAV-01">
                <ListItemText primary="Каталог" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/billing`} data-testid="nav-ff-billing" data-task-id="NAV-01">
                <ListItemText primary="Расчёты" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/honest-sign`}
                data-testid="nav-ff-honest-sign"
                data-task-id="NAV-01"
              >
                <ListItemText primary="Честный знак" />
              </ListItemButton>
            ) : null}
          </List>
          {/* NAV-01: календарь, настройки и упаковка прижаты к низу, но список выше остаётся плотным */}
          <List dense aria-label="Разделы ФФ, нижние" sx={{ mt: 'auto' }}>
            <ListItemButton
              component={NavLink}
              to={`${base}/dashboard`}
              data-testid="nav-dashboard"
              data-task-id="NAV-01"
            >
              <ListItemText primary="Календарь отгрузок" />
            </ListItemButton>
            {can('settings') || isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/settings`} data-testid="nav-ff-settings" data-task-id="NAV-01">
                <ListItemText primary="Настройки" />
              </ListItemButton>
            ) : null}
            {canPackaging ? (
              <ListItemButton component={NavLink} to={`${base}/packaging`} data-testid="nav-ff-packaging" data-task-id="NAV-01">
                <ListItemText primary="Упаковка" />
              </ListItemButton>
            ) : null}
          </List>
        </Box>
      </Drawer>

      <Box
        component="main"
        sx={(theme) => ({
          flexGrow: 1,
          p: 3,
          background: `linear-gradient(165deg, ${alpha(theme.palette.primary.main, 0.07)} 0%, ${theme.palette.background.default} 32%, ${theme.palette.background.default} 100%)`,
        })}
        data-testid="app-content"
      >
        <Toolbar />
        {children}
      </Box>
    </Box>
  )
}
