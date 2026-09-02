import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Box, Button, IconButton, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import PauseOutlinedIcon from '@mui/icons-material/PauseOutlined'
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined'
import SkipNextOutlinedIcon from '@mui/icons-material/SkipNextOutlined'
import ReplayOutlinedIcon from '@mui/icons-material/ReplayOutlined'

import type { Scenario } from './scenes/scenarios'

/**
 * Проигрыватель сценария: живой макет, который сам идёт по шагам.
 *
 * Макет открывается в `<iframe>`, а не рендерится рядом со статьёй, и это
 * решение, а не лень. Причин три. Шелл портала держит шапку на `position:
 * fixed` — внутри статьи она вылезла бы поверх всей страницы. Макеты подменяют
 * глобальный `fetch`, и внутри рамки эта подмена физически не может дотянуться
 * до настоящего портала. И, наконец, страница макета собирается как обычная
 * точка входа `/kb-scenes.html`, то есть один и тот же файл показывает и
 * проигрыватель, и та страница, с которой снимают картинки для статей —
 * расхождению взяться неоткуда.
 *
 * Рамка кладётся не на глаз: элемент ищется по `data-testid` внутри макета,
 * у него спрашивается настоящий прямоугольник, и координаты пересчитываются
 * в масштаб, в котором макет вписан в ширину статьи.
 */

type Props = {
  scenario: Scenario
}

/** Логический размер макета. Ровно в нём экран верстался и снимался. */
const FRAME_WIDTH = 1440
const FRAME_HEIGHT = 900

/** Пауза после нажатия — чтобы человек увидел, что произошло от нажатия. */
const AFTER_CLICK_MS = 900

type Highlight = { left: number; top: number; width: number; height: number }

