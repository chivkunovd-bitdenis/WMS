import { useCallback, useEffect, useState, type FormEvent } from 'react'
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
import { sellerPortalUrl } from '../../utils/portalUrls'
import { FfBillingProfilesDialog } from '../ff/FfBillingProfilesDialog'

type SellerRow = { id: string; name: string }

/** Сохранённые реквизиты в строке селлера: видно, но не редактируется. */
function SellerProfileSummary({ profile }: { profile: SellerProfile | null }) {
  if (!profile?.inn) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="seller-profile-empty">
        Не заполнены
      </Typography>
    )
  }
  const bank = [profile.bank_name, profile.bik ? `БИК ${profile.bik}` : null, profile.settlement_account]
    .filter(Boolean)
    .join(' · ')
  return (
    <Stack spacing={0.25} data-testid="seller-profile-summary">
      <Typography variant="body2">{profile.legal_name}</Typography>
      <Typography variant="caption" color="text.secondary">
        {[`ИНН ${profile.inn}`, profile.kpp ? `КПП ${profile.kpp}` : null].filter(Boolean).join(', ')}
      </Typography>
      {bank ? (
        <Typography variant="caption" color="text.secondary">
          {bank}
        </Typography>
      ) : null}
    </Stack>
  )
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  isFulfillmentAdmin: boolean
  sellers: SellerRow[]
  onRefresh: () => void | Promise<void>
}

type SellerProfile = {
  legal_name?: string | null
  inn?: string | null
  kpp?: string | null
  bank_name?: string | null
  bik?: string | null
  settlement_account?: string | null
}

export function SellersScreen({
  token,
  authHeaders,
  isFulfillmentAdmin,
  sellers,
  onRefresh,
}: Props) {
  const [busy, setBusy] = useState(false)
  // Реквизиты живут на селлере: заполняются один раз и дальше просто видны в
  // его строке. Счёт собирается по ним же — снимок берётся в момент выставления.
  const [profiles, setProfiles] = useState<Record<string, SellerProfile | null>>({})

  const loadProfiles = useCallback(async () => {
    if (!token || !isFulfillmentAdmin) return
    const pairs = await Promise.all(
      sellers.map(async (seller) => {
        try {
          const response = await fetch(apiUrl(`/billing/profiles/sellers/${seller.id}`), {
            headers: authHeaders(token),
          })
          if (!response.ok) return [seller.id, null] as const
          return [seller.id, (await response.json()) as SellerProfile | null] as const
        } catch {
          return [seller.id, null] as const
        }
      }),
    )
    setProfiles(Object.fromEntries(pairs))
  }, [authHeaders, isFulfillmentAdmin, sellers, token])

  useEffect(() => {
    void loadProfiles()
  }, [loadProfiles])
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
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/sellers/with-account'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as {
        seller_id: string
        seller_name: string
        email: string
      }

      form.reset()
      await onRefresh()
      const portalLink = sellerPortalUrl()
      setSuccess(
        `Селлер «${created.seller_name}» создан. Передайте селлеру email ${created.email} и ссылку: ${portalLink} ` +
          '(не корень сайта /). Первый вход: пароль пустой — система попросит задать новый.',
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
                <TableCell>Реквизиты для счетов</TableCell>
                {isFulfillmentAdmin ? <TableCell align="right" /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {sellers.map((s) => (
                <TableRow key={s.id} hover data-testid="seller-row" data-seller-id={s.id}>
                  <TableCell>{s.name}</TableCell>
                  <TableCell>
                    <SellerProfileSummary profile={profiles[s.id] ?? null} />
                  </TableCell>
                  {isFulfillmentAdmin ? (
                    <TableCell align="right">
                      <FfBillingProfilesDialog
                        token={token}
                        sellerId={s.id}
                        sellerName={s.name}
                        onSaved={() => void loadProfiles()}
                      />
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
              {sellers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={isFulfillmentAdmin ? 3 : 2}>
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
