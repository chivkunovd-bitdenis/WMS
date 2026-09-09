// Inline composer that submits chat messages.
//
// One text field + one "send" button, plus:
//   * an attach-file button that uploads through the standard REST endpoint
//   * a paste handler for Ctrl+V / Cmd+V that treats image blobs as inline
//     attachments (per WMS-397 minimal contract: paste-image renders inline,
//     not as a generic file block).
// The composer is dumb: it stages attachments locally, uploads them on
// paste/pick, and hands the resulting attachment IDs to onSend so the caller
// decides which conversation to post into.

import { useCallback, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AttachFileOutlinedIcon from '@mui/icons-material/AttachFileOutlined'
import SendOutlinedIcon from '@mui/icons-material/SendOutlined'
import CloseIcon from '@mui/icons-material/Close'
import {
  attachmentContentUrl,
  makeClientMessageId,
  sendMessage,
  uploadAttachment,
  type AttachedDocument,
  type ChatAttachment,
  type ChatMessage,
} from './chatApi'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  conversationId: string
  attachedDocument?: AttachedDocument
  autoFocus?: boolean
  placeholder?: string
  onSent?: (msg: ChatMessage) => void
}

type StagedAttachment = ChatAttachment & { previewUrl?: string }

export function ChatComposer({
  token,
  authHeaders,
  conversationId,
  attachedDocument,
  autoFocus,
  placeholder,
  onSent,
}: Props) {
  const [text, setText] = useState('')
  const [attachments, setAttachments] = useState<StagedAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const stageFile = useCallback(
    async (file: File | Blob, filename: string, isImage: boolean | undefined) => {
      setUploading(true)
      setError(null)
      try {
        const uploaded = await uploadAttachment(
          token,
          authHeaders,
          conversationId,
          file,
          filename,
          isImage,
        )
        const previewUrl = uploaded.is_image
          ? attachmentContentUrl(uploaded.id)
          : undefined
        setAttachments((prev) => [...prev, { ...uploaded, previewUrl }])
      } catch (exc) {
        setError((exc as Error).message)
      } finally {
        setUploading(false)
      }
    },
    [authHeaders, conversationId, token],
  )

  const handlePaste = useCallback(
    (event: React.ClipboardEvent<HTMLDivElement>) => {
      // Grab image blobs from the clipboard. This is what covers both Ctrl+V
      // (Windows/Linux) and Cmd+V (macOS): the DataTransfer API is identical.
      const items = event.clipboardData?.items
      if (!items) return
      for (let index = 0; index < items.length; index += 1) {
        const item = items[index]
        if (item.kind === 'file' && item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (!file) continue
          event.preventDefault()
          const extension = item.type.split('/')[1] ?? 'png'
          const filename = `paste-${Date.now()}.${extension}`
          void stageFile(file, filename, true)
        }
      }
    },
    [stageFile],
  )

  const handleFilePick = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return
      const isImage = file.type.startsWith('image/') || undefined
      await stageFile(file, file.name, isImage)
      event.target.value = ''
    },
    [stageFile],
  )

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((row) => row.id !== id))
  }, [])

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !sending
  const submit = useCallback(async () => {
    if (!canSend) return
    setSending(true)
    setError(null)
    try {
      const msg = await sendMessage(token, authHeaders, conversationId, {
        clientMessageId: makeClientMessageId(),
        text,
        attachmentIds: attachments.map((row) => row.id),
        attachedDocument,
      })
      setText('')
      setAttachments([])
      onSent?.(msg)
    } catch (exc) {
      setError((exc as Error).message)
    } finally {
      setSending(false)
    }
  }, [
    attachments,
    attachedDocument,
    authHeaders,
    canSend,
    conversationId,
    onSent,
    text,
    token,
  ])

  return (
    <Box sx={{ borderTop: 1, borderColor: 'divider', p: 1.25, bgcolor: '#fff' }}>
      {error ? (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
      {attachments.length > 0 ? (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: 1 }}>
          {attachments.map((row) => (
            <Box
              key={row.id}
              sx={{
                position: 'relative',
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                p: 0.75,
                display: 'flex',
                gap: 0.75,
                alignItems: 'center',
                maxWidth: 220,
              }}
              data-testid="chat-staged-attachment"
            >
              {row.previewUrl ? (
                <Box
                  component="img"
                  src={row.previewUrl}
                  alt={row.filename}
                  sx={{
                    width: 44,
                    height: 44,
                    objectFit: 'cover',
                    borderRadius: 0.5,
                  }}
                />
              ) : (
                <AttachFileOutlinedIcon fontSize="small" />
              )}
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" noWrap>
                  {row.filename}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {Math.max(1, Math.round(row.size_bytes / 1024))} КБ
                </Typography>
              </Box>
              <IconButton
                size="small"
                aria-label="убрать вложение"
                onClick={() => removeAttachment(row.id)}
                sx={{ ml: 'auto' }}
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>
          ))}
        </Stack>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
        <TextField
          fullWidth
          multiline
          maxRows={6}
          size="small"
          value={text}
          autoFocus={autoFocus}
          placeholder={placeholder ?? 'Сообщение продавцу…'}
          onChange={(event) => setText(event.target.value)}
          onPaste={handlePaste}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault()
              void submit()
            }
          }}
          data-testid="chat-composer-input"
        />
        <Tooltip title="Прикрепить файл">
          <span>
            <IconButton
              size="small"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || sending}
              aria-label="Прикрепить файл"
            >
              <AttachFileOutlinedIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFilePick}
          style={{ display: 'none' }}
          data-testid="chat-composer-file-input"
        />
        <Button
          variant="contained"
          size="small"
          endIcon={sending ? <CircularProgress size={14} color="inherit" /> : <SendOutlinedIcon fontSize="small" />}
          disabled={!canSend}
          onClick={() => void submit()}
          data-testid="chat-composer-send"
        >
          Отправить
        </Button>
      </Stack>
      {uploading ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Загружаем вложение…
        </Typography>
      ) : null}
    </Box>
  )
}
