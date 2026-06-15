import { Avatar, Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { useCallback, useState } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  src: string | null | undefined
  alt?: string
  size?: number
  previewSize?: number
  testId?: string
}

type PreviewPos = { top: number; left: number }

function clampPreviewPos(anchor: DOMRect, previewSize: number): PreviewPos {
  const gap = 8
  const padding = 8
  let left = anchor.right + gap
  let top = anchor.top

  if (left + previewSize > window.innerWidth - padding) {
    left = anchor.left - previewSize - gap
  }
  if (top + previewSize > window.innerHeight - padding) {
    top = window.innerHeight - previewSize - padding
  }
  if (left < padding) {
    left = padding
  }
  if (top < padding) {
    top = padding
  }

  return { top, left }
}

export function ProductPhotoThumb({
  src,
  alt = '',
  size = 44,
  previewSize = 240,
  testId,
}: Props) {
  const theme = useTheme()
  const [previewPos, setPreviewPos] = useState<PreviewPos | null>(null)
  const imageSrc = src?.trim() || null

  const openPreview = useCallback(
    (el: HTMLElement) => {
      if (!imageSrc) {
        return
      }
      setPreviewPos(clampPreviewPos(el.getBoundingClientRect(), previewSize))
    },
    [imageSrc, previewSize],
  )

  const closePreview = useCallback(() => {
    setPreviewPos(null)
  }, [])

  return (
    <>
      <Box
        onMouseEnter={(e) => openPreview(e.currentTarget)}
        onMouseLeave={closePreview}
        onFocus={(e) => openPreview(e.currentTarget)}
        onBlur={closePreview}
        tabIndex={imageSrc ? 0 : -1}
        aria-label={imageSrc ? 'Увеличить фото товара' : undefined}
        sx={{
          display: 'inline-flex',
          lineHeight: 0,
          cursor: imageSrc ? 'zoom-in' : 'default',
          borderRadius: 1,
          outline: 'none',
          '&:focus-visible': imageSrc
            ? { boxShadow: `0 0 0 2px ${theme.palette.primary.main}` }
            : undefined,
        }}
      >
        <Avatar
          variant="rounded"
          src={imageSrc ?? undefined}
          alt={alt}
          sx={{ width: size, height: size }}
          slotProps={{ img: { loading: 'lazy' } }}
          data-testid={testId}
        />
      </Box>
      {imageSrc && previewPos
        ? createPortal(
            <Box
              component="img"
              src={imageSrc}
              alt={alt}
              data-testid="product-photo-enlarged"
              sx={{
                position: 'fixed',
                top: previewPos.top,
                left: previewPos.left,
                width: previewSize,
                height: previewSize,
                objectFit: 'contain',
                bgcolor: 'background.paper',
                borderRadius: 1,
                boxShadow: 4,
                border: '1px solid',
                borderColor: 'divider',
                pointerEvents: 'none',
                zIndex: theme.zIndex.tooltip,
              }}
            />,
            document.body,
          )
        : null}
    </>
  )
}
