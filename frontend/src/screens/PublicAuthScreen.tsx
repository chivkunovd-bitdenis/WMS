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
import { WmsBrandMark } from '../components/WmsBrandMark'
import type { AuthPortal } from '../hooks/useAuth'
import { sellerPortalUrl } from '../utils/portalUrls'

type Props = {
  variant: AuthPortal
  error: string | null
  notice: string | null
  authBusy: boolean
  onLogin: (e: React.FormEvent<HTMLFormElement>) => void
  onSetPasswordByLink: (e: React.FormEvent<HTMLFormElement>, linkToken: string) => void
  onRequestPasswordReset: (e: React.FormEvent<HTMLFormElement>) => void
  clearNotice: () => void
}

type AuthMode = 'login' | 'forgot'

const fieldStackSx = { display: 'flex', flexDirection: 'column', gap: 2 } as const

/** Токен из ссылки в письме: /set-password?token=… (и /seller/set-password). */
function readLinkToken(): string | null {
  if (typeof window === 'undefined') {
    return null
  }
  if (!window.location.pathname.endsWith('/set-password')) {
    return null
  }
  const token = new URLSearchParams(window.location.search).get('token')
  return token && token.trim() ? token : null
}

export function PublicAuthScreen({
  variant,
  error,
  notice,
  authBusy,
  onLogin,
  onSetPasswordByLink,
  onRequestPasswordReset,
  clearNotice,
}: Props) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [linkToken] = useState<string | null>(() => readLinkToken())
  const isFf = variant === 'fulfillment'
  const portal = isFf ? 'fulfillment' : 'seller'
  const heading = isFf ? 'Короб ВМС' : 'WMS · Портал селлера'

  const header = (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <WmsBrandMark size={48} portal={portal} />
        <Typography
          variant="h5"
          component="h1"
          sx={{ fontWeight: 900, letterSpacing: 0 }}
        >
          {heading}
        </Typography>
      </Box>
      {error ? (
        <Alert severity="error" data-testid="auth-error">
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert severity="success" data-testid="auth-notice">
          {notice}
        </Alert>
      ) : null}
    </>
  )

  const shell = (children: React.ReactNode) => (
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
          {header}
          {children}
        </Box>
      </Container>
    </Box>
  )

  // Человек пришёл по ссылке из письма — приглашение или восстановление.
  if (linkToken) {
    return shell(
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Задайте пароль
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Вы перешли по ссылке из письма. Придумайте пароль — дальше вход по
          email и паролю.
        </Typography>
        <form
          data-testid="set-password-form"
          noValidate
          onSubmit={(e) => onSetPasswordByLink(e, linkToken)}
        >
          <Box sx={fieldStackSx}>
            <TextField
              name="new_password"
              type="password"
              label="Новый пароль"
              required
              fullWidth
              autoComplete="new-password"
              helperText="Минимум 8 символов."
              slotProps={{ htmlInput: { minLength: 8 } }}
            />
            <TextField
              name="new_password_confirm"
              type="password"
              label="Повтор пароля"
              required
              fullWidth
              autoComplete="new-password"
              slotProps={{ htmlInput: { minLength: 8 } }}
            />
            <Button
              type="submit"
              variant="contained"
              color="primary"
              disabled={authBusy}
              fullWidth
              size="large"
              data-testid="set-password-submit"
            >
              {authBusy ? 'Сохранение…' : 'Сохранить и войти'}
            </Button>
          </Box>
        </form>
      </Paper>,
    )
  }

  if (mode === 'forgot') {
    return shell(
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Восстановление пароля
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Укажите почту, на которую заведён кабинет. Пришлём ссылку для нового
          пароля.
        </Typography>
        <form
          data-testid="forgot-password-form"
          noValidate
          onSubmit={onRequestPasswordReset}
        >
          <Box sx={fieldStackSx}>
            <TextField
              name="reset_email"
              type="email"
              label="Email"
              required
              fullWidth
              autoComplete="email"
            />
            <Button
              type="submit"
              variant="contained"
              color="primary"
              disabled={authBusy}
              fullWidth
              size="large"
              data-testid="forgot-password-submit"
            >
              {authBusy ? 'Отправка…' : 'Прислать ссылку'}
            </Button>
            <Button
              type="button"
              variant="text"
              onClick={() => {
                clearNotice()
                setMode('login')
              }}
              fullWidth
            >
              Назад ко входу
            </Button>
          </Box>
        </form>
      </Paper>,
    )
  }

  return shell(
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
                ? 'Только сотрудники фулфилмента. Селлеры входят на /seller/ (кнопка ниже).'
                : 'Первый вход — по ссылке из письма-приглашения.'
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
      <Button
        type="button"
        variant="text"
        color="primary"
        data-testid="go-to-forgot-password"
        onClick={() => {
          clearNotice()
          setMode('forgot')
        }}
        sx={{ mt: 1.5 }}
        fullWidth
      >
        Забыли пароль?
      </Button>
      {isFf ? (
        <Button
          type="button"
          variant="text"
          color="primary"
          data-testid="go-to-seller-portal"
          href={sellerPortalUrl()}
          component="a"
          sx={{ mt: 1.5 }}
          fullWidth
        >
          Вход для селлера (портал /seller/)
        </Button>
      ) : null}
    </Paper>,
  )
}
