import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '../index.css'
import '../ui/ui.css'
import { FbsMarkingScene } from '../screens/ff/knowledge/scenes/FbsScenes'
import type { KizReprintRow } from '../utils/kizReprintApi'
import { startAutoKizReprintPrint } from '../utils/kizReprintPrint'

const reprints = new Map<string, KizReprintRow>()

async function mockupReprintKiz(rawKiz: string): Promise<boolean> {
  if (/^WB-/i.test(rawKiz)) return false
  const existing = reprints.get(rawKiz)
  const row: KizReprintRow = existing ?? {
    id: `mock-reprint-${reprints.size + 1}`,
    seller_id: 'demo-seller',
    kiz: rawKiz,
    created_at: new Date().toISOString(),
    print_started_at: null,
  }
  const result = await startAutoKizReprintPrint(
    row,
    `mock-attempt-${row.id}`,
    async () => {},
    {
      claim: async (target) => ({ row: target, claimed: !target.print_started_at }),
      markStarted: async (target) => ({ ...target, print_started_at: new Date().toISOString() }),
      releaseClaim: async (target) => target,
    },
  )
  reprints.set(rawKiz, result.row)
  return true
}

// Отдельная точка входа макета. Она рендерит настоящий FfFbsSupplyWorkspace,
// настоящую тему и существующий подставной API сцены базы знаний; копии экрана нет.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FbsMarkingScene mockupReprintKiz={mockupReprintKiz} />
  </StrictMode>,
)
