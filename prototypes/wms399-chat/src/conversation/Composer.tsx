import { useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AttachFileIcon from '@mui/icons-material/AttachFileOutlined'
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined'
import SendIcon from '@mui/icons-material/SendRounded'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import AlternateEmailIcon from '@mui/icons-material/AlternateEmailOutlined'
import LockIcon from '@mui/icons-material/LockOutlined'
import PublicIcon from '@mui/icons-material/PublicOutlined'
import type { Attachment, Conversation, Visibility } from '../types'
import { useStore } from '../state/store'
import { canWriteInternal, defaultVisibility } from '../state/selectors'
import { fmtBytes } from '../utils/format'
import { Row } from '../common/Row'

const MAX_FILE_MB = 25
const MAX_FILES = 10

function inferKind(file: File): Attachment['kind'] {
  return file.type.startsWith('image/') ? 'image' : 'file'
}

function makeAttachment(file: File): Attachment | { error: string } {
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return { error: `Файл больше ${MAX_FILE_MB} МБ, нельзя` }
  }
  return {
    id: `att_${Math.random().toString(36).slice(2, 10)}`,
    name: file.name,
    mime: file.type || 'application/octet-stream',
    size: file.size,
    kind: inferKind(file),
    uploadStatus: 'uploading',
    uploadProgress: 0,
    blobUrl: URL.createObjectURL(file),
    dataUri: undefined,
  }
}

