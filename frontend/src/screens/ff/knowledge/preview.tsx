import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Box, CssBaseline, ThemeProvider, Typography } from '@mui/material'

import { muiTheme } from '../../../mui/theme'
import { FfKnowledgeBaseScreen } from './FfKnowledgeBaseScreen'
import '../../../index.css'

// Превью экрана «База знаний» без сервера и без входа в систему. Открывается по
// адресу /knowledge.html при запущенном `npm run dev`. Раздел статический, поэтому
// в превью он ведёт себя ровно так же, как в портале — это единственный способ
// посмотреть на статьи глазами, не заводя токен.
//
// `?article=<slug>` открывает статью сразу. Нужно для проверки снимками: без этого
// на нужную страницу можно попасть только кликом, а безголовый браузер не кликает.

function initialEntry(): string {
  const slug = new URLSearchParams(window.location.search).get('article')
  return slug ? `/app/ff/knowledge/${slug}` : '/app/ff/knowledge'
}

export function KnowledgePreview() {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box sx={{ p: 3 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          Превью раздела «База знаний». Рамка вокруг — обвязка превью, в портале экран живёт внутри
          общего шелла с левым меню.
        </Typography>
        <MemoryRouter initialEntries={[initialEntry()]}>
          <Routes>
            <Route path="/app/ff/knowledge" element={<FfKnowledgeBaseScreen />} />
            <Route path="/app/ff/knowledge/:slug" element={<FfKnowledgeBaseScreen />} />
          </Routes>
        </MemoryRouter>
      </Box>
    </ThemeProvider>
  )
}

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <KnowledgePreview />
    </StrictMode>,
  )
}
