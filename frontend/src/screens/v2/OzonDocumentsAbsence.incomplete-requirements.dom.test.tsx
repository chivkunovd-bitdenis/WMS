// @vitest-environment jsdom
// F3 continuation only: an incomplete/legacy reply must not suppress explicit POST.
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { OzonDocumentsAbsence } from './OzonDocumentsAbsence'

it.each([false, undefined])('requirements_complete=%s cannot suppress explicit absence for a partial snapshot', async complete => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const requests: { method: string; path: string; body: unknown }[] = []
  const path = '/operations/fbs-orders/partial/ozon-exemplar-documents'
  let cabinet = {
    version: 4, state: 'editable', absence_selected: false,
    ...(complete === undefined ? {} : { requirements_complete: complete }),
    products: [{ product_id: 663001, exemplars: [{ exemplar_id: 81,
      gtd_required: false, rnpt_required: false, is_gtd_absent: false, is_rnpt_absent: false }] }],
  }
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const requestedPath = new URL(String(url), 'http://synthetic.test').pathname.replace(/^\/api/, '')
    const method = init?.method ?? 'GET'
    requests.push({ method, path: requestedPath, body: init?.body ? JSON.parse(String(init.body)) : null })
    if (requestedPath !== path && requestedPath !== path + '/absent') throw new Error('Foreign request')
    if (method === 'POST') {
      cabinet = { version: 5, state: 'accepted', absence_selected: true, requirements_complete: true,
        products: [cabinet.products[0], { product_id: 663002, exemplars: [{ exemplar_id: 91,
          gtd_required: true, rnpt_required: false, is_gtd_absent: true, is_rnpt_absent: false }] }] }
    }
    return new Response(JSON.stringify(cabinet), { headers: { 'Content-Type': 'application/json' } })
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<OzonDocumentsAbsence orderIds={['partial']}
      token="synthetic-completeness-contract" authHeaders={() => ({})} onError={vi.fn()} />))
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    const checkbox = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    expect(checkbox).toBeTruthy()
    expect(checkbox.checked).toBe(false)
    expect(checkbox.disabled).toBe(false)
    expect(requests.filter(request => request.method !== 'GET')).toHaveLength(0)
    await act(async () => checkbox.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(requests.filter(request => request.method !== 'GET')).toEqual([
      { method: 'POST', path: path + '/absent', body: { expected_version: 4 } },
    ])
    expect(checkbox.checked).toBe(true)
    expect(host.querySelectorAll('button')).toHaveLength(0)
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
