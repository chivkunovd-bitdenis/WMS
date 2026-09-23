import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '../index.css'
import '../ui/ui.css'
import { FbsMarkingScene } from '../screens/ff/knowledge/scenes/FbsScenes'

// Отдельная точка входа макета. Она рендерит настоящий FfFbsSupplyWorkspace,
// настоящую тему и существующий подставной API сцены базы знаний; копии экрана нет.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FbsMarkingScene />
  </StrictMode>,
)
