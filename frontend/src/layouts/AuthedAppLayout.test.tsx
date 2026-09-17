import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthedAppLayout } from './AuthedAppLayout'

// Колокольчик уведомлений в шапке читает токен из localStorage при рендере;
// в node его нет — подставляется пустое хранилище.
beforeEach(() => {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// WMS-433/R23: у выключенного тенанта (и без профиля вовсе) в каркасе портала
// ФФ нет ни кнопки, ни окна помощника — элементов нет в разметке, а не
// «спрятаны». Включённое состояние здесь не рендерится: панель живёт в
// портале на document.body, которого у статического рендера нет; оно
// проверяется в браузере (C25).

function render(assistantProfile: { assistant_enabled?: boolean } | null | undefined) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/app/ff/warehouse-map']}>
      <AuthedAppLayout
        portal="ff"
        meRole="fulfillment_admin"
        ffPermissions={null}
        userLabel="admin@example.com"
        onLogout={() => {}}
        assistantProfile={assistantProfile}
      >
        <div data-testid="content">содержимое</div>
      </AuthedAppLayout>
    </MemoryRouter>,
  )
}

describe('AuthedAppLayout: помощник по тенантам (R23)', () => {
  it('выключенный тенант — в разметке нет ни кнопки, ни окна помощника', () => {
    const markup = render({ assistant_enabled: false })
    expect(markup).toContain('data-testid="app-frame"')
    expect(markup).toContain('data-testid="content"')
    expect(markup).not.toContain('assistant-toggle')
    expect(markup).not.toContain('assistant-window')
    expect(markup).not.toContain('Помощник')
  })

  it('профиль без признака или без профиля (превью, сцены) — помощника тоже нет', () => {
    expect(render({})).not.toContain('Помощник')
    expect(render(null)).not.toContain('Помощник')
    expect(render(undefined)).not.toContain('Помощник')
  })
})
