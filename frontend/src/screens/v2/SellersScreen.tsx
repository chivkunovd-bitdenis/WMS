import { useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  isFulfillmentAdmin: boolean
  sellers: SellerRow[]
  onRefresh: () => void | Promise<void>
}

export function SellersScreen({
  token,
  authHeaders,
  isFulfillmentAdmin,
  sellers,
  onRefresh,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !isFulfillmentAdmin) {
      return
    }
    setError(null)
    setSuccess(null)
    setBusy(true)
    try {
      const fd = new FormData(form)
      const name = String(fd.get('seller_name') ?? '').trim()
      const email = String(fd.get('seller_email') ?? '').trim()
      if (!name) {
        setError('Укажите название селлера.')
        return
      }
      if (!email) {
        setError('Укажите email для входа в кабинет селлера.')
        return
      }

      const sellerRes = await fetch(apiUrl('/sellers'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (!sellerRes.ok) {
        setError(await readApiErrorMessage(sellerRes))
        return
      }
      const seller = (await sellerRes.json()) as { id: string; name: string }

      const accRes = await fetch(apiUrl('/auth/seller-accounts'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ seller_id: seller.id, email }),
      })
      if (!accRes.ok) {
        setError(await readApiErrorMessage(accRes))
        return
      }

      form.reset()
      await onRefresh()
      setSuccess(
        `Селлер «${seller.name}» создан. Передайте селлеру email ${email} и ссылку на портал селлера. ` +
          'Первый вход: оставить пароль пустым — система попросит задать новый пароль.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить селлера.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box data-testid="sellers-screen">
      <Typography variant="h5" gutterBottom>
        Селлеры
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Клиенты фулфилмента. Одна форма: запись селлера и учётная запись для входа (email). Пароль
        селлер задаёт при первом входе.
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="sellers-error">
          {error}
        </Alert>
      ) : null}
      {success ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-create-success">
          {success}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <TableContainer
          component={Paper}
          variant="outlined"
          sx={{ flex: 1, width: '100%' }}
          data-testid="sellers-panel"
        >
          <Table size="small" data-testid="sellers-table">
            <TableHead>
              <TableRow>
                <TableCell>Название</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sellers.map((s) => (
                <TableRow key={s.id} hover data-testid="seller-row" data-seller-id={s.id}>
                  <TableCell>{s.name}</TableCell>
                </TableRow>
              ))}
              {sellers.length === 0 ? (
                <TableRow>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary" data-testid="sellers-empty">
                      Пока нет селлеров. Добавьте первого в форме справа.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>

        {isFulfillmentAdmin ? (
          <Paper
            variant="outlined"
            component="form"
            noValidate
            onSubmit={(e) => void onSubmit(e)}
            sx={{ p: 2, width: { xs: '100%', md: 360 } }}
            data-testid="seller-create-panel"
          >
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
              Добавить селлера
            </Typography>
            <Stack spacing={2}>
              <TextField
                name="seller_name"
                label="Название / бренд"
                required
                fullWidth
                size="small"
                autoComplete="off"
                placeholder="Например, ACME Brand"
                slotProps={{ htmlInput: { 'data-testid': 'seller-name' } }}
              />
              <TextField
                name="seller_email"
                label="Email для входа"
                type="email"
                required
                fullWidth
                size="small"
                autoComplete="off"
                helperText="Пароль не задаётся: при первом входе селлер создаст его сам"
                slotProps={{ htmlInput: { 'data-testid': 'seller-email' } }}
              />
              <Button
                type="submit"
                variant="contained"
                disabled={busy}
                data-testid="seller-submit"
                startIcon={busy ? <CircularProgress size={16} color="inherit" /> : null}
              >
                {busy ? 'Сохранение…' : 'Добавить селлера'}
              </Button>
            </Stack>
          </Paper>
        ) : (
          <Alert severity="info" data-testid="sellers-admin-only">
            Добавление селлеров доступно только администратору фулфилмента.
          </Alert>
        )}
      </Stack>
    </Box>
  )
}
