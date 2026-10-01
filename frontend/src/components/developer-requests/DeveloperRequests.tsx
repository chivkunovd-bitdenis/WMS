import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, CircularProgress, Fab, IconButton, List, ListItemButton, Stack, Tab, Tabs, Tooltip, Typography } from '@mui/material'
import Close from '@mui/icons-material/Close'
import CheckCircleOutline from '@mui/icons-material/CheckCircleOutlineOutlined'
import ArrowBack from '@mui/icons-material/ArrowBack'
import { useLocation } from 'react-router-dom'
import { useHelpButtonBottom } from './useHelpButtonBottom'
import { apiUrl } from '../../api'
import { AppDialog, PrimaryAction, SecondaryAction, SelectInput, StatusChip, TextInput } from '../../ui-kit'
import { draftStorageKey, emptyDraft, readDraft, requestPayload, statusLabels, typeLabels, validateDraft } from './draft'
import type { Draft, RequestIdentity, RequestPayload, RequestRecord, RequestType } from './draft'

export type DeveloperRequestsProps = { me: RequestIdentity; token: string }

export function DeveloperRequests({ me, token }: DeveloperRequestsProps) {
  if (!me.id || !me.tenant_id || !token) return null
  const scope = draftStorageKey(me)
  // Reset synchronously on identity changes, so an old draft or response never flashes for a new user/shop.
  return <ScopedDeveloperRequests key={scope} scope={scope} token={token} />
}

