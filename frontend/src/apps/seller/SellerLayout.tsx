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

type Props = {
  children: ReactNode
  onLogout: () => void
  title?: string
  userLabel?: string
  userRoleLabel?: string
}

export function SellerLayout({
  children,
  onLogout,
  title = 'WMS',
  userLabel,
  userRoleLabel,
}: Props) {
  const drawerWidth = 240
  const base = ''
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
                <span>{userLabel}</span>
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
            <ListItemButton component={NavLink} to={`${base}/documents`} data-testid="nav-seller-documents">
              <ListItemText primary="Документы" />
            </ListItemButton>
            <ListItemButton component={NavLink} to={`${base}/products`} data-testid="nav-seller-products">
              <ListItemText primary="Товары" />
            </ListItemButton>
            <ListItemButton component={NavLink} to={`${base}/settings`} data-testid="nav-seller-settings">
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

