import { Avatar, Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import PersonIcon from '@mui/icons-material/Person'
import { memo, useCallback, useEffect, useState } from 'react'
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

function ProductPhotoThumbBase({
  src,
  alt = '',
  size = 44,
  previewSize = 240,
  testId,
}: Props) {
  const theme = useTheme()
  const [previewPos, setPreviewPos] = useState<PreviewPos | null>(null)
  const rawSrc = src?.trim() || null
  // Битая/протухшая ссылка на фото WB должна выглядеть так же, как отсутствие фото —
  // единая заглушка (силуэт), а не буква названия товара в кружке.
  //
  // MUI Avatar сам пытается подгрузить src отдельным внутренним Image()-пробником
  // (см. useLoaded в @mui/material/Avatar) и решает, что показать вместо картинки,
  // независимо от онError на реально отрендеренном <img>: если alt задан и src ещё
  // не сброшен в null, Avatar выбирает первую букву alt раньше, чем наш onError на
  // DOM-элементе успевает сработать (тот <img> к этому моменту уже может быть
  // размонтирован). Поэтому вместо onError на <img> используем свой собственный
  // независимый пробник (тот же приём, что и внутри MUI) — он не привязан к тому,
  // что и когда рендерит Avatar, и его результат надёжно приходит в наше состояние.
  const [loadFailed, setLoadFailed] = useState(false)
  useEffect(() => {
    setLoadFailed(false)
    if (!rawSrc) {
      return undefined
    }
    let active = true
    const probe = new Image()
    probe.onload = () => {
      if (active) {
        setLoadFailed(false)
      }
    }
    probe.onerror = () => {
      if (active) {
        setLoadFailed(true)
      }
    }
    probe.src = rawSrc
    return () => {
      active = false
    }
  }, [rawSrc])
  const imageSrc = loadFailed ? null : rawSrc

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
        >
          {/*
            Явный children — единственный надёжный (не зависящий от гонки состояний
            внутри MUI Avatar, см. комментарий выше) способ гарантировать, что при
            неудачной загрузке Avatar покажет именно эту заглушку-силуэт, а не первую
            букву alt. Ветка "буква из alt" в MUI Avatar проверяется только когда
            children не передан, так что передавая свою иконку мы её отключаем
            полностью, независимо от того, кто быстрее — наш пробник или их. Размер
            75% повторяет внутренний дефолт MUI (AvatarFallback), чтобы силуэт
            выглядел так же, как в случае "фото вообще нет".
          */}
          <PersonIcon sx={{ width: '75%', height: '75%' }} />
        </Avatar>
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

/**
 * memo: компонент повторяется в каждой строке операционных таблиц.
 * Без него любое обновление состояния экрана перерисовывало его во всех строках сразу.
 */
export const ProductPhotoThumb = memo(ProductPhotoThumbBase)