function ScopedDeveloperRequests({ scope, token }: { scope: string; token: string }) {
  const { pathname } = useLocation()
  const helpBottom = useHelpButtonBottom()
  const [draft, setDraft] = useState<Draft>(() => { try { return readDraft(scope) } catch { return emptyDraft() } })
  const [storageError, setStorageError] = useState(false)
  const [open, setOpen] = useState(false)
  const [section, setSection] = useState<'new' | 'mine'>('new')
  const [errors, setErrors] = useState<ReturnType<typeof validateDraft>>({})
  const [error, setError] = useState('')
  const [recovery, setRecovery] = useState<'unknown' | 'conflict' | null>(null)
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const [success, setSuccess] = useState(false)
  const [keptEdits, setKeptEdits] = useState(false)
  const [records, setRecords] = useState<RequestRecord[]>([])
  const [detailId, setDetailId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RequestRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  function saveDraft(next: Draft, remove = false) {
    setDraft(next)
    try {
      if (remove) localStorage.removeItem(scope)
      else localStorage.setItem(scope, JSON.stringify(next))
      setStorageError(false)
    } catch { setStorageError(true) }
  }
  function edit(field: keyof Pick<Draft, 'description' | 'screen' | 'problem' | 'proposal' | 'type'>, value: string) {
    saveDraft({ ...draft, [field]: value })
    setErrors({})
  }
  function show() {
    // Pick up edits made in another tab before opening, without reading any authentication storage.
    if (!storageError) {
      try { setDraft(readDraft(scope)); setStorageError(false) } catch { setStorageError(true) }
    }
    setOpen(true); setSection('new'); setSuccess(false); setError(''); setErrors({}); setRecovery(null)
  }
  function clear() {
    if (submitting.current) return
    saveDraft(emptyDraft(), true); setErrors({}); setError(''); setRecovery(null)
  }
  function changeSection(value: 'new' | 'mine') {
    setSection(value); setDetailId(null); setDetail(null); setSuccess(false)
  }

  useEffect(() => {
    if (!open || section !== 'mine') return
    const controller = new AbortController()
    setLoading(true); setLoadError(''); setDetail(null)
    void (async () => {
      try {
        const res = await fetch(apiUrl(detailId ? `/developer-requests/${encodeURIComponent(detailId)}` : '/developer-requests'), {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        })
        if (!res.ok) throw new Error('load')
        const data: RequestRecord | RequestRecord[] = await res.json()
        if (controller.signal.aborted) return
        if (detailId) setDetail(data as RequestRecord)
        else setRecords((data as RequestRecord[]).sort((a, b) => b.created_at.localeCompare(a.created_at)))
      } catch {
        if (!controller.signal.aborted) setLoadError('Не удалось загрузить заявки. Попробуйте ещё раз.')
      } finally { if (!controller.signal.aborted) setLoading(false) }
    })()
    return () => controller.abort()
  }, [open, section, detailId, token, refresh])

  async function submit(recover = false) {
    if (submitting.current) return
    const validation = validateDraft(draft)
    if (!recover && Object.keys(validation).length) { setErrors(validation); return }
    const payload: RequestPayload = recover && draft.attempt ? draft.attempt : requestPayload(draft, pathname)
    if (!recover && draft.attempt && JSON.stringify(payload) !== JSON.stringify(draft.attempt)) {
      setRecovery('unknown')
      setError('Результат предыдущей отправки пока не подтверждён. Проверьте её отправку перед отправкой изменённого текста. Изменения останутся в черновике.')
      return
    }
    const sentDraft = { ...draft, attempt: draft.attempt ?? payload }
    saveDraft(sentDraft)
    submitting.current = true; setBusy(true); setError(''); setRecovery(null)
    try {
      const res = await fetch(apiUrl('/developer-requests'), {
        method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })
      if (!mounted.current) return
      if (res.status === 409) {
        setRecovery('conflict')
        setError('Предыдущая попытка уже сохранена с другим текстом. Посмотрите её в «Моих заявках» или продолжите текущий текст как новый черновик.')
        return
      }
      if (res.status === 422) {
        const body = await res.json() as { detail?: { code?: string; message?: string } }
        if (!mounted.current) return
        if (body.detail?.code === 'developer_request_description_too_long') {
          // A rejected correction does not disprove an earlier uncertain submission.
          if (JSON.stringify(sentDraft.attempt) === JSON.stringify(payload)) {
            saveDraft({ ...sentDraft, attempt: undefined })
          }
          setError(body.detail.message || 'Обращение слишком длинное для передачи разработчикам. Сократите текст и отправьте ещё раз.')
          return
        }
      }
      if (!res.ok) throw new Error('save')
      const saved = await res.json() as RequestRecord
      if (!saved.id) throw new Error('save')
      if (!mounted.current) return
      const changed = JSON.stringify(requestPayload(sentDraft, pathname)) !== JSON.stringify(payload)
      if (changed) saveDraft({ ...sentDraft, key: crypto.randomUUID(), attempt: undefined })
      else saveDraft(emptyDraft(), true)
      setKeptEdits(changed); setSuccess(true); setErrors({})
    } catch {
      if (mounted.current) setError('Не удалось подтвердить сохранение. Текст сохранён в форме. Повторите отправку: повтор этой попытки не создаст вторую заявку.')
    } finally {
      submitting.current = false
      if (mounted.current) setBusy(false)
    }
  }

  const actions = section === 'new' && !success ? (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, width: '100%', p: 1 }}>
      <Button size="small" onClick={clear} disabled={busy}>Очистить черновик</Button>
      <Box sx={{ display: 'flex', gap: 1, ml: 'auto', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
      <SecondaryAction onClick={() => setOpen(false)}>Отменить</SecondaryAction>
      <PrimaryAction type="submit" form="developer-request-form" disabled={busy || Boolean(recovery)}>
        {busy ? 'Отправляем…' : 'Отправить'}
      </PrimaryAction>
      </Box>
    </Box>
  ) : undefined

  return <>
    <Tooltip title="Задача разработчикам">
      <Fab color="primary" size="small" aria-label="Задача разработчикам" onClick={show}
        data-testid="developer-requests-open"
        sx={{ position: 'fixed', bottom: helpBottom, right: 16, zIndex: (theme) => theme.zIndex.drawer + 1, fontSize: 24, fontWeight: 700 }}>
        ?
      </Fab>
    </Tooltip>
    <AppDialog open={open} onClose={() => setOpen(false)} testId="developer-requests-dialog" maxWidth="sm"
      title={<Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
        <Box component="span">Задача разработчикам</Box>
        <IconButton size="small" aria-label="Закрыть" onClick={() => setOpen(false)}><Close /></IconButton>
      </Box>}
      actions={actions}>
      <Tabs value={section} onChange={(_, value: 'new' | 'mine') => changeSection(value)} aria-label="Обращения разработчикам" sx={{ mb: 3 }}>
        <Tab value="new" label="Новая заявка" id="request-new-tab" aria-controls="request-new-panel" />
        <Tab value="mine" label="Мои заявки" id="request-mine-tab" aria-controls="request-mine-panel" />
      </Tabs>
      {section === 'new' ? <Box role="tabpanel" id="request-new-panel" aria-labelledby="request-new-tab">
        {success ? <Stack spacing={2} sx={{ alignItems: 'center', py: 5, textAlign: 'center' }} role="status">
          <CheckCircleOutline color="success" sx={{ fontSize: 64 }} />
          <Typography variant="h6">Спасибо, ваше обращение зафиксировано</Typography>
          {keptEdits && <Typography color="text.secondary">Предыдущая заявка сохранена. Ваши изменения остались в черновике.</Typography>}
          <PrimaryAction onClick={() => { setSuccess(false); setError('') }}>{keptEdits ? 'Продолжить черновик' : 'Новая заявка'}</PrimaryAction>
        </Stack> : <Stack component="form" id="developer-request-form" noValidate spacing={2.5} onSubmit={(event) => { event.preventDefault(); void submit() }}>
          {storageError && <Alert severity="warning">Браузер не смог сохранить черновик. Не обновляйте страницу до отправки.</Alert>}
          {error && <Alert severity="error" role="alert">{error}{recovery && <Box sx={{ mt: 1 }}>
            {recovery === 'conflict' ? <Button size="small" onClick={() => {
              // A confirmed 409 proves the key is already used. Starting a new draft is explicit and sends nothing.
              saveDraft({ ...draft, key: crypto.randomUUID(), attempt: undefined })
              setRecovery(null); setError(''); setErrors({})
            }} disabled={busy}>Продолжить как новый черновик</Button> :
              <Button size="small" onClick={() => void submit(true)} disabled={busy}>Проверить отправку</Button>}
            <Button size="small" onClick={() => changeSection('mine')}>Мои заявки</Button>
          </Box>}</Alert>}
          <SelectInput label="Тип обращения" value={draft.type} onChange={(value) => edit('type', value as RequestType)}
            disabled={busy} options={Object.entries(typeLabels).map(([value, label]) => ({ value, label }))} />
          <Box sx={{ '& textarea:not([aria-hidden])': { minHeight: '112px' } }}>
            {draft.type === 'bug' ? <TextInput label="Описание ошибки" value={draft.description} onChange={(value) => edit('description', value)} multiline required disabled={busy} error={errors.description} /> :
              <Stack spacing={2.5}>
                <TextInput label="Экран / процесс" value={draft.screen} onChange={(value) => edit('screen', value)} required disabled={busy} error={errors.screen}
                  helperText="Например: Шаг упаковки при отгрузке FBS заказов" />
                <TextInput label="В чём сейчас проблема" value={draft.problem} onChange={(value) => edit('problem', value)} multiline required disabled={busy} error={errors.problem} />
                <TextInput label="Как можно улучшить" value={draft.proposal} onChange={(value) => edit('proposal', value)} multiline required disabled={busy} error={errors.proposal} />
              </Stack>}
          </Box>
        </Stack>}
      </Box> : <Box role="tabpanel" id="request-mine-panel" aria-labelledby="request-mine-tab" sx={{ minHeight: 180 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          {detailId ? <Button size="small" startIcon={<ArrowBack />} onClick={() => setDetailId(null)}>К списку</Button> : <Box />}
          <Button size="small" onClick={() => setRefresh((value) => value + 1)} disabled={loading}>Обновить</Button>
        </Box>
        {loading ? <Box sx={{ textAlign: 'center', py: 5 }}><CircularProgress size={28} aria-label="Загрузка заявок" /></Box> : loadError ?
          <Alert severity="error">{loadError}</Alert> : detail ? <Stack spacing={2.5}>
            <RequestMeta record={detail} />
            <Typography sx={{ fontWeight: 600 }}>{typeLabels[detail.type]}</Typography>
            {(detail.type === 'bug' ? [['Описание ошибки', detail.description]] : [['Экран / процесс', detail.screen], ['В чём сейчас проблема', detail.problem], ['Как можно улучшить', detail.proposal]]).map(([label, value]) =>
              <Box key={label}><Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>{label}</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{value}</Typography></Box>)}
          </Stack> : !records.length ? <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>У вас пока нет заявок</Typography> :
            <List disablePadding>{records.map((record) => <ListItemButton key={record.id} onClick={() => setDetailId(record.id)} sx={{ px: 1, py: 2, borderBottom: '1px solid', borderColor: 'divider', alignItems: 'flex-start' }}>
              <Box sx={{ minWidth: 0, width: '100%' }}><Typography sx={{ fontWeight: 600, overflowWrap: 'anywhere', mb: 1 }}>{record.title}</Typography><RequestMeta record={record} /></Box>
            </ListItemButton>)}</List>}
      </Box>}
    </AppDialog>
  </>
}
function RequestMeta({ record }: { record: RequestRecord }) {
  return <Stack direction="row" sx={{ gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
    <StatusChip label={statusLabels[record.status]} tone={record.status === 'completed' ? 'ok' : 'neutral'} />
    <Typography variant="body2" color="text.secondary" component="time" dateTime={record.created_at}>
      {new Date(record.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
    </Typography>
  </Stack>
}
