import { Button } from '../ui/Button'

type Props = {
  loading: boolean
  onLogout: () => void
}

export function ProfileLoadingScreen({ loading, onLogout }: Props) {
  return (
    <main data-testid="app-root" className="shell">
      <header className="top">
        <h1>WMS</h1>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          data-testid="logout"
          onClick={onLogout}
        >
          Выйти
        </Button>
      </header>
      <p className="hint" data-testid="loading">
        {loading ? 'Загрузка профиля…' : 'Получаем данные аккаунта…'} Если экран
        не меняется, проверьте, что API доступен (прокси Vite / контейнер api в
        docker).
      </p>
    </main>
  )
}

