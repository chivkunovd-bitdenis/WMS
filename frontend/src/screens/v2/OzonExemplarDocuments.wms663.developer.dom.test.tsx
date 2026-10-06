// @vitest-environment jsdom
// Supplemental developer probe; the frozen full-workspace contract remains unchanged.
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { OzonExemplarDocuments } from './OzonExemplarDocuments'

it('developer probe: contextual Save preserves input, error and current version', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const oldFetch = globalThis.fetch
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  const requests: unknown[] = []
  const view = {
    version: 4, state: 'editable', products: [{ product_id: 663001, sku: '663001', name: 'Товар',
      exemplars: [{ exemplar_id: 81, ordinal: 1, gtd_required: true, rnpt_required: false,
        gtd: '', rnpt: '', is_gtd_absent: false, is_rnpt_absent: false, state: 'editable', errors: [] }] }],
  }
  globalThis.fetch = async (_input, init) => {
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body))
      requests.push(body)
      return new Response(JSON.stringify({ ...view, version: 5, state: 'rejected',
        products: [{ ...view.products[0], exemplars: [{ ...view.products[0].exemplars[0],
          gtd: body.gtd, state: 'rejected', errors: ['gtd_invalid'] }] }] }))
    }
    return new Response(JSON.stringify(view))
  }
  const settle = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) }) }
  try {
    await act(async () => root.render(<><button disabled data-testid="shipment-save">Сохранить</button>
      <OzonExemplarDocuments orderId="order" token="test" authHeaders={() => ({})} /></>))
    await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === 'ГТД / РНПТ')!.click())
    await settle()
    const target = host.querySelector<HTMLInputElement>('input[aria-label="Номер ГТД · SKU 663001 · экземпляр 1"]')!
    const edit = (value: string) => act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(target, value)
      target.dispatchEvent(new Event('input', { bubbles: true }))
      target.dispatchEvent(new Event('change', { bubbles: true }))
    })
    edit('001/ABC-09')
    const saves = [...host.querySelectorAll('button')].filter(b => b.textContent === 'Сохранить')
    console.log('Unscoped frozen helper selects shipment Save:', saves[0].dataset.testid, 'disabled:', saves[0].disabled)
    const save = host.querySelector<HTMLButtonElement>('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')!
    expect(save.disabled).toBe(false)
    await act(async () => save.click())
    await settle()
    expect(requests[0]).toEqual({ product_id: 663001, exemplar_id: 81, gtd: '001/ABC-09',
      rnpt: null, is_gtd_absent: false, is_rnpt_absent: false, expected_version: 4 })
    expect(host.textContent).toContain('gtd_invalid')
    expect(target.value).toBe('001/ABC-09')
    edit('001/ABC-10')
    await act(async () => save.click())
    await settle()
    expect(requests[1]).toEqual({ product_id: 663001, exemplar_id: 81, gtd: '001/ABC-10',
      rnpt: null, is_gtd_absent: false, is_rnpt_absent: false, expected_version: 5 })
  } finally {
    act(() => root.unmount())
    host.remove()
    globalThis.fetch = oldFetch
  }
})
