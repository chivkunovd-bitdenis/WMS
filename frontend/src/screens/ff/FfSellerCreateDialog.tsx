import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type CreatedSeller = { id: string; name: string }

type Props = {
  open: boolean
  token: string
  authHeaders: (t: string) => Record<string, string>
  onClose: () => void
  onCreated: (seller: CreatedSeller) => void | Promise<void>
}

/**
 * Quick "just a name" seller creation — no login/email required.
 * The seller shows up immediately wherever the sellers list is used
 * (product creation, Excel import, catalog filter).
 */
export function FfSellerCreateDialog({ open, token, authHeaders, onClose, onCreated }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')

  useEffect(() => {
    if (open) {
      setName('')
      setError(null)
    }
  }, [open])

  function handleClose() {
    if (busy) return
    onClose()
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Укажите название селлера.')
      return
    }
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/sellers'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as CreatedSeller
      setName('')
      await onCreated(created)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать селлера.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="xs"
      data-testid="ff-seller-create-dialog"
    >
      <form noValidate onSubmit={(e) => void onSubmit(e)}>
        <DialogTitle>Создать селлера</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Селлер создаётся сразу, без входа и почты — только название. Он появится в списке
              селлеров и будет доступен при создании товаров.
            </Typography>
            {error ? (
              <Alert severity="error" data-testid="ff-seller-create-error">
                {error}
              </Alert>
            ) : null}
            <TextField
              autoFocus
              required
              size="small"
              label="Название / бренд"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например, ACME Brand"
              slotProps={{ htmlInput: { 'data-testid': 'ff-seller-create-name' } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} disabled={busy}>
            Отмена
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={busy}
            data-testid="ff-seller-create-submit"
          >
            {busy ? 'Создание…' : 'Создать'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
