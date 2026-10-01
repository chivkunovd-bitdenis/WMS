import { useState, type ReactNode } from 'react'
import { Link as RouterLink, NavLink } from 'react-router-dom'
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

import { DeveloperRequests, type DeveloperRequestsProps } from '../../components/developer-requests/DeveloperRequests'
import { WmsBrandMark } from '../../components/WmsBrandMark'
import { NotificationBell } from '../../components/NotificationBell'
import { SellerShopSidebar, type SellerShopRow } from '../../components/SellerShopSidebar'
import { emptySellerPermissions, firstAllowedSellerPath, type SellerPermissions } from '../../utils/sellerPermissions'

export type SellerNavItem = { key: string; label: string; to: string; testId: string }

/**
 * Пункты меню портала селлера в порядке отображения.
 *
 * Вынесено из JSX отдельной функцией, чтобы порядок и видимость по правам
 * проверялись напрямую, без раскрытия постоянного Drawer (он рендерит
 * содержимое только при `desktop`-медиазапросе).
 */
export function visibleSellerNavItems(base: string, permissions: SellerPermissions): SellerNavItem[] {
  const items: SellerNavItem[] = []
  if (permissions.documents) {
    items.push({ key: 'documents', label: 'Документы', to: `${base}/documents`, testId: 'nav-seller-documents' })
    // WMS-616 D1: «FBS» — отдельный read-only раздел селлера, доступен по тому
    // же праву «Документы» (новое право не создаётся). Стоит сразу после
    // «Документов» — заказы FBS селлер видит как собственные документы.
    items.push({ key: 'fbs', label: 'FBS', to: `${base}/fbs`, testId: 'nav-seller-fbs' })
  }
  if (permissions.products) {
    items.push({ key: 'products', label: 'Товары', to: `${base}/products`, testId: 'nav-seller-products' })
    items.push({ key: 'reports', label: 'Отчёты', to: `${base}/reports`, testId: 'nav-seller-reports' })
  }
  // WMS-549 R1: тот же гейт, что и у «Документы» — расчёты показывают стоимость
  // тех же документов, а новое право владелец не просил.
  if (permissions.documents) {
    items.push({ key: 'billing', label: 'Расчёты', to: `${base}/billing`, testId: 'nav-seller-billing' })
  }
  if (permissions.honest_sign) {
    items.push({ key: 'honest_sign', label: 'Честный знак', to: `${base}/honest-sign`, testId: 'nav-seller-honest-sign' })
  }
  if (permissions.settings || permissions.staff) {
    items.push({ key: 'settings', label: 'Настройки', to: `${base}/settings`, testId: 'nav-seller-settings' })
  }
  return items
}

type Props = {
  children: ReactNode
  developerRequests?: DeveloperRequestsProps
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
  developerRequests,
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
            {/* WMS-567: логотип и «Короб ВМС» ведут на стартовую страницу — ту же, что
                корень портала (firstAllowedSellerPath). «Бургер» и подпись в ссылку не входят. */}
            <Box
              component={RouterLink}
              to={`${base}${firstAllowedSellerPath(permissions)}`}
              data-testid="topbar-home-link"
              sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, md: 1.5 }, minWidth: 0, color: 'inherit', textDecoration: 'none' }}
            >
              <WmsBrandMark size={desktop ? 44 : 32} portal="seller" />
              <Typography variant="h5" noWrap sx={{ fontWeight: 900, letterSpacing: 0, fontSize: { xs: 18, md: 28 } }}>
                Короб ВМС
              </Typography>
            </Box>
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
            {visibleSellerNavItems(base, permissions).map((item) => (
              <ListItemButton key={item.key} component={NavLink} to={item.to} data-testid={item.testId}>
                <ListItemText primary={item.label} />
              </ListItemButton>
            ))}
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

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 3 }, pb: developerRequests ? 10 : undefined }} data-testid="app-content">
        <Toolbar />
        {children}
      </Box>
      {developerRequests && <DeveloperRequests {...developerRequests} />}
    </Box>
  )
}
