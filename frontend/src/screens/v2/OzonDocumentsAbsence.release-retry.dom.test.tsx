// @vitest-environment jsdom
// R11/C16: preserve one checkbox and saved intent while an explicit retry stays reachable.
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { OzonDocumentsAbsence } from './OzonDocumentsAbsence'

const posting = '/operations/fbs-orders/retry-order/ozon-exemplar-documents'
function saved(state: string, version: number, selected: boolean) {
  return { state, version, absence_selected: selected, requirements_complete: true,
    errors: state === 'rejected' ? ['fixture_rate_limit'] : [],
    products: [{ exemplars: [{ gtd_required: true, rnpt_required: false,
      is_gtd_absent: selected, is_rnpt_absent: false }] }] }
}

it('definite rejection keeps checked intent and next explicit checkbox click submits current version once', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const posts: unknown[] = []
  let cabinet = saved('editable', 0, false)
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const path = new URL(String(url), 'http://synthetic.test').pathname.replace(/^\/api/, '')
    if (path !== posting && path !== posting + '/absent') throw new Error('Foreign scope')
    if (init?.method === 'POST') {
      posts.push(JSON.parse(String(init.body)))
      cabinet = posts.length === 1 ? saved('rejected', 1, true) : saved('accepted', 2, true)
    }
    return new Response(JSON.stringify(cabinet), { headers: { 'Content-Type': 'application/json' } })
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  const errors = vi.fn()
  const mount = async () => {
    await act(async () => root.render(<OzonDocumentsAbsence orderIds={['retry-order']}
      token="synthetic-retry" authHeaders={() => ({})} onError={errors} />))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  }
  try {
    await mount()
    let checkbox = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    expect(checkbox.checked).toBe(false)
    expect(posts).toEqual([])
    await act(async () => checkbox.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(posts).toEqual([{ expected_version: 0 }])
    expect(checkbox.checked).toBe(true)
    expect(errors).toHaveBeenCalledWith('fixture_rate_limit')
    await act(async () => root.render(null))
    await mount()
    checkbox = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    expect(checkbox.checked).toBe(true)
    expect(posts).toEqual([{ expected_version: 0 }])
    // No separate button/window or mass absent=false: retry through the same
    // actual control, preserving checked intent on reopening and after click.
    expect(host.querySelectorAll('input[type="checkbox"]')).toHaveLength(1)
    expect(host.querySelectorAll('button')).toHaveLength(0)
    await act(async () => checkbox.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(posts).toEqual([{ expected_version: 0 }, { expected_version: 1 }])
    expect(checkbox.checked).toBe(true)
    expect(host.textContent).toContain('Без ГТД и РНПТ')
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})

it.each(['unknown', 'checking', 'accepted'])('%s intent reopening and reverse click never POST again', async state => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const requests: string[] = []
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const path = new URL(String(url), 'http://synthetic.test').pathname.replace(/^\/api/, '')
    if (path !== posting && path !== posting + '/absent') throw new Error('Foreign scope')
    requests.push(init?.method ?? 'GET')
    return new Response(JSON.stringify(saved(state, 7, true)), { headers: { 'Content-Type': 'application/json' } })
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<OzonDocumentsAbsence orderIds={['retry-order']}
      token="synthetic-retry" authHeaders={() => ({})} onError={vi.fn()} />))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    const checkbox = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    expect(checkbox.checked).toBe(true)
    await act(async () => checkbox.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(checkbox.checked).toBe(true)
    expect(requests.every(method => method === 'GET')).toBe(true)
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
