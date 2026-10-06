// @vitest-environment jsdom
// Separate analyst residual contract; original frozen workspace test is untouched.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { OzonExemplarDocuments } from './OzonExemplarDocuments'

type View = {
  version: number; state: string; editable: boolean; errors?: string[] | null
  products: { product_id: number; sku: string; name: string; exemplars: {
    exemplar_id: number; ordinal: number; gtd_required: boolean; rnpt_required: boolean
    gtd?: string | null; rnpt?: string | null; is_gtd_absent?: boolean | null
    is_rnpt_absent?: boolean | null; state: string; errors?: string[] | null
  }[] }[]
}
const view = (number = 'B-CABINET'): View => ({ version: 4, state: 'editable', editable: true,
  products: [{ product_id: 663001, sku: '663001', name: 'Товар Ozon', exemplars: [{
    exemplar_id: 81, ordinal: 1, gtd_required: true, rnpt_required: true,
    gtd: number, rnpt: '', is_gtd_absent: false, is_rnpt_absent: false, state: 'editable', errors: [],
  }] }],
})
const json = (data: View) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })
let host: HTMLDivElement
let root: Root
const settle = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
const render = async (orderId: string) => {
  // Matches the workspace's order-specific React key, including tab unmount.
  await act(async () => root.render(<OzonExemplarDocuments key={`supply:${orderId}`} orderId={orderId} token="test" authHeaders={() => ({})} />))
}
const button = (name: string) => {
  const found = [...host.querySelectorAll<HTMLButtonElement>('button')].find(b => b.getAttribute('aria-label') === name || b.textContent?.trim() === name)
  expect(found, name).toBeTruthy()
  return found!
}
const click = async (name: string) => { await act(async () => button(name).click()); await settle() }
const input = (name: string) => {
  const found = host.querySelector<HTMLInputElement>(`input[aria-label="${name}"]`)
  expect(found, name).toBeTruthy()
  return found!
}
const edit = async (name: string, value: string) => {
  await act(async () => {
    const target = input(name)
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(target, value)
    target.dispatchEvent(new Event('input', { bubbles: true }))
    target.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
const context = ' · SKU 663001 · экземпляр 1'
const save = `Сохранить ГТД / РНПТ${context}`
beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals() })

it.each(['ГТД', 'РНПТ'])('C2: %s exact number → absent → unchecked empty; PUT and refresh', async name => {
  const field = name === 'ГТД' ? 'gtd' : 'rnpt'
  const absent = name === 'ГТД' ? 'is_gtd_absent' : 'is_rnpt_absent'
  let cabinet = view('')
  const puts: Record<string, unknown>[] = []
  const methods: string[] = []
  vi.stubGlobal('fetch', async (_url: unknown, init: RequestInit) => {
    methods.push(init.method!)
    if (init.method === 'PUT') {
      const body = JSON.parse(String(init.body))
      puts.push(body)
      cabinet = { ...cabinet, version: cabinet.version + 1,
        products: [{ ...cabinet.products[0], exemplars: [{ ...cabinet.products[0].exemplars[0],
          gtd: body.gtd, rnpt: body.rnpt, is_gtd_absent: body.is_gtd_absent, is_rnpt_absent: body.is_rnpt_absent,
        }] }] }
    }
    return json(cabinet)
  })
  await render('A')
  await click('ГТД / РНПТ')
  expect(puts).toHaveLength(0)
  await edit(`Номер ${name}${context}`, '000/ABC-09')
  await click(save)
  expect(puts[0]).toEqual({ product_id: 663001, exemplar_id: 81,
    gtd: field === 'gtd' ? '000/ABC-09' : null, rnpt: field === 'rnpt' ? '000/ABC-09' : null,
    is_gtd_absent: false, is_rnpt_absent: false, expected_version: 4 })
  await click('Проверить в Ozon')
  expect(input(`Номер ${name}${context}`).value).toBe('000/ABC-09')
  await act(async () => input(`Номера ${name} нет${context}`).click())
  expect(input(`Номер ${name}${context}`).disabled).toBe(true)
  expect(input(`Номер ${name}${context}`).value).toBe('')
  await click(save)
  expect(puts[1][field]).toBeNull()
  expect(puts[1][absent]).toBe(true)
  expect(puts[1].expected_version).toBe(5)
  await click('Проверить в Ozon')
  expect(input(`Номера ${name} нет${context}`).checked).toBe(true)
  await act(async () => input(`Номера ${name} нет${context}`).click())
  expect(input(`Номер ${name}${context}`).disabled).toBe(false)
  await click(save)
  expect(puts[2][field]).toBeNull()
  expect(puts[2][absent]).toBe(false)
  expect(puts[2].expected_version).toBe(6)
  // A true reopen reads the mocked server, rather than only checking draft state.
  await act(async () => root.render(null))
  await render('A')
  await click('ГТД / РНПТ')
  expect(input(`Номер ${name}${context}`).value).toBe('')
  expect(input(`Номера ${name} нет${context}`).checked).toBe(false)
  expect(puts).toHaveLength(3)
  expect(methods.filter(m => m === 'GET')).toHaveLength(4)
})

it('C11: rejected absent → uncheck → current number, refresh and reopen preserve correction', async () => {
  let cabinet = view('')
  const puts: Record<string, unknown>[] = []
  vi.stubGlobal('fetch', async (_url: unknown, init: RequestInit) => {
    if (init.method === 'PUT') {
      const body = JSON.parse(String(init.body))
      puts.push(body)
      const rejected = puts.length === 1
      cabinet = { ...cabinet, version: cabinet.version + 1, state: rejected ? 'rejected' : 'checking',
        errors: rejected ? ['gtd_invalid'] : [], products: [{ ...cabinet.products[0], exemplars: [{
          ...cabinet.products[0].exemplars[0], gtd: body.gtd, is_gtd_absent: body.is_gtd_absent,
          state: rejected ? 'rejected' : 'checking', errors: rejected ? ['gtd_invalid'] : [],
        }] }] }
    }
    return json(cabinet)
  })
  await render('A'); await click('ГТД / РНПТ')
  await act(async () => input(`Номера ГТД нет${context}`).click())
  await click(save)
  expect(host.textContent).toContain('gtd_invalid')
  await act(async () => input(`Номера ГТД нет${context}`).click())
  await edit(`Номер ГТД${context}`, '000/CORRECTED-09')
  await click(save)
  expect(puts[1]).toEqual({ product_id: 663001, exemplar_id: 81, gtd: '000/CORRECTED-09',
    rnpt: null, is_gtd_absent: false, is_rnpt_absent: false, expected_version: 5 })
  await click('Проверить в Ozon')
  expect(input(`Номер ГТД${context}`).value).toBe('000/CORRECTED-09')
  await act(async () => root.render(null)); await render('A'); await click('ГТД / РНПТ')
  expect(input(`Номер ГТД${context}`).value).toBe('000/CORRECTED-09')
  expect(host.textContent).not.toContain('gtd_invalid')
})

it.each(['order B', 'tab'])('C11: delayed A status after switching %s does not mutate current component', async destination => {
  let resolveA!: (response: Response) => void
  let aReads = 0
  const calls: string[] = []
  vi.stubGlobal('fetch', async (url: string) => {
    calls.push(String(url))
    if (String(url).includes('/A/')) {
      aReads += 1
      if (aReads === 2) return await new Promise<Response>(resolve => { resolveA = resolve })
      return json(view('A-INITIAL'))
    }
    return json(view('B-CABINET'))
  })
  await render('A'); await click('ГТД / РНПТ')
  await act(async () => button('Проверить в Ozon').click())
  expect(resolveA).toBeTypeOf('function')
  if (destination === 'tab') {
    await act(async () => root.render(<button>Другая вкладка</button>))
  }
  await render('B'); await click('ГТД / РНПТ')
  await edit(`Номер ГТД${context}`, 'B-DIRTY-000')
  const before = host.innerHTML
  await act(async () => resolveA(json({ ...view('A-LATE'), state: 'rejected', errors: ['A-LATE-ERROR'] })))
  await settle()
  expect(host.innerHTML).toBe(before)
  expect(input(`Номер ГТД${context}`).value).toBe('B-DIRTY-000')
  expect(host.textContent).not.toContain('A-LATE')
  expect(host.querySelector('[data-testid="ozon-documents-B"]')).toBeTruthy()
  expect(calls).toHaveLength(3)
})

it('C12: malformed JSON on refresh preserves draft and concrete prior rejection', async () => {
  const rejected = view('REJECTED-000')
  rejected.state = 'rejected'
  rejected.errors = ['gtd_invalid']
  rejected.products[0].exemplars[0].errors = ['gtd_invalid']
  let reads = 0
  vi.stubGlobal('fetch', async () => ++reads === 1 ? json(rejected) : new Response('{"broken":'))
  await render('A'); await click('ГТД / РНПТ')
  await edit(`Номер ГТД${context}`, '000/UNSENT-INPUT')
  await click('Проверить в Ozon')
  expect(input(`Номер ГТД${context}`).value).toBe('000/UNSENT-INPUT')
  expect(host.textContent).toContain('gtd_invalid')
  expect(host.querySelector('[role="alert"]')?.textContent).toBeTruthy()
  expect(host.textContent).not.toContain('Принято')
  expect(button(save).disabled).toBe(false)
})

it.each(['missing', 'null'])('C12: %s optional values render safely without acceptance or implicit absent', async optional => {
  const raw = view()
  raw.state = 'unknown'
  raw.products[0].exemplars[0].state = 'unknown'
  const exemplar = raw.products[0].exemplars[0]
  if (optional === 'null') {
    Object.assign(exemplar, { gtd: null, rnpt: null, is_gtd_absent: null, is_rnpt_absent: null, errors: null })
    raw.errors = null
  } else {
    delete exemplar.gtd; delete exemplar.rnpt; delete exemplar.is_gtd_absent; delete exemplar.is_rnpt_absent
    delete exemplar.errors; delete raw.errors
  }
  vi.stubGlobal('fetch', async () => json(raw))
  await render('A'); await click('ГТД / РНПТ')
  expect(input(`Номер ГТД${context}`).value).toBe('')
  expect(input(`Номер РНПТ${context}`).value).toBe('')
  expect(input(`Номера ГТД нет${context}`).checked).toBe(false)
  expect(input(`Номера РНПТ нет${context}`).checked).toBe(false)
  expect(host.textContent).not.toContain('Принято')
  expect(host.textContent).toContain('Результат Ozon пока неизвестен')
})
