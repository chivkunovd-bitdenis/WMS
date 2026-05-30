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
}

export function AuthedAppLayout({
  children,
  onLogout,
  title = 'WMS',
  subtitle,
  userLabel,
  userRoleLabel,
  portal,
  meRole = '',
  ffPermissions = null,
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 0 }}>
              <Typography variant="h6" noWrap>
                {title}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {userLabel ? (
                <Box data-testid="topbar-user" sx={{ color: 'text.secondary', fontSize: 14 }}>
                  <span data-testid="user-email">{userLabel}</span>
                  {userRoleLabel ? <span> · {userRoleLabel}</span> : null}
                </Box>
              ) : null}
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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 0 }}>
            <Typography variant="h6" noWrap>
              {title}
            </Typography>
            {subtitle ? (
              <Typography variant="body2" color="text.secondary" noWrap>
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {userLabel ? (
              <Box data-testid="topbar-user" sx={{ color: 'text.secondary', fontSize: 14 }}>
                <span data-testid="user-email">{userLabel}</span>
                {userRoleLabel ? <span> · {userRoleLabel}</span> : null}
              </Box>
            ) : null}
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
        <Box sx={{ p: 1 }}>
          <List dense aria-label="Разделы ФФ">
            <ListItemButton component={NavLink} to={`${base}/dashboard`} data-testid="nav-dashboard">
              <ListItemText primary="Дашборд" />
            </ListItemButton>
            {can('mp_shipments') ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/mp-shipments`}
                data-testid="nav-ff-mp-shipments"
              >
                <ListItemText primary="Отгрузки на МП" />
              </ListItemButton>
            ) : null}
            {can('reception') ? (
              <>
                <ListItemButton component={NavLink} to={`${base}/reception`} data-testid="nav-ff-reception">
                  <ListItemText primary="Приёмка" />
                </ListItemButton>
                <ListItemButton component={NavLink} to={`${base}/sorting`} data-testid="nav-ff-sorting">
                  <ListItemText primary="Сортировка" />
                </ListItemButton>
                <ListItemButton component={NavLink} to={`${base}/packaging`} data-testid="nav-ff-packaging">
                  <ListItemText primary="Упаковка" />
                </ListItemButton>
              </>
            ) : null}
            {can('cells') ? (
              <ListItemButton component={NavLink} to="/app/catalog" data-testid="nav-catalog">
                <ListItemText primary="Каталог" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/sellers`} data-testid="nav-sellers">
                <ListItemText primary="Селлеры" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/products`} data-testid="nav-ff-products">
                <ListItemText primary="Товары" />
              </ListItemButton>
            ) : null}
            {can('inventory') ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/inventory`}
                data-testid="nav-ff-inventory"
              >
                <ListItemText primary="Инвентаризация" />
              </ListItemButton>
            ) : null}
            {isAdmin ? (
              <ListItemButton
                component={NavLink}
                to={`${base}/honest-sign`}
                data-testid="nav-ff-honest-sign"
              >
                <ListItemText primary="Честный знак" />
              </ListItemButton>
            ) : null}
            {can('settings') || isAdmin ? (
              <ListItemButton component={NavLink} to={`${base}/settings`} data-testid="nav-ff-settings">
                <ListItemText primary="Настройки" />
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

