import { NavLink, Outlet } from 'react-router-dom'
import { Screen } from '../AppV2Screens'

export function SellerRequestsScreen() {
  return (
    <Screen title="Заявки" subtitle="Поставки, отгрузки и акты корректировки">
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <NavLink to="/requests/inbound" className="ui-badge" data-testid="seller-tab-inbound">
          Поставки
        </NavLink>
        <NavLink to="/requests/outbound" className="ui-badge" data-testid="seller-tab-outbound">
          Отгрузки
        </NavLink>
        <NavLink
          to="/requests/corrections"
          className="ui-badge"
          data-testid="seller-tab-corrections"
        >
          Акты корректировки
        </NavLink>
      </div>

      <Outlet />
    </Screen>
  )
}

