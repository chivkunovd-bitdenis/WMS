import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AppBar,
  Box,
  Button as MuiButton,
  CssBaseline,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'

import { WmsBrandMark } from '../../components/WmsBrandMark'
import { NotificationBell } from '../../components/NotificationBell'
import { SellerShopSidebar, type SellerShopRow } from '../../components/SellerShopSidebar'
import { emptySellerPermissions, type SellerPermissions } from '../../utils/sellerPermissions'

type Props = {
  children: ReactNode
  onLogout: () => void
  title?: string
  userLabel?: string
  userJobTitle?: string | null
  userRoleLabel?: string
  canManageSellerShops?: boolean
  homeSellerId?: string | null
  activeSellerId?: string | null
  delegatableShops?: SellerShopRow[]
  switchableShops?: SellerShopRow[]
  shopsBusy?: boolean
  permissions?: SellerPermissions
  navigationBasePath?: string
  onToggleShop?: (sellerId: string, enabled: boolean) => void
  onSwitchShop?: (sellerId: string | null) => void
}

export function SellerLayout({
  children,
  onLogout,
  title = 'Портал селлера',
  userLabel,
  userJobTitle,
  userRoleLabel,
  canManageSellerShops = false,
  homeSellerId = null,
  activeSellerId = null,
  delegatableShops = [],
  switchableShops = [],
  shopsBusy = false,
  permissions = emptySellerPermissions(),
  navigationBasePath = '',
  onToggleShop,
  onSwitchShop,
}: Props) {
  const drawerWidth = 240
  const theme = useTheme()
  const desktop = useMediaQuery(theme.breakpoints.up('md'))
  const [menuOpen, setMenuOpen] = useState(false)
  const base = navigationBasePath
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
        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between', gap: { xs: 0.5, md: 2 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, md: 1.5 }, minWidth: 0 }}>
            {!desktop ? <IconButton aria-label="Открыть меню" onClick={() => setMenuOpen(true)} edge="start"><MenuIcon /></IconButton> : null}
            <WmsBrandMark size={desktop ? 44 : 32} portal="seller" />
            <Typography variant="h5" noWrap sx={{ fontWeight: 900, letterSpacing: 0, fontSize: { xs: 18, md: 28 } }}>
              Короб ВМС
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              noWrap
              sx={{ fontWeight: 700, display: { xs: 'none', md: 'block' } }}
            >
              {title}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, md: 2 }, flexShrink: 0 }}>
            {userLabel ? (
              <Box data-testid="topbar-user" sx={{ color: 'text.secondary', fontSize: 14, display: { xs: 'none', md: 'block' } }}>
                <span>{userLabel}</span>
                {userJobTitle ? <span> · {userJobTitle}</span> : null}
                {userRoleLabel ? <span> · {userRoleLabel}</span> : null}
              </Box>
            ) : null}
            <MuiButton component={NavLink} to={`${base}/chat`}>Чат</MuiButton>
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
        variant={desktop ? 'permanent' : 'temporary'}
        open={desktop || menuOpen}
        onClose={() => setMenuOpen(false)}
        sx={{
          width: desktop ? drawerWidth : 0,
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
          <List dense aria-label="Разделы" onClick={() => setMenuOpen(false)}>
            {permissions.documents ? (
              <ListItemButton component={NavLink} to={`${base}/documents`} data-testid="nav-seller-documents">
                <ListItemText primary="Документы" />
              </ListItemButton>
            ) : null}
            {permissions.products ? (
              <ListItemButton component={NavLink} to={`${base}/products`} data-testid="nav-seller-products">
                <ListItemText primary="Товары" />
              </ListItemButton>
            ) : null}
            {permissions.products ? (
              <ListItemButton component={NavLink} to={`${base}/reports`} data-testid="nav-seller-reports">
                <ListItemText primary="Отчёты" />
              </ListItemButton>
            ) : null}
            {permissions.honest_sign ? (
              <ListItemButton component={NavLink} to={`${base}/honest-sign`} data-testid="nav-seller-honest-sign">
                <ListItemText primary="Честный знак" />
              </ListItemButton>
            ) : null}
            {permissions.settings || permissions.staff ? (
              <ListItemButton component={NavLink} to={`${base}/settings`} data-testid="nav-seller-settings">
                <ListItemText primary="Настройки" />
              </ListItemButton>
            ) : null}
          </List>
          {onToggleShop && onSwitchShop ? (
            <SellerShopSidebar
              canManage={canManageSellerShops}
              homeSellerId={homeSellerId}
              activeSellerId={activeSellerId}
              delegatableShops={delegatableShops}
              switchableShops={switchableShops}
              busy={shopsBusy}
              onToggleShop={onToggleShop}
              onSwitchShop={onSwitchShop}
            />
          ) : null}
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 3 } }} data-testid="app-content">
        <Toolbar />
        {children}
      </Box>
    </Box>
  )
}
