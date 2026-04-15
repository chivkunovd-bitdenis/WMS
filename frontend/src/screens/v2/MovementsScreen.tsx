import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Screen } from '../AppV2Screens'

type GlobalMovementRow = {
  id: string
  sku_code: string
  quantity_delta: number
  movement_type: string
}

type Props = {
  globalMovements: GlobalMovementRow[]
  onRefreshGlobalMovementsClick: () => void
}

export function MovementsScreen({ globalMovements, onRefreshGlobalMovementsClick }: Props) {
  return (
    <Screen title="Журнал движений" subtitle="Последние операции по складу">
      <Card className="card" data-testid="global-movements-section">
        <p className="subtle">
          Последние операции по складу (приёмка, перемещение, отгрузка).
        </p>
        <Button type="button" data-testid="global-movements-refresh" onClick={onRefreshGlobalMovementsClick}>
          Обновить
        </Button>
        <div data-testid="global-movements-list">
          <table className="ui-table" data-testid="global-movements-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Δ</th>
                <th>Тип</th>
              </tr>
            </thead>
            <tbody>
              {globalMovements.map((m) => (
                <tr key={m.id} data-testid="global-movement-row">
                  <td>{m.sku_code}</td>
                  <td>
                    {m.quantity_delta > 0 ? '+' : ''}
                    {m.quantity_delta}
                  </td>
                  <td>{m.movement_type}</td>
                </tr>
              ))}
              {globalMovements.length === 0 ? (
                <tr>
                  <td colSpan={3}>
                    <span className="subtle">Пока пусто.</span>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>
    </Screen>
  )
}

