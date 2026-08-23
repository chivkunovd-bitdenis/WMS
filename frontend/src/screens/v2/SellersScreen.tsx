import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import { ErrorNotice, PrimaryAction, SecondaryAction } from '../../ui-kit'

type SellerRow = { id: string; name: string }
type SellerProfile = { legal_name: string; inn: string; kpp: string }

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
  const [searchParams] = useSearchParams()
  const requestedSellerId = searchParams.get('seller_id')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [selectedSeller, setSelectedSeller] = useState<SellerRow | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSuccess, setProfileSuccess] = useState(false)
  const [profiles, setProfiles] = useState<Record<string, SellerProfile>>({})
  const [profileRevision, setProfileRevision] = useState(0)

  useEffect(() => {
    if (!requestedSellerId) return
    const seller = sellers.find((candidate) => candidate.id === requestedSellerId)
    if (!seller) return
    setSelectedSeller(seller)
    setProfileOpen(true)
    setProfileError(null)
    setProfileSuccess(false)
    void loadSellerProfile(seller.id)
  }, [requestedSellerId, sellers])

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

  function openSeller(seller: SellerRow) {
    setSelectedSeller(seller)
    setProfileOpen(false)
    setProfileError(null)
    setProfileSuccess(false)
  }

  async function loadSellerProfile(sellerId: string) {
    if (!token) return
    setProfileError(null)
    setProfileLoading(true)
    try {
      const res = await fetch(apiUrl(`/billing/profiles/sellers/${sellerId}`), {
        headers: authHeaders(token),
      })
      if (!res.ok) {
        setProfileError(await readApiErrorMessage(res))
        return
      }
      const profile = (await res.json()) as SellerProfile | null
      if (profile) {
        setProfiles((current) => ({ ...current, [sellerId]: profile }))
        setProfileRevision((current) => current + 1)
      }
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Не удалось загрузить реквизиты.')
    } finally {
      setProfileLoading(false)
    }
  }

  async function saveSellerProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedSeller) return
    const form = e.currentTarget
    setProfileError(null)
    setProfileSuccess(false)
    const data = new FormData(form)
    const profile = {
      legal_name: String(data.get('legal_name') ?? '').trim(),
      inn: String(data.get('inn') ?? '').trim(),
      kpp: String(data.get('kpp') ?? '').trim(),
    }
    if (!profile.legal_name) {
      setProfileError('Укажите юридическое наименование.')
      return
    }
    if (!profile.inn) {
      setProfileError('Укажите ИНН.')
      return
    }
    setProfileBusy(true)
    try {
      const res = await fetch(apiUrl(`/billing/profiles/sellers/${selectedSeller.id}`), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      })
      if (!res.ok) {
        setProfileError(await readApiErrorMessage(res))
        return
      }
      setProfiles((current) => ({ ...current, [selectedSeller.id]: profile }))
      setProfileSuccess(true)
      setProfileRevision((current) => current + 1)
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Не удалось сохранить реквизиты.')
    } finally {
      setProfileBusy(false)
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
                <TableRow key={s.id} hover onClick={() => openSeller(s)} data-testid="seller-row" data-seller-id={s.id}>
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
      <Dialog open={Boolean(selectedSeller)} onClose={profileBusy ? undefined : () => setSelectedSeller(null)} fullWidth maxWidth="sm">
        <DialogTitle>{selectedSeller ? `Селлер: ${selectedSeller.name}` : ''}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Данные аккаунта селлера
          </Typography>
          <Box component="details" open={profileOpen} onToggle={(event) => {
            const open = (event.currentTarget as HTMLDetailsElement).open
            setProfileOpen(open)
            if (open && selectedSeller) void loadSellerProfile(selectedSeller.id)
          }} data-testid="seller-billing-details">
            <Typography component="summary" sx={{ cursor: 'pointer', fontWeight: 600 }}>
              Реквизиты для счетов
            </Typography>
            {profileOpen && selectedSeller ? (
              <Box component="form" key={`${selectedSeller.id}-${profileRevision}`} onSubmit={(e) => void saveSellerProfile(e)} sx={{ pt: 2 }}>
                {profileError ? <ErrorNotice testId="seller-profile-error">{profileError}</ErrorNotice> : null}
                {profileSuccess ? <Typography color="success.main" sx={{ mb: 2 }} data-testid="seller-profile-success">Реквизиты сохранены</Typography> : null}
                <Stack spacing={2}>
                  <TextField name="legal_name" label="Юридическое наименование" required defaultValue={profiles[selectedSeller.id]?.legal_name ?? ''} fullWidth size="small" disabled={profileLoading} slotProps={{ htmlInput: { 'data-testid': 'seller-legal-name' } }} />
                  <TextField name="inn" label="ИНН" required defaultValue={profiles[selectedSeller.id]?.inn ?? ''} fullWidth size="small" disabled={profileLoading} slotProps={{ htmlInput: { 'data-testid': 'seller-inn' } }} />
                  <TextField name="kpp" label="КПП" defaultValue={profiles[selectedSeller.id]?.kpp ?? ''} fullWidth size="small" disabled={profileLoading} slotProps={{ htmlInput: { 'data-testid': 'seller-kpp' } }} />
                  <PrimaryAction type="submit" disabled={profileBusy || profileLoading} data-testid="seller-profile-save">
                    {profileLoading ? 'Загрузка…' : profileBusy ? 'Сохранение…' : 'Сохранить реквизиты'}
                  </PrimaryAction>
                </Stack>
              </Box>
            ) : null}
          </Box>
        </DialogContent>
        <DialogActions>
          <SecondaryAction onClick={() => setSelectedSeller(null)} disabled={profileBusy}>Закрыть</SecondaryAction>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