export function Composer({ conversation }: { conversation: Conversation }) {
  const { ui, dispatch, data, currentActor, actorById, actions } = useStore()
  const draft = ui.drafts[conversation.id] ?? {
    text: '',
    visibility: defaultVisibility(currentActor, conversation),
    attachments: [] as Attachment[],
    mentions: [],
  }
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const [mentionAnchor, setMentionAnchor] = useState<HTMLElement | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canInternal = canWriteInternal(currentActor, conversation)
  const sellerReading = currentActor.role === 'seller'

  const replyMsg = draft.replyToId ? data.messages.get(draft.replyToId) ?? null : null

  const mentionableActors = useMemo(() => {
    const list = conversation.participantIds
      .map((id) => actorById.get(id))
      .filter((a): a is NonNullable<typeof a> => Boolean(a))
      .filter((a) => a.id !== currentActor.id)
    if (sellerReading) return list.filter((a) => a.role !== 'seller' || a.id === currentActor.id)
    return list
  }, [conversation.participantIds, actorById, currentActor.id, sellerReading])

  const setDraft = (patch: Partial<typeof draft>) => dispatch({ type: 'set_draft', conversationId: conversation.id, patch })

  const clearReply = () => setDraft({ replyToId: undefined })
  const clearDocRef = () => setDraft({ documentRef: undefined })

  const onFilePick = (files: FileList | null) => {
    if (!files || files.length === 0) return
    const nextList: Attachment[] = [...draft.attachments]
    const arr = Array.from(files)
    if (nextList.length + arr.length > MAX_FILES) {
      setError(`Не больше ${MAX_FILES} вложений в одном сообщении`)
      return
    }
    for (const f of arr) {
      const made = makeAttachment(f)
      if ('error' in made) {
        setError(made.error)
        return
      }
      nextList.push({ ...made, uploadStatus: 'done', uploadProgress: 100 })
    }
    setError(null)
    setDraft({ attachments: nextList })
  }

  const onPaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    const items = e.clipboardData?.items
    if (!items) return
    const files: File[] = []
    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      if (it?.kind === 'file') {
        const f = it.getAsFile()
        if (f) files.push(f)
      }
    }
    if (files.length > 0) {
      e.preventDefault()
      onFilePick(dtToFileList(files))
    }
  }

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (e.dataTransfer.files?.length) onFilePick(e.dataTransfer.files)
  }

  const dropStop = (e: React.DragEvent<HTMLDivElement>) => e.preventDefault()

  const removeAttachment = (id: string) => {
    setDraft({ attachments: draft.attachments.filter((a) => a.id !== id) })
  }

  const send = () => {
    if (!draft.text.trim() && draft.attachments.length === 0 && !draft.documentRef) return
    if (currentActor.role === 'seller' && draft.visibility === 'internal') return
    if (conversation.kind === 'warehouse_internal' && draft.visibility !== 'internal') {
      setDraft({ visibility: 'internal' })
    }
    actions.sendMessage(conversation.id, {
      text: draft.text,
      visibility: draft.visibility,
      attachments: draft.attachments,
      replyToId: draft.replyToId,
      documentRef: draft.documentRef,
      mentions: draft.mentions,
    })
    setError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  const insertMention = (actorId: string) => {
    const actor = actorById.get(actorId)
    if (!actor) return
    const tag = `@${actor.short.toLowerCase()}`
    const nextText = (draft.text ?? '').replace(/@$/, '') + tag + ' '
    setDraft({
      text: nextText,
      mentions: [
        ...(draft.mentions ?? []),
        { actorId, offset: nextText.length - tag.length - 1, length: tag.length },
      ],
    })
    setMentionAnchor(null)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  return (
    <Paper
      elevation={0}
      onPaste={onPaste}
      onDrop={onDrop}
      onDragOver={dropStop}
      onDragEnter={dropStop}
      sx={{
        m: { xs: 1.5, md: 2 },
        p: 1.5,
        borderRadius: 3,
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
      data-testid="composer"
    >
      {replyMsg ? (
        <Row align="center" spacing={1} sx={{ mb: 1 }}>
          <Chip size="small" label="Ответ" sx={{ fontWeight: 700 }} />
          <Typography variant="caption" sx={{ flex: 1, color: 'text.secondary' }} noWrap>
            {replyMsg.text || (replyMsg.attachments?.length ? '📎 Вложение' : '[документ]')}
          </Typography>
          <IconButton size="small" onClick={clearReply} aria-label="Отменить ответ">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Row>
      ) : null}
      {draft.documentRef ? (
        <Row align="center" spacing={1} sx={{ mb: 1 }}>
          <Chip size="small" icon={<DescriptionIcon />} label="Карточка документа" sx={{ fontWeight: 700 }} />
          <Typography variant="caption" sx={{ flex: 1, color: 'text.secondary' }} noWrap>
            Вставим карточку при отправке
          </Typography>
          <IconButton size="small" onClick={clearDocRef} aria-label="Убрать документ">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Row>
      ) : null}
      {draft.attachments.length > 0 ? (
        <Row spacing={1} wrap sx={{ mb: 1 }}>
          {draft.attachments.map((a) => (
            <Chip
              key={a.id}
              variant="outlined"
              size="small"
              onDelete={() => removeAttachment(a.id)}
              label={`${a.name} · ${fmtBytes(a.size)}`}
              sx={{ maxWidth: 240, fontWeight: 600 }}
            />
          ))}
        </Row>
      ) : null}
      <TextField
        inputRef={inputRef}
        placeholder={
          draft.visibility === 'internal'
            ? 'Внутренняя заметка для склада. Селлеру не видна.'
            : 'Сообщение для канала. Enter — отправить, Shift+Enter — новая строка.'
        }
        multiline
        minRows={2}
        maxRows={6}
        fullWidth
        value={draft.text}
        onChange={(e) => {
          const val = e.target.value
          setDraft({ text: val })
          if (val.endsWith('@')) setMentionAnchor(inputRef.current)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            send()
          }
          if (e.key === '@') {
            setTimeout(() => setMentionAnchor(inputRef.current), 0)
          }
        }}
        sx={{
          bgcolor: draft.visibility === 'internal' ? '#fff7ed' : 'background.paper',
          borderRadius: 2,
          '& .MuiInputBase-root': { borderRadius: 2 },
        }}
        slotProps={{
          input: {
            sx: {
              fontFamily: 'inherit',
              fontSize: 14,
            },
          },
        }}
      />
      <Row align="center" spacing={0.5} wrap sx={{ mt: 1, rowGap: 1 }}>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          onChange={(e) => onFilePick(e.target.files)}
        />
        <Tooltip title="Прикрепить файлы (до 10 шт, до 25 МБ)">
          <IconButton onClick={() => fileInput.current?.click()} aria-label="Прикрепить файл">
            <AttachFileIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Вставить карточку документа">
          <IconButton onClick={() => dispatch({ type: 'toggle_document_picker', open: true })} aria-label="Документ">
            <DescriptionIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Упомянуть участника">
          <IconButton onClick={(e) => setMentionAnchor(e.currentTarget)} aria-label="Упоминание">
            <AlternateEmailIcon />
          </IconButton>
        </Tooltip>
        <Box sx={{ flexShrink: 0 }}>
          <VisibilityToggle
            value={draft.visibility}
            onChange={(v) => setDraft({ visibility: v })}
            canInternal={canInternal}
            conversation={conversation}
          />
        </Box>
        <Button
          size="medium"
          variant="contained"
          endIcon={<SendIcon />}
          disabled={!draft.text.trim() && draft.attachments.length === 0 && !draft.documentRef}
          onClick={send}
          sx={{ ml: 'auto', flexShrink: 0 }}
        >
          Отправить
        </Button>
      </Row>
      {error ? (
        <Alert severity="warning" sx={{ mt: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
      {ui.demo.offline ? (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Оффлайн (демо). Отправка упадёт с ошибкой, вложения помечаются «нет сети».
        </Alert>
      ) : null}
      <Menu anchorEl={mentionAnchor} open={!!mentionAnchor} onClose={() => setMentionAnchor(null)}>
        {mentionableActors.length === 0 ? (
          <MenuItem disabled>Никого нельзя упомянуть</MenuItem>
        ) : (
          mentionableActors.map((a) => (
            <MenuItem key={a.id} onClick={() => insertMention(a.id)}>
              <Row align="center" spacing={1}>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                  {a.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {a.title}
                </Typography>
              </Row>
            </MenuItem>
          ))
        )}
      </Menu>
    </Paper>
  )
}

function VisibilityToggle({
  value,
  onChange,
  canInternal,
  conversation,
}: {
  value: Visibility
  onChange: (v: Visibility) => void
  canInternal: boolean
  conversation: Conversation
}) {
  const forcedInternal = conversation.kind === 'warehouse_internal'
  if (forcedInternal) {
    return (
      <Chip
        size="small"
        icon={<LockIcon fontSize="small" />}
        label="Внутренний канал"
        sx={{ bgcolor: 'grey.900', color: 'grey.100', fontWeight: 700 }}
      />
    )
  }
  if (!canInternal) {
    return (
      <Chip
        size="small"
        icon={<PublicIcon fontSize="small" />}
        label="Селлеру виден"
        sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', fontWeight: 700 }}
      />
    )
  }
  return (
    <Row align="center" spacing={0.5}>
      <Chip
        size="small"
        icon={value === 'shared' ? <PublicIcon fontSize="small" /> : <LockIcon fontSize="small" />}
        label={value === 'shared' ? 'Селлеру виден' : 'Внутренняя заметка'}
        onClick={() => onChange(value === 'shared' ? 'internal' : 'shared')}
        sx={{
          bgcolor: value === 'shared' ? 'primary.main' : 'warning.main',
          color: value === 'shared' ? 'primary.contrastText' : 'warning.contrastText',
          fontWeight: 700,
          cursor: 'pointer',
        }}
      />
      <Tooltip title="Переключить видимость: внутренняя заметка склада или сообщение, видимое селлеру">
        <Switch
          size="small"
          checked={value === 'shared'}
          onChange={(e) => onChange(e.target.checked ? 'shared' : 'internal')}
          slotProps={{ input: { 'aria-label': 'Переключить видимость сообщения' } }}
        />
      </Tooltip>
    </Row>
  )
}

function dtToFileList(files: File[]): FileList {
  const dt = new DataTransfer()
  files.forEach((f) => dt.items.add(f))
  return dt.files
}
