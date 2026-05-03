import { Card } from '../../ui/Card'

export function CorrectionActsPlaceholderScreen() {
  return (
    <Card className="card" data-testid="seller-corrections-placeholder">
      <h3 style={{ margin: 0, fontSize: 16 }}>Акты корректировки</h3>
      <p className="subtle">
        Здесь будут акты корректировки с подтверждением второй стороной. На этом этапе делаем только
        каркас портала и навигацию.
      </p>
    </Card>
  )
}