export function ScenarioPlayer({ scenario }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [scale, setScale] = useState(0.5)
  const [started, setStarted] = useState(false)
  const [playing, setPlaying] = useState(true)
  const [index, setIndex] = useState(0)
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [loadedScene, setLoadedScene] = useState<string | null>(null)

  const step = scenario.steps[index]
  const sceneOfStep = step?.scene ?? scenario.steps[0]?.scene ?? null

  // Макет вписываем в ширину статьи. Меряем контейнер, а не окно: статья живёт
  // внутри портала с левым меню, и ширина окна тут ничего не говорит.
  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return
    const measure = () => {
      const width = host.clientWidth
      if (width > 0) setScale(width / FRAME_WIDTH)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(host)
    return () => observer.disconnect()
  }, [started])

  // Рамку поднимаем не сразу, а следующим кадром: сначала должна отрисоваться
  // сама статья. Внутри рамки грузится второй бандл портала, и если начать с
  // него, читатель несколько секунд смотрит на пустой экран вместо текста.
  useEffect(() => {
    const timer = window.setTimeout(() => setStarted(true), 300)
    return () => window.clearTimeout(timer)
  }, [])

  const findAnchor = useCallback((selector: string): HTMLElement | null => {
    const doc = frameRef.current?.contentDocument
    if (!doc) return null
    return doc.querySelector<HTMLElement>(selector)
  }, [])

  const placeHighlight = useCallback(
    (selector: string) => {
      const element = findAnchor(selector)
      if (!element) {
        setHighlight(null)
        return
      }
      element.scrollIntoView({ block: 'center', behavior: 'auto' })
      const rect = element.getBoundingClientRect()
      setHighlight({
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      })
    },
    [findAnchor],
  )

  const goNext = useCallback(() => {
    setIndex((current) => (current + 1) % scenario.steps.length)
  }, [scenario.steps.length])

  // Смена макета: если следующий шаг живёт в другом макете, ждём его загрузки.
  useEffect(() => {
    if (!started || !sceneOfStep) return
    if (loadedScene === sceneOfStep) return
    const frame = frameRef.current
    if (!frame) return
    setHighlight(null)
    frame.src = `/kb-scenes.html?scene=${sceneOfStep}`
  }, [started, sceneOfStep, loadedScene])

  // Основной такт: поставить рамку, подождать, нажать, шагнуть дальше.
  useEffect(() => {
    if (!started || !step || loadedScene !== step.scene) return
    let cancelled = false
    // Экран внутри рамки мог ещё дорисовываться — даём ему кадр.
    const place = window.setTimeout(() => {
      if (!cancelled) placeHighlight(step.anchor)
    }, 120)
    if (!playing) return () => {
      cancelled = true
      window.clearTimeout(place)
    }

    const dwell = window.setTimeout(() => {
      if (cancelled) return
      if (step.click) {
        findAnchor(step.anchor)?.click()
        window.setTimeout(() => {
          if (!cancelled) goNext()
        }, AFTER_CLICK_MS)
        return
      }
      goNext()
    }, step.dwellMs ?? 3200)

    return () => {
      cancelled = true
      window.clearTimeout(place)
      window.clearTimeout(dwell)
    }
  }, [started, step, playing, loadedScene, placeHighlight, findAnchor, goNext])

  const onFrameLoad = () => {
    const frame = frameRef.current
    if (!frame) return
    const url = new URL(frame.src, window.location.origin)
    setLoadedScene(url.searchParams.get('scene'))
  }

  const frameHeight = Math.round(FRAME_HEIGHT * scale)

  return (
    <Paper
      variant="outlined"
      sx={{ my: 3, overflow: 'hidden' }}
      data-testid="knowledge-scenario-player"
    >
      <Box sx={{ px: 2, py: 1.25, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Показ по шагам: {scenario.title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Это тренажёр на выдуманных данных, а не рабочий экран. Ничего из того, что здесь
          нажимается, на складе не происходит.
        </Typography>
      </Box>

      <Box
        ref={hostRef}
        sx={{
          position: 'relative',
          width: '100%',
          height: started ? frameHeight : 260,
          bgcolor: 'background.default',
          overflow: 'hidden',
        }}
      >
        {started ? (
          <>
            <Box
              component="iframe"
              ref={frameRef}
              title={`Живой макет: ${scenario.title}`}
              onLoad={onFrameLoad}
              sx={{
                width: FRAME_WIDTH,
                height: FRAME_HEIGHT,
                border: 0,
                transform: `scale(${scale})`,
                transformOrigin: 'top left',
                // Показ ведёт проигрыватель, а не читатель: случайный клик мимо
                // шага увёл бы макет в состояние, из которого сценарий не
                // продолжается. Нажатия делает сам проигрыватель, ему `pointer-events` не нужны.
                pointerEvents: 'none',
              }}
            />
            {highlight ? (
              <Box
                data-testid="knowledge-scenario-highlight"
                sx={{
                  position: 'absolute',
                  left: highlight.left * scale - 6,
                  top: highlight.top * scale - 6,
                  width: highlight.width * scale + 12,
                  height: highlight.height * scale + 12,
                  border: '3px solid',
                  borderColor: '#f2622a',
                  borderRadius: 1.5,
                  pointerEvents: 'none',
                  transition: 'all 220ms ease',
                  boxShadow: '0 0 0 9999px rgba(15, 18, 34, 0.28)',
                }}
              >
                <Box
                  sx={{
                    position: 'absolute',
                    left: -13,
                    top: -13,
                    width: 26,
                    height: 26,
                    borderRadius: '50%',
                    bgcolor: '#f2622a',
                    color: '#fff',
                    fontSize: 14,
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {index + 1}
                </Box>
              </Box>
            ) : null}
          </>
        ) : (
          <Stack sx={{ height: '100%', alignItems: 'center', justifyContent: 'center' }} spacing={1}>
            <Typography variant="body2" color="text.secondary">
              Загружаем макет…
            </Typography>
          </Stack>
        )}
      </Box>

      <LinearProgress
        variant="determinate"
        value={((index + 1) / scenario.steps.length) * 100}
        sx={{ height: 3 }}
      />

      <Box sx={{ px: 2, py: 1.5 }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
          <Stack direction="row" spacing={0.5} sx={{ pt: 0.25 }}>
            <IconButton
              size="small"
              onClick={() => setPlaying((value) => !value)}
              aria-label={playing ? 'Пауза' : 'Продолжить'}
              data-testid="knowledge-scenario-pause"
            >
              {playing ? <PauseOutlinedIcon fontSize="small" /> : <PlayArrowOutlinedIcon fontSize="small" />}
            </IconButton>
            <IconButton
              size="small"
              onClick={goNext}
              aria-label="Шаг вперёд"
              data-testid="knowledge-scenario-next"
            >
              <SkipNextOutlinedIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => setIndex(0)}
              aria-label="Сначала"
              data-testid="knowledge-scenario-restart"
            >
              <ReplayOutlinedIcon fontSize="small" />
            </IconButton>
          </Stack>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Шаг {index + 1} из {scenario.steps.length}. {step?.title}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.55 }}>
              {step?.text}
            </Typography>
          </Box>
        </Stack>
        {!playing ? (
          <Button size="small" sx={{ mt: 1 }} onClick={() => setPlaying(true)}>
            Продолжить показ
          </Button>
        ) : null}
      </Box>
    </Paper>
  )
}
