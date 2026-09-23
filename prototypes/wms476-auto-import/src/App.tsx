import { useState } from 'react'
import { HonestSignBackground } from './HonestSignBackground'
import { MarkingImportDialog } from './MarkingImportDialog'
import { demoScenarios, type DemoScenario } from './data'

export default function App() {
  const [scenario, setScenario] = useState<DemoScenario>('partial')
  const [dialogOpen, setDialogOpen] = useState(true)
  const activeHint = demoScenarios.find((s) => s.id === scenario)?.hint

  return (
    <div className="app">
      <div className="proto-topbar" role="region" aria-label="Инструменты макета">
        <div className="proto-demo-control" role="group" aria-label="Демо-сценарий">
          <div className="proto-demo-label">Демо-сценарий</div>
          <div className="proto-demo-segments" role="radiogroup">
            {demoScenarios.map((option) => {
              const isActive = option.id === scenario
              return (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  className={`proto-demo-segment${isActive ? ' is-active' : ''}`}
                  onClick={() => setScenario(option.id)}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
          {activeHint ? <div className="proto-demo-hint">{activeHint}</div> : null}
        </div>
        <div className="proto-banner" role="note" aria-label="Прототип">
          <span className="proto-banner-dot" aria-hidden />
          Интерактивный макет · данные тестовые
        </div>
      </div>
      <HonestSignBackground onOpenImport={() => setDialogOpen(true)} />
      <MarkingImportDialog
        open={dialogOpen}
        scenario={scenario}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  )
}
