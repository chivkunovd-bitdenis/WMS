import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'

type Props = {
  error: string | null
  authBusy: boolean
  onRegister: (e: React.FormEvent<HTMLFormElement>) => void
  onLogin: (e: React.FormEvent<HTMLFormElement>) => void
}

export function PublicAuthScreen({
  error,
  authBusy,
  onRegister,
  onLogin,
}: Props) {
  return (
    <main data-testid="app-root" className="shell">
      <header className="top">
        <h1>WMS</h1>
      </header>
      {error ? (
        <p className="error" data-testid="auth-error">
          {error}
        </p>
      ) : null}
      <div className="grid2">
        <Card className="card">
          <h2>Регистрация фулфилмента</h2>
          <p className="hint">
            Slug — короткое имя на латинице (например <code>acme-ff</code>), без
            пробелов.
          </p>
          <form data-testid="register-form" noValidate onSubmit={onRegister}>
            <label>
              Организация
              <Input name="organization_name" required />
            </label>
            <label>
              Slug (латиница)
              <Input
                name="slug"
                data-testid="register-slug"
                required
                placeholder="acme-ff"
                autoComplete="off"
              />
            </label>
            <label>
              Email админа
              <Input name="admin_email" type="email" required />
            </label>
            <label>
              Пароль
              <Input name="password" type="password" minLength={8} required />
            </label>
            <Button type="submit" disabled={authBusy}>
              {authBusy ? 'Отправка…' : 'Создать аккаунт'}
            </Button>
          </form>
        </Card>
        <Card className="card">
          <h2>Вход</h2>
          <form data-testid="login-form" noValidate onSubmit={onLogin}>
            <label>
              Email
              <Input name="email" type="email" required />
            </label>
            <label>
              Пароль
              <Input name="password" type="password" required />
            </label>
            <Button type="submit" disabled={authBusy}>
              {authBusy ? 'Вход…' : 'Войти'}
            </Button>
          </form>
        </Card>
      </div>
    </main>
  )
}

