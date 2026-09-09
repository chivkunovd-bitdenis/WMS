// Extra-chat creation dialog for FF admins — WMS-397 gap 3.
//
// Owner spec: FF admin can spin up an extra chat for a seller and add
// additional FF employees as participants. We reuse the existing REST
// endpoint (`POST /operations/chat/conversations/extra`) and the FF staff
// account listing (`GET /auth/staff-accounts`) as the participant picker
// source — no new backend surface required.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Autocomplete,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { createExtraChat, type ChatConversation } from './chatApi'

type SellerOption = { id: string; name: string }

type StaffOption = { id: string; email: string; role: string }

type Props = {
  open: boolean
  onClose: () => void
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellers: SellerOption[]
  // Notify the parent so it can select the freshly created conversation.
  onCreated: (conversation: ChatConversation) => void
  // Seed the seller when opened from a seller-scoped surface. Optional.
  initialSellerId?: string | null
}

export function ExtraChatCreateDialog({
  open,
  onClose,
  token,
  authHeaders,
  sellers,
  onCreated,
  initialSellerId = null,
}: Props) {
  const [sellerId, setSellerId] = useState<string>(initialSellerId ?? '')
  const [title, setTitle] = useState<string>('')
  const [participants, setParticipants] = useState<StaffOption[]>([])
  const [staffOptions, setStaffOptions] = useState<StaffOption[]>([])
  const [staffLoading, setStaffLoading] = useState(false)
  const [staffError, setStaffError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSellerId(initialSellerId ?? '')
    setTitle('')
    setParticipants([])
    setError(null)
  }, [initialSellerId, open])

  const loadStaff = useCallback(async () => {
    setStaffLoading(true)
    setStaffError(null)
    try {
      const res = await fetch(apiUrl('/auth/staff-accounts'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        throw new Error(`staff_${res.status}`)
      }
      const rows = (await res.json()) as Array<{ id: string; email: string; role: string }>
      setStaffOptions(rows.map((row) => ({ id: row.id, email: row.email, role: row.role })))
    } catch (exc) {
      setStaffError((exc as Error).message)
    } finally {
      setStaffLoading(false)
    }
  }, [authHeaders, token])

  useEffect(() => {
    if (!open) return
    void loadStaff()
  }, [loadStaff, open])

  const canSubmit = useMemo(
    () => Boolean(sellerId) && title.trim().length > 0 && !busy,
    [sellerId, title, busy],
  )

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const conv = await createExtraChat(token, authHeaders, {
        seller_id: sellerId,
        title: title.trim(),
        participant_user_ids: participants.map((p) => p.id),
      })
      onCreated(conv)
      onClose()
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setBusy(false)
    }
  }, [
    authHeaders,
    canSubmit,
    onClose,
    onCreated,
    participants,
    sellerId,
    title,
    token,
  ])

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Новый чат с продавцом</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error ? (
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}
          <FormControl fullWidth size="small" disabled={busy}>
            <InputLabel id="extra-chat-seller-label">Продавец</InputLabel>
            <Select
              labelId="extra-chat-seller-label"
              label="Продавец"
              value={sellerId}
              onChange={(e) => setSellerId(String(e.target.value))}
              data-testid="extra-chat-seller-select"
            >
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Название чата"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            size="small"
            disabled={busy}
            data-testid="extra-chat-title-input"
            helperText="Например: «Приёмка на выходных», «Возвраты июнь»"
          />
          {staffError ? (
            <Alert severity="warning" onClose={() => setStaffError(null)}>
              Не удалось загрузить список сотрудников: {staffError}
            </Alert>
          ) : null}
          <Autocomplete
            multiple
            options={staffOptions}
            value={participants}
            loading={staffLoading}
            disabled={busy}
            onChange={(_, next) => setParticipants(next)}
            getOptionLabel={(option) => option.email}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            renderOption={(props, option, { selected }) => (
              <ListItem {...props} key={option.id} dense>
                <Checkbox size="small" checked={selected} sx={{ mr: 1 }} />
                <ListItemText
                  primary={option.email}
                  secondary={option.role}
                />
              </ListItem>
            )}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Дополнительные участники"
                size="small"
                placeholder="Найдите сотрудника по email"
                data-testid="extra-chat-participants-input"
              />
            )}
          />
          <Typography variant="caption" color="text.secondary">
            FF-админы и так видят все чаты продавца. Явное добавление нужно,
            чтобы пригласить конкретного сотрудника со стороны фулфилмента —
            например, сменного лида по крупной поставке.
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          data-testid="extra-chat-create-submit"
        >
          Создать чат
        </Button>
      </DialogActions>
    </Dialog>
  )
}
