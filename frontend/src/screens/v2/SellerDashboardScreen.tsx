import { Screen } from '../AppV2Screens'
import { StatCard } from '../../components/StatCard'
import { PlaceholderCard } from '../AppV2Screens'

type Props = {
  inboundCount: number
  outboundCount: number
  productsCount: number
  correctionActsCount?: number
  sellerName?: string | null
}

export function SellerDashboardScreen({
  inboundCount,
  outboundCount,
  productsCount,
  correctionActsCount = 0,
  sellerName,
}: Props) {
  return (
    <Screen
      title="Портал селлера"
      subtitle="Заявки, товары, остатки и согласования"
    >
      <div className="kpi-grid" data-testid="kpi-grid">
        <StatCard
          label="Заявки на поставку"
          value={inboundCount}
          hint="Мои поставки"
          tone="accent"
          data-testid="kpi-inbound"
        />
        <StatCard
          label="Заявки на отгрузку"
          value={outboundCount}
          hint="Мои отгрузки"
          data-testid="kpi-outbound"
        />
        <StatCard
          label="Товары"
          value={productsCount}
          hint="Мои товары"
          data-testid="kpi-products"
        />
        <StatCard
          label="Акты корректировки"
          value={correctionActsCount}
          hint="Требуют согласования"
          data-testid="kpi-corrections"
        />
      </div>

      <div className="screen-grid">
        <div className="stack">
          <PlaceholderCard
            title="Мой контекст"
            hint={sellerName ? `Селлер: ${sellerName}` : 'Селлер'}
          />
        </div>
        <div className="stack">
          <PlaceholderCard
            title="Быстрые действия"
            hint="Перейди в «Заявки», чтобы создать поставку или отгрузку."
          />
        </div>
      </div>
    </Screen>
  )
}

