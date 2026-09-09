// Scrollable feed of messages.
//
// Renders text, image attachments inline (per WMS-397 paste flow), generic
// files as compact download chips, and an AttachedDocCard when the message
// originated from a document page. All rows are static; editing is not part
// of the MVP UI yet — only the API supports it.

import { memo, useMemo } from 'react'
import { Box, Chip, Link, Stack, Typography } from '@mui/material'
import AttachFileOutlinedIcon from '@mui/icons-material/AttachFileOutlined'
import { AttachedDocCard } from './AttachedDocCard'
import { attachmentContentUrl, type ChatMessage } from './chatApi'

type Props = {
  currentUserId: string | null
  messages: ChatMessage[]
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
    })
  } catch {
    return iso
  }
}

export const ChatFeed = memo(function ChatFeed({ currentUserId, messages }: Props) {
  const rows = useMemo(() => messages, [messages])
  if (rows.length === 0) {
    return (
      <Box sx={{ px: 3, py: 6, textAlign: 'center' }}>
        <Typography color="text.secondary">Сообщений пока нет.</Typography>
      </Box>
    )
  }
  return (
    <Stack spacing={1.25} sx={{ p: 2 }}>
      {rows.map((message) => {
        const mine = currentUserId !== null && message.author_user_id === currentUserId
        return (
          <Box
            key={message.id}
            sx={{
              display: 'flex',
              justifyContent: mine ? 'flex-end' : 'flex-start',
            }}
            data-testid="chat-message-row"
            data-mine={mine ? 'true' : 'false'}
          >
            <Box
              sx={{
                maxWidth: '78%',
                bgcolor: mine ? 'primary.light' : 'grey.100',
                color: mine ? 'primary.contrastText' : 'text.primary',
                borderRadius: 2,
                px: 1.5,
                py: 1,
              }}
            >
              {message.attached_document ? (
                <Box sx={{ mb: message.text ? 0.75 : 0 }}>
                  <AttachedDocCard document={message.attached_document} />
                </Box>
              ) : null}
              {message.text ? (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {message.text}
                </Typography>
              ) : null}
              {message.attachments.length > 0 ? (
                <Stack direction="row" spacing={1} sx={{ mt: 0.75, flexWrap: 'wrap' }}>
                  {message.attachments.map((attachment) =>
                    attachment.is_image ? (
                      <Box
                        key={attachment.id}
                        component="a"
                        href={attachmentContentUrl(attachment.id)}
                        target="_blank"
                        rel="noreferrer"
                        sx={{ display: 'inline-block' }}
                      >
                        <Box
                          component="img"
                          src={attachmentContentUrl(attachment.id)}
                          alt={attachment.filename}
                          sx={{
                            maxWidth: 220,
                            maxHeight: 220,
                            borderRadius: 1,
                            display: 'block',
                          }}
                          data-testid="chat-message-image"
                        />
                      </Box>
                    ) : (
                      <Chip
                        key={attachment.id}
                        icon={<AttachFileOutlinedIcon fontSize="small" />}
                        component={Link}
                        href={attachmentContentUrl(attachment.id)}
                        target="_blank"
                        rel="noreferrer"
                        clickable
                        label={`${attachment.filename} · ${Math.max(1, Math.round(attachment.size_bytes / 1024))} КБ`}
                        variant="outlined"
                        size="small"
                        data-testid="chat-message-file"
                      />
                    ),
                  )}
                </Stack>
              ) : null}
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mt: 0.5,
                  opacity: 0.75,
                  textAlign: 'right',
                }}
              >
                {formatTime(message.created_at)}
                {message.edited_at ? ' · изменено' : ''}
              </Typography>
            </Box>
          </Box>
        )
      })}
    </Stack>
  )
})
