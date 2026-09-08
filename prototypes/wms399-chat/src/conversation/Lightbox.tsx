import { useEffect, useMemo } from 'react'
import { Backdrop, Box, IconButton, Stack, Tooltip, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeftOutlined'
import ChevronRightIcon from '@mui/icons-material/ChevronRightOutlined'
import DownloadIcon from '@mui/icons-material/DownloadOutlined'
import { useStore } from '../state/store'
import { fmtBytes, fmtTime } from '../utils/format'

export function Lightbox() {
  const { ui, dispatch, data, actorById } = useStore()

  const opened = ui.openLightbox
  const message = opened ? data.messages.get(opened.messageId) : null
  const author = message ? actorById.get(message.authorId) : null

  const images = useMemo(() => {
    if (!message?.attachments) return []
    return message.attachments.filter((a) => a.kind === 'image' && (a.dataUri || a.blobUrl) && a.uploadStatus === 'done')
  }, [message])

  const index = opened ? images.findIndex((a) => a.id === opened.attachmentId) : -1
  const attachment = index >= 0 ? images[index] : null

  const close = () => dispatch({ type: 'open_lightbox', payload: null })
  const goPrev = () => {
    if (!opened || images.length === 0) return
    const i = (index - 1 + images.length) % images.length
    dispatch({ type: 'open_lightbox', payload: { messageId: opened.messageId, attachmentId: images[i]!.id } })
  }
  const goNext = () => {
    if (!opened || images.length === 0) return
    const i = (index + 1) % images.length
    dispatch({ type: 'open_lightbox', payload: { messageId: opened.messageId, attachmentId: images[i]!.id } })
  }

  useEffect(() => {
    if (!opened) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      if (e.key === 'ArrowLeft') goPrev()
      if (e.key === 'ArrowRight') goNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!opened || !attachment) return null

  return (
    <Backdrop
      open
      onClick={close}
      sx={{ zIndex: (t) => t.zIndex.modal + 1, bgcolor: 'rgba(15, 23, 42, 0.92)', p: 2 }}
    >
      <Box
        onClick={(e) => e.stopPropagation()}
        sx={{
          maxWidth: '100%',
          maxHeight: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 2,
          width: '100%',
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignSelf: 'stretch',
            alignItems: 'center',
            color: 'common.white',
            px: 1,
          }}
        >
          <Stack sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle2" noWrap>
              {attachment.name}
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.75 }} noWrap>
              {author?.name ?? '—'} · {message ? fmtTime(message.createdAt) : ''} · {fmtBytes(attachment.size)}
              {images.length > 1 ? ` · ${index + 1} из ${images.length}` : ''}
            </Typography>
          </Stack>
          <Tooltip title="Скачать (демо)">
            <IconButton
              sx={{ color: 'common.white' }}
              aria-label="Скачать"
              component="a"
              href={attachment.dataUri ?? attachment.blobUrl ?? '#'}
              download={attachment.name}
              onClick={(e) => e.stopPropagation()}
            >
              <DownloadIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Закрыть (Esc)">
            <IconButton sx={{ color: 'common.white' }} aria-label="Закрыть" onClick={close}>
              <CloseIcon />
            </IconButton>
          </Tooltip>
        </Stack>
        <Box
          sx={{
            position: 'relative',
            width: '100%',
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {images.length > 1 ? (
            <IconButton
              onClick={goPrev}
              aria-label="Предыдущее"
              sx={{ position: 'absolute', left: 8, color: 'common.white', bgcolor: 'rgba(0,0,0,0.3)' }}
            >
              <ChevronLeftIcon />
            </IconButton>
          ) : null}
          <img
            src={attachment.dataUri ?? attachment.blobUrl}
            alt={attachment.name}
            style={{
              maxWidth: '100%',
              maxHeight: '78vh',
              borderRadius: 8,
              boxShadow: '0 6px 40px rgba(0,0,0,0.4)',
              background: '#111',
            }}
          />
          {images.length > 1 ? (
            <IconButton
              onClick={goNext}
              aria-label="Следующее"
              sx={{ position: 'absolute', right: 8, color: 'common.white', bgcolor: 'rgba(0,0,0,0.3)' }}
            >
              <ChevronRightIcon />
            </IconButton>
          ) : null}
        </Box>
        {message?.text ? (
          <Box
            sx={{
              maxWidth: 640,
              alignSelf: 'center',
              px: 2,
              py: 1,
              borderRadius: 2,
              bgcolor: 'rgba(255,255,255,0.08)',
              color: 'common.white',
            }}
          >
            <Typography variant="body2">{message.text}</Typography>
          </Box>
        ) : null}
      </Box>
    </Backdrop>
  )
}
