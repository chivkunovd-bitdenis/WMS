import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Link, Stack, ThemeProvider, Typography } from '@mui/material'

import { muiTheme } from '../../../../mui/theme'
import { SCENES, findScene } from './registry'
import { SceneMarkers } from './SceneMarkers'
import '../../../../index.css'

// Точка входа `/kb-scenes.html?scene=<id>` — витрина живых макетов базы знаний.
// Без параметра показывает оглавление, с параметром — один макет во весь экран,
// без единой лишней рамки: из этой страницы снимаются иллюстрации для статей,
// и любая обвязка сверху попала бы на картинку.

function SceneIndex() {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box sx={{ p: 4 }}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Живые макеты базы знаний
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: 720 }}>
          Настоящие экраны портала на выдуманных данных: сервера нет, входа нет. Отсюда снимаются
          иллюстрации для статей, эти же макеты показывает проигрыватель сценария.
        </Typography>
        <Stack spacing={1}>
          {SCENES.map((scene) => (
            <Link key={scene.id} href={`?scene=${scene.id}`} variant="body1">
              {scene.title} <Typography component="span" variant="caption" color="text.secondary">({scene.id})</Typography>
            </Link>
          ))}
        </Stack>
      </Box>
    </ThemeProvider>
  )
}

const params = new URLSearchParams(window.location.search)
const scene = findScene(params.get('scene'))
// Селекторы для нумерованных рамок: `&mark=<селектор>|<селектор>`. Разделитель —
// вертикальная черта, потому что в CSS-селекторах запятая значит «или» и
// разрезать по ней было бы нельзя.
const marks = (params.get('mark') ?? '')
  .split('|')
  .map((item) => item.trim())
  .filter(Boolean)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {scene ? (
      <Suspense fallback={null}>
        <scene.component />
        <SceneMarkers selectors={marks} />
      </Suspense>
    ) : (
      <SceneIndex />
    )}
  </StrictMode>,
)
