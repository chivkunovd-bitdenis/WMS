// @vitest-environment jsdom
// Third concrete review defect only; original owner contracts stay untouched.
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { OzonDocumentsAbsence } from './OzonDocumentsAbsence'

it('one required posting selects the supply checkbox; a known no-documents posting gets no absence write', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const requests: { method: string; order: string; body: unknown }[] = []
  const cabinet = {
    A: { version: 4, state: 'editable', absence_selected: false, products: [{
      product_id: 663001, exemplars: [{ exemplar_id: 81,
        gtd_required: true, rnpt_required: false, is_gtd_absent: false, is_rnpt_absent: false }],
    }] },
    B: { version: 7, state: 'editable', absence_selected: false, products: [{
      product_id: 663002, exemplars: [{ exemplar_id: 91,
        gtd_required: false, rnpt_required: false, is_gtd_absent: false, is_rnpt_absent: false }],
    }] },
  }
  // B has a complete real snapshot, not an empty/unknown reply. No requirements
  // is not a fabricated saved-absence choice and must not trigger preparation.
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const match = /\/fbs-orders\/(A|B)\/ozon-exemplar-documents(\/absent)?$/.exec(String(url))
    if (!match) throw new Error(`Unexpected transport path: ${url}`)
    const order = match[1] as 'A' | 'B'
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : null
    requests.push({ method, order, body })
    if (method === 'POST') {
      expect(match[2]).toBe('/absent')
      if (order === 'A') {
        cabinet.A.version = 5
        cabinet.A.state = 'accepted'
        cabinet.A.absence_selected = true
        cabinet.A.products[0].exemplars[0].is_gtd_absent = true
      }
    }
    return new Response(JSON.stringify(cabinet[order]), { headers: { 'Content-Type': 'application/json' } })
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  const errors = vi.fn()
  const render = async () => {
    await act(async () => {
      root.render(<OzonDocumentsAbsence orderIds={['A', 'B']} token="synthetic-owner-contract"
        authHeaders={() => ({})} onError={errors} />)
    })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  }
  const choice = () => {
    const inputs = host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')
    expect(inputs).toHaveLength(1)
    expect(host.querySelector('label')?.textContent).toBe('Без ГТД и РНПТ')
    return inputs[0]!
  }
  const writes = () => requests.filter(request => request.method !== 'GET')
  try {
    await render()
    expect(choice().checked).toBe(false)
    expect(choice().disabled).toBe(false)
    expect(writes()).toHaveLength(0)
    await act(async () => choice().click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(writes()).toEqual([{ method: 'POST', order: 'A', body: { expected_version: 4 } }])
    expect(choice().checked).toBe(true)
    expect(choice().getAttribute('data-indeterminate')).toBe('false')
    expect(host.querySelectorAll('button')).toHaveLength(0)
    await act(async () => root.render(null))
    await render()
    expect(choice().checked).toBe(true)
    expect(writes()).toEqual([{ method: 'POST', order: 'A', body: { expected_version: 4 } }])
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
