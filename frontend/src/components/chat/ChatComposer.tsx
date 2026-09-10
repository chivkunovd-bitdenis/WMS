import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, TextField, Typography } from '@mui/material'
import AttachFileOutlinedIcon from '@mui/icons-material/AttachFileOutlined'
import CloseIcon from '@mui/icons-material/Close'
import { ChatApiError, makeClientMessageId, sendMessage, uploadAttachment, listDraftAttachments, discardDraftAttachment,
  type AttachedDocument, type ChatAttachment, type ChatMessage, type SendMessageInput } from './chatApi'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  conversationId: string
  attachedDocument?: AttachedDocument
  autoFocus?: boolean
  placeholder?: string
  onSent?: (msg: ChatMessage) => void
}
type Staged = { id: string; file?: File; preview?: string; uploaded?: ChatAttachment }

export function ChatComposer({ token, authHeaders, conversationId, attachedDocument, autoFocus, placeholder, onSent }: Props) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<Staged[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(false)
  const [drafts, setDrafts] = useState<ChatAttachment[]>([])
  const [draftError, setDraftError] = useState(false)
  const [draftRefresh, setDraftRefresh] = useState(0)
  const [discardTarget, setDiscardTarget] = useState<ChatAttachment | null>(null)
  useEffect(() => {
    let active = true
    void listDraftAttachments(token, authHeaders, conversationId).then((rows) => {
      if (active) { setDrafts(rows); setDraftError(false) }
    }).catch(() => { if (active) { setDrafts([]); setDraftError(true) } })
    return () => { active = false }
  }, [token, authHeaders, conversationId, draftRefresh])
  const pending = useRef<SendMessageInput | null>(null)
  const busy = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  const urls = useRef<string[]>([])
  useEffect(() => () => { urls.current.forEach(URL.revokeObjectURL) }, [])
  const stage = (picked: File[]) => {
    if (busy.current || pending.current) return
    if (files.length + picked.length > 10) { setError('Не больше 10 файлов в сообщении.'); return }
    if (picked.some((f) => f.size > 25 * 1024 * 1024) ||
        files.reduce((n, f) => n + (f.file?.size ?? f.uploaded?.size_bytes ?? 0), 0) + picked.reduce((n, f) => n + f.size, 0) > 100 * 1024 * 1024) {
      setError('До 25 МБ на файл и 100 МБ на сообщение.'); return
    }
    const staged = picked.map((file) => {
      const preview = /image\/(png|jpeg|gif|webp|bmp)$/.test(file.type) ? URL.createObjectURL(file) : undefined
      if (preview) urls.current.push(preview)
      return { id: makeClientMessageId(), file, preview }
    })
    setFiles((old) => [...old, ...staged]); setError(null)
  }
  const submit = async () => {
    if (busy.current || (!text.trim() && !files.length)) return
    busy.current = true; setSending(true); setError(null)
    try {
      if (!pending.current) {
        const uploaded: string[] = []
        for (const row of files) {
          // Keep successful uploads for retry; failed uploads keep their File and preview.
          if (!row.uploaded && !row.file) throw new Error('attachment_missing')
          const attachment = row.uploaded ?? await uploadAttachment(token, authHeaders,
            conversationId, row.file!, row.file!.name)
          row.uploaded = attachment
          uploaded.push(attachment.id)
        }
        pending.current = { clientMessageId: makeClientMessageId(), text, attachmentIds: uploaded, attachedDocument }
      }
      const message = await sendMessage(token, authHeaders, conversationId, pending.current)
      pending.current = null; setRetry(false); setText(''); setFiles([])
      urls.current.forEach(URL.revokeObjectURL); urls.current = []
      onSent?.(message)
    } catch (exc) {
      // A definitive input/access rejection permits correcting the draft. An
      // uncertain network/server response must replay the exact original request.
      if (exc instanceof ChatApiError && exc.status >= 400 && exc.status < 500) pending.current = null
      setRetry(pending.current !== null)
      setError(exc instanceof ChatApiError && exc.message.includes('attachment_content_missing') ?
        'Файл вложения отсутствует. Уберите его из сообщения, удалите неотправленное вложение и загрузите файл заново. Текст сохранён.' :
        exc instanceof ChatApiError && exc.message.includes('attachment_storage_unavailable') ?
        'Хранилище файлов временно недоступно. Повторите отправку позже: текст и вложения сохранены.' :
        exc instanceof ChatApiError && exc.message.includes('draft_upload_budget_exceeded') ?
        'Достигнут лимит незавершённых загрузок: 10 файлов или 100 МБ во всех чатах. Прикрепите или удалите свои неотправленные вложения в соответствующих чатах. Новые файлы и текст сохранены в редакторе.' : pending.current ? 'Ответ сервера не получен. Повторите отправку: текст и файлы сохранены, повтор не создаст копию.' :
        'Не удалось отправить сообщение. Текст и файлы сохранены. Проверьте доступ, размер файлов и повторите.')
    } finally { busy.current = false; setSending(false); setDraftRefresh((n) => n + 1) }
  }
  const recover = (attachment: ChatAttachment) => {
    if (busy.current || pending.current || files.some((f) => f.uploaded?.id === attachment.id)) return
    if (files.length >= 10 || files.reduce((n, f) => n + (f.file?.size ?? f.uploaded?.size_bytes ?? 0), 0) + attachment.size_bytes > 100 * 1024 * 1024) {
      setError('До 10 файлов и 100 МБ на сообщение.'); return
    }
    setFiles((rows) => [...rows, { id: attachment.id, uploaded: attachment }])
  }
  const discard = async (attachment: ChatAttachment) => {
    if (busy.current || pending.current) return
    busy.current = true; setSending(true)
    try {
      await discardDraftAttachment(token, authHeaders, conversationId, attachment.id)
      setDrafts((rows) => rows.filter((row) => row.id !== attachment.id))
      setDiscardTarget(null)
    } catch {
      setDiscardTarget(null)
      setError('Не удалось удалить вложение. Оно могло быть отправлено в другой вкладке. Обновите список.')
    } finally { busy.current = false; setSending(false); setDraftRefresh((n) => n + 1) }
  }
  const availableDrafts = drafts.filter((d) => !files.some((f) => f.uploaded?.id === d.id))
  return <Box sx={{ borderTop: 1, borderColor: 'divider', p: 1.25 }}>
    <Dialog open={discardTarget !== null} onClose={() => { if (!sending) setDiscardTarget(null) }}>
      <DialogTitle>Удалить неотправленное вложение?</DialogTitle>
      <DialogContent>{discardTarget?.filename}. Файл будет удалён из черновиков этого чата.</DialogContent>
      <DialogActions>
        <Button disabled={sending} onClick={() => setDiscardTarget(null)}>Оставить</Button>
        <Button color="error" disabled={sending} onClick={() => { if (discardTarget) void discard(discardTarget) }}>Удалить файл</Button>
      </DialogActions>
    </Dialog>
    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
    {(availableDrafts.length > 0 || draftError) && <Box sx={{ mb: 1 }}>
      <Typography variant="caption">{draftError ? 'Не удалось прочитать неотправленные вложения.' : 'Ваши неотправленные вложения'}</Typography>
      <Button size="small" disabled={sending || retry} onClick={() => setDraftRefresh((n) => n + 1)}>Обновить вложения</Button>
      {availableDrafts.map((attachment) => <Stack key={attachment.id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>{attachment.filename}</Typography>
        <Button size="small" disabled={sending || retry} onClick={() => recover(attachment)}>Прикрепить</Button>
        <Button size="small" color="error" disabled={sending || retry} onClick={() => setDiscardTarget(attachment)}>Удалить файл</Button>
      </Stack>)}
    </Box>}
    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: files.length ? 1 : 0 }}>
      {files.map((row) => <Box key={row.id} sx={{ border: 1, borderColor: 'divider', p: 0.5, maxWidth: 180 }}>
        {row.preview && <Box component="img" src={row.preview} alt={row.file?.name ?? row.uploaded?.filename} sx={{ width: 90, height: 70, objectFit: 'contain' }} />}
        <Typography variant="caption" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{row.file?.name ?? row.uploaded?.filename}</Typography>
        <IconButton size="small" aria-label="Убрать вложение" disabled={sending || retry}
          onClick={() => setFiles((rows) => rows.filter((f) => f.id !== row.id))}><CloseIcon fontSize="small" /></IconButton>
      </Box>)}
    </Stack>
    <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
      <TextField fullWidth multiline maxRows={6} size="small" autoFocus={autoFocus} value={text}
        disabled={sending || retry} placeholder={placeholder ?? 'Сообщение…'}
        onChange={(e) => setText(e.target.value)}
        onPaste={(event) => {
          const images = Array.from(event.clipboardData.items).filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
            .map((item) => item.getAsFile()).filter((file): file is File => file !== null)
          if (images.length) { event.preventDefault(); stage(images) }
        }}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void submit() } }} />
      <IconButton disabled={sending || retry} aria-label="Прикрепить файл" onClick={() => input.current?.click()}><AttachFileOutlinedIcon /></IconButton>
      <input ref={input} type="file" multiple style={{ display: 'none' }} onChange={(e) => {
        stage(Array.from(e.target.files ?? [])); e.target.value = ''
      }} />
      <Button variant="contained" disabled={sending || (!text.trim() && !files.length)} onClick={() => void submit()}>
        {sending ? 'Отправляем…' : retry ? 'Повторить отправку' : 'Отправить'}
      </Button>
    </Stack>
  </Box>
}
