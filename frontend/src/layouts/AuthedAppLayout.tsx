import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Button } from '../ui/Button'

type Props = {
  children: ReactNode
  onLogout: () => void
  title?: string
  subtitle?: string
  userLabel?: string
  userRoleLabel?: string
}

export function AuthedAppLayout({
  children,
  onLogout,
  title = 'WMS',
  subtitle,
  userLabel,
  userRoleLabel,
}: Props) {
  return (
    <div className="app-frame" data-testid="app-frame">
      <aside className="app-sidebar" aria-label="Навигация" data-testid="app-sidebar">
        <div className="app-brand">
          <div className="app-brand-title">{title}</div>
          {subtitle ? <div className="app-brand-sub">{subtitle}</div> : null}
        </div>
        <nav className="app-navlist" aria-label="Разделы">
          <NavLink to="/app/dashboard" className="app-navitem" data-testid="nav-dashboard">
            Дашборд
          </NavLink>
          <div className="app-navgroup" aria-label="Каталог">
            <div className="app-navgroup-title">Каталог</div>
            <NavLink
              to="/app/catalog"
              end
              className="app-navitem"
              data-testid="nav-catalog"
            >
              Обзор
            </NavLink>
            <NavLink
              to="/app/catalog/products"
              className="app-navitem"
              data-testid="nav-products"
            >
              Товары (SKU)
            </NavLink>
            <NavLink
              to="/app/catalog/warehouses"
              className="app-navitem"
              data-testid="nav-warehouses"
            >
              Склады
            </NavLink>
            <NavLink
              to="/app/catalog/locations"
              className="app-navitem"
              data-testid="nav-locations"
            >
              Ячейки
            </NavLink>
            <NavLink
              to="/app/catalog/sellers"
              className="app-navitem"
              data-testid="nav-sellers"
            >
              Селлеры
            </NavLink>
          </div>
          <div className="app-navgroup" aria-label="Операции">
            <div className="app-navgroup-title">Операции</div>
            <NavLink
              to="/app/ops"
              end
              className="app-navitem"
              data-testid="nav-ops"
            >
              Обзор
            </NavLink>
            <NavLink
              to="/app/ops/inbound"
              className="app-navitem"
              data-testid="nav-inbound"
            >
              Приёмка
            </NavLink>
            <NavLink
              to="/app/ops/outbound"
              className="app-navitem"
              data-testid="nav-outbound"
            >
              Отгрузка
            </NavLink>
            <NavLink
              to="/app/ops/movements"
              className="app-navitem"
              data-testid="nav-movements"
            >
              Движения
            </NavLink>
            <NavLink
              to="/app/ops/transfers"
              className="app-navitem"
              data-testid="nav-transfers"
            >
              Перемещения
            </NavLink>
          </div>
          <div className="app-navgroup" aria-label="Интеграции">
            <div className="app-navgroup-title">Интеграции</div>
            <NavLink to="/app/integrations/wb" className="app-navitem" data-testid="nav-wb">
              Wildberries
            </NavLink>
          </div>
        </nav>
      </aside>

      <div className="app-main">
        <header className="app-topbar" data-testid="app-topbar">
          <div className="app-topbar-left">
            <div className="app-topbar-title">{title}</div>
          </div>
          <div className="app-topbar-right">
            {userLabel ? (
              <div className="topbar-user" data-testid="topbar-user">
                <span>{userLabel}</span>
                {userRoleLabel ? (
                  <span className="topbar-user-role">· {userRoleLabel}</span>
                ) : null}
              </div>
            ) : null}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              data-testid="logout"
              onClick={onLogout}
            >
              Выйти
            </Button>
          </div>
        </header>

        <main className="app-content" data-testid="app-content">
          {children}
        </main>
      </div>
    </div>
  )
}

