import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Container,
  Paper,
  TextField,
  Typography,
} from '@mui/material'
import type { AuthPortal } from '../hooks/useAuth'

type Props = {
  variant: AuthPortal
  error: string | null
  authBusy: boolean
  pendingPasswordSetupEmail: string | null
  onRegister: (e: React.FormEvent<HTMLFormElement>) => void
  onLogin: (e: React.FormEvent<HTMLFormElement>) => void
  onSetInitialPassword: (e: React.FormEvent<HTMLFormElement>) => void
  onCancelPasswordSetup: () => void
}

type AuthMode = 'login' | 'register'

const fieldStackSx = { display: 'flex', flexDirection: 'column', gap: 2 } as const

export function PublicAuthScreen({
  variant,
  error,
  authBusy,
  pendingPasswordSetupEmail,
  onRegister,
  onLogin,
  onSetInitialPassword,
  onCancelPasswordSetup,
}: Props) {
  const [mode, setMode] = useState<AuthMode>('login')
  const isFf = variant === 'fulfillment'

  const title = isFf ? 'Портал фулфилмента' : 'Портал селлера'
  const subtitle = isFf
    ? 'Регистрация организации — для первого администратора. Аккаунты селлеров создаёт админ фулфилмента.'
    : 'Вход для селлера. Регистрация недоступна — доступ выдаёт администратор вашего фулфилмента.'

  if (pendingPasswordSetupEmail) {
    return (
      <Box
        component="main"
        data-testid="app-root"
        sx={{
          minHeight: '100vh',
          bgcolor: 'background.default',
          py: { xs: 3, sm: 5 },
          px: 2,
        }}
      >
        <Container maxWidth="sm">
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="h5" component="h1">
              {title}
            </Typography>
            {error ? (
              <Alert severity="error" data-testid="auth-error">
                {error}
              </Alert>
            ) : null}
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                Установите пароль
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Это первый вход для {pendingPasswordSetupEmail}. Задайте пароль и
                подтверждение — далее вход только по email и паролю.
              </Typography>
              <form
                data-testid="seller-password-setup-form"
                noValidate
                onSubmit={onSetInitialPassword}
              >
                <Box sx={fieldStackSx}>
                  <TextField
                    name="email_display"
                    type="email"
                    label="Email"
                    value={pendingPasswordSetupEmail}
                    fullWidth
                    disabled
                  />
                  <TextField
                    name="new_password"
                    type="password"
                    label="Новый пароль"
                    required
                    fullWidth
                    autoComplete="new-password"
                    helperText="Минимум 8 символов."
                    slotProps={{
                      htmlInput: { minLength: 8 },
                    }}
                  />
                  <TextField
                    name="new_password_confirm"
                    type="password"
                    label="Повтор пароля"
                    required
                    fullWidth
                    autoComplete="new-password"
                    slotProps={{
                      htmlInput: { minLength: 8 },
                    }}
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    color="primary"
                    disabled={authBusy}
                    fullWidth
                    size="large"
                    data-testid="seller-password-setup-submit"
                  >
                    {authBusy ? 'Сохранение…' : 'Сохранить и войти'}
                  </Button>
                  <Button
                    type="button"
                    variant="text"
                    onClick={onCancelPasswordSetup}
                    fullWidth
                  >
                    Назад ко входу
                  </Button>
                </Box>
              </form>
            </Paper>
          </Box>
        </Container>
      </Box>
    )
  }

  return (
    <Box
      component="main"
      data-testid="app-root"
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        py: { xs: 3, sm: 5 },
        px: 2,
      }}
    >
      <Container maxWidth="sm">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="h5" component="h1">
            WMS · {title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {subtitle}
          </Typography>
          {error ? (
            <Alert severity="error" data-testid="auth-error">
              {error}
            </Alert>
          ) : null}

          {mode === 'login' || !isFf ? (
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                Вход
              </Typography>
              <form data-testid="login-form" noValidate onSubmit={onLogin}>
                <Box sx={fieldStackSx}>
                  <TextField
                    name="email"
                    type="email"
                    label="Email"
                    required
                    fullWidth
                    autoComplete="email"
                  />
                  <TextField
                    name="password"
                    type="password"
                    label="Пароль"
                    required={false}
                    fullWidth
                    autoComplete="current-password"
                    helperText={
                      isFf
                        ? 'Сотрудник фулфилмента: введите пароль. Селлер при первом входе на этой странице может оставить поле пустым.'
                        : 'Первый вход: оставьте пароль пустым и нажмите «Войти», затем задайте пароль.'
                    }
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    color="primary"
                    disabled={authBusy}
                    fullWidth
                    size="large"
                  >
                    {authBusy ? 'Вход…' : 'Войти'}
                  </Button>
                </Box>
              </form>
              {isFf ? (
                <Button
                  type="button"
                  variant="text"
                  color="primary"
                  data-testid="go-to-register"
                  onClick={() => setMode('register')}
                  sx={{ mt: 1.5 }}
                  fullWidth
                >
                  Регистрация организации (первый админ)
                </Button>
              ) : null}
            </Paper>
          ) : null}

          {mode === 'register' && isFf ? (
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                Регистрация организации
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Внутренний код организации создаётся автоматически. Дальнейших
                сотрудников добавляет админ в кабинете.
              </Typography>
              <form data-testid="register-form" noValidate onSubmit={onRegister}>
                <Box sx={fieldStackSx}>
                  <TextField
                    name="organization_name"
                    label="Организация"
                    required
                    fullWidth
                    autoComplete="organization"
                  />
                  <TextField
                    name="admin_email"
                    type="email"
                    label="Email администратора"
                    required
                    fullWidth
                    autoComplete="email"
                  />
                  <TextField
                    name="password"
                    type="password"
                    label="Пароль"
                    required
                    fullWidth
                    autoComplete="new-password"
                    helperText="Минимум 8 символов."
                    slotProps={{
                      htmlInput: { minLength: 8 },
                    }}
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    color="primary"
                    disabled={authBusy}
                    fullWidth
                    size="large"
                  >
                    {authBusy ? 'Отправка…' : 'Создать аккаунт'}
                  </Button>
                </Box>
              </form>
              <Button
                type="button"
                variant="text"
                color="primary"
                data-testid="go-to-login"
                onClick={() => setMode('login')}
                sx={{ mt: 1.5 }}
                fullWidth
              >
                Уже есть аккаунт? Войти
              </Button>
            </Paper>
          ) : null}
        </Box>
      </Container>
    </Box>
  )
}
