// Additional conversations use the existing seller and FF accounts.

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

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setParticipants([]); setStaffOptions([]); setStaffError(null)
    if (!sellerId) { setStaffLoading(false); return }
    setStaffLoading(true)
    void fetch(apiUrl(`/operations/chat/participant-options?seller_id=${sellerId}`), {
      headers: authHeaders(token), signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw Error()
      const rows = await response.json() as StaffOption[]
      if (!controller.signal.aborted) setStaffOptions(rows)
    }).catch(() => {
      if (!controller.signal.aborted) setStaffError('Не удалось загрузить участников. Выберите продавца повторно.')
    }).finally(() => { if (!controller.signal.aborted) setStaffLoading(false) })
    return () => controller.abort()
  }, [authHeaders, open, sellerId, token])

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
    } catch {
      setError('Не удалось создать чат. Проверьте соединение и выбранных участников.')
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
              {staffError}
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
                placeholder="Найдите участника по email"
                data-testid="extra-chat-participants-input"
              />
            )}
          />
          <Typography variant="caption" color="text.secondary">
            Дополнительный чат видят создатель и выбранные участники. Основной чат продавца остаётся доступным.
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
