// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FboPassDialog, type PassDetails } from './FboPassDialog'

// WMS-686 D7/D8: пропуск — одна запись на отгрузку. ФФ правит до проведения,
// селлер только читает. Тесты идут через настоящее окно и подменённый fetch.

type Call = { url: string; method: string; body: unknown; headers: Record<string, string> }

const REQUEST_ID = 'req-686'
const FILLED: PassDetails = {
  driver_last_name: 'Иванов',
  driver_first_name: 'Пётр',
  driver_phone: '+79990001122',
  car_brand: 'Газель Next',
  car_number: 'А123ВС77',
  cargo_type: 'box',
  cargo_places_count: 12,
  arrival_date: '2026-10-12',
}

let root: Root
let host: HTMLDivElement
let calls: Call[]
let getResponse: () => Response
let putResponse: (body: unknown) => Response | Promise<Response>
let xlsxResponse: () => Response
let downloads: string[]

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  calls = []
  downloads = []
  getResponse = () => json({ pass_details: null, editable: true })
  putResponse = (body) => json({ pass_details: body, editable: true })
  xlsxResponse = () =>
    new Response(new Blob(['xlsx']), {
      status: 200,
      headers: { 'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent('Пропуск.xlsx')}` },
    })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      // Сервер принимает {pass_details: {...}} и отвечает тем же вложением.
      calls.push({ url, method, body, headers: (init?.headers ?? {}) as Record<string, string> })
      if (url.endsWith('/pass.xlsx')) return xlsxResponse()
      if (url.endsWith('/pass') && method === 'PUT') return putResponse(body?.pass_details)
      if (url.endsWith('/pass')) return getResponse()
      return new Response('{}', { status: 404 })
    }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:pass')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push(this.download)
  })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

type RenderOptions = {
  mode?: 'ff' | 'seller'
  marketplace?: string | null
  onClose?: () => void
  onSaved?: (pass: PassDetails | null) => void
}

async function render(options: RenderOptions = {}) {
  await act(async () => {
    root.render(
      <FboPassDialog
        open
        token="tok"
        authHeaders={(t) => ({ Authorization: `Bearer ${t}` })}
        requestId={REQUEST_ID}
        mode={options.mode ?? 'ff'}
        marketplace={options.marketplace ?? 'wb'}
        onClose={options.onClose ?? (() => {})}
        onSaved={options.onSaved}
      />,
    )
  })
}

const field = (key: string) => document.querySelector<HTMLInputElement | HTMLSelectElement>(`[data-testid="fbo-pass-${key}"]`)!
const button = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="fbo-pass-${id}"]`)
const text = (id: string) => document.querySelector(`[data-testid="${id}"]`)?.textContent ?? null

async function type(key: string, value: string) {
  const el = field(key)
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(el, value)
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  })
}

async function click(id: string) {
  await act(async () => button(id)!.click())
}

async function fillRequired() {
  await type('driver_last_name', 'Иванов')
  await type('driver_first_name', 'Пётр')
  await type('car_brand', 'Газель Next')
  await type('car_number', 'А123ВС77')
}

const puts = () => calls.filter((c) => c.method === 'PUT')

describe('FboPassDialog · ФФ', () => {
  it('читает сведения с сервера с токеном и открывает пустую форму, если их ещё нет', async () => {
    await render()
    expect(calls[0].url).toContain(`/operations/marketplace-unload-requests/${REQUEST_ID}/pass`)
    expect(calls[0].headers.Authorization).toBe('Bearer tok')
    for (const key of ['driver_last_name', 'driver_first_name', 'driver_phone', 'car_brand', 'car_number']) {
      expect(field(key).value).toBe('')
      expect((field(key) as HTMLInputElement).readOnly).toBe(false)
    }
    expect(button('save')).not.toBeNull()
    expect(document.querySelector('[data-testid="fbo-pass-empty"]')).toBeNull()
  })

  it('не отправляет форму без обязательных полей и показывает ошибки на местах, введённое остаётся', async () => {
    await render()
    await type('driver_last_name', 'Иванов')
    await click('save')
    expect(puts()).toHaveLength(0)
    expect(document.querySelector('[data-testid="fbo-pass-driver_first_name-field"]')?.textContent).toContain('Заполните поле')
    expect(document.querySelector('[data-testid="fbo-pass-car_brand-field"]')?.textContent).toContain('Заполните поле')
    expect(document.querySelector('[data-testid="fbo-pass-car_number-field"]')?.textContent).toContain('Заполните поле')
    expect(document.querySelector('[data-testid="fbo-pass-driver_phone-field"]')?.textContent).not.toContain('Заполните поле')
    expect(field('driver_last_name').value).toBe('Иванов')
  })

  it('сохраняет: госномер и телефон строками, пустое необязательное — null, затем onSaved и закрытие', async () => {
    const onSaved = vi.fn()
    const onClose = vi.fn()
    await render({ onSaved, onClose })
    await fillRequired()
    await type('car_number', '0123АВ')
    await type('driver_phone', '+7 (999) 000-11-22')
    await type('cargo_places_count', '3')
    await click('save')
    expect(puts()).toHaveLength(1)
    expect(puts()[0].url).toContain(`/operations/marketplace-unload-requests/${REQUEST_ID}/pass`)
    expect(Object.keys(puts()[0].body as object)).toEqual(['pass_details'])
    expect(puts()[0].body).toEqual({ pass_details: {
      driver_last_name: 'Иванов',
      driver_first_name: 'Пётр',
      driver_phone: '+7 (999) 000-11-22',
      car_brand: 'Газель Next',
      car_number: '0123АВ',
      cargo_type: null,
      cargo_places_count: 3,
      arrival_date: null,
    } })
    const sent = (puts()[0].body as { pass_details: Record<string, unknown> }).pass_details
    expect(typeof sent.car_number).toBe('string')
    expect(typeof sent.driver_phone).toBe('string')
    expect(onSaved).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('передаёт тип грузомест и плановую дату приезда', async () => {
    await render()
    await fillRequired()
    await type('cargo_type', 'pallet')
    await type('arrival_date', '2026-10-15')
    await click('save')
    expect(puts()[0].body).toMatchObject({ pass_details: { cargo_type: 'pallet', arrival_date: '2026-10-15' } })
  })

  it('открывает сохранённые значения для правки', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render()
    expect(field('driver_last_name').value).toBe('Иванов')
    expect(field('car_number').value).toBe('А123ВС77')
    expect(field('driver_phone').value).toBe('+79990001122')
    expect(field('cargo_type').value).toBe('box')
    expect(field('cargo_places_count').value).toBe('12')
    expect(field('arrival_date').value).toBe('2026-10-12')
  })

  it('«Закрыть» не сохраняет: запроса на запись нет, окно закрывается после подтверждения', async () => {
    const onClose = vi.fn()
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render({ onClose })
    await type('car_number', 'К999КК99')
    await click('close')
    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(puts()).toHaveLength(0)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('«Закрыть» с несохранённой правкой не закрывает окно, если оператор отказался', async () => {
    const onClose = vi.fn()
    vi.mocked(window.confirm).mockReturnValue(false)
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render({ onClose })
    await type('car_number', 'К999КК99')
    await click('close')
    expect(onClose).not.toHaveBeenCalled()
    expect(field('car_number').value).toBe('К999КК99')
  })

  it('без правок «Закрыть» закрывает окно без вопроса', async () => {
    const onClose = vi.fn()
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render({ onClose })
    await click('close')
    expect(window.confirm).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Ozon: телефон обязателен ещё до запроса, ошибка стоит на поле телефона', async () => {
    await render({ marketplace: 'ozon' })
    await fillRequired()
    await click('save')
    expect(puts()).toHaveLength(0)
    expect(document.querySelector('[data-testid="fbo-pass-driver_phone-field"]')?.textContent).toContain(
      'Для Ozon телефон водителя обязателен.',
    )
    expect(field('car_number').value).toBe('А123ВС77')
  })

  it('WB: телефон необязателен', async () => {
    await render({ marketplace: 'wb' })
    await fillRequired()
    await click('save')
    expect(puts()).toHaveLength(1)
  })

  it('ответ сервера 422 pass_phone_required показывается на поле телефона, введённое не теряется', async () => {
    const onClose = vi.fn()
    putResponse = () => json({ detail: 'pass_phone_required' }, 422)
    await render({ marketplace: null, onClose })
    await fillRequired()
    await click('save')
    expect(puts()).toHaveLength(1)
    expect(document.querySelector('[data-testid="fbo-pass-driver_phone-field"]')?.textContent).toContain(
      'Для Ozon телефон водителя обязателен.',
    )
    expect(document.querySelector('[data-testid="fbo-pass-save-error"]')).toBeNull()
    expect(field('driver_last_name').value).toBe('Иванов')
    expect(field('car_brand').value).toBe('Газель Next')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('прочая ошибка сохранения видна над формой, введённое остаётся, окно открыто', async () => {
    const onClose = vi.fn()
    putResponse = () => json({ detail: 'Сервер недоступен' }, 500)
    await render({ onClose })
    await fillRequired()
    await click('save')
    expect(text('fbo-pass-save-error')).toContain('Сервер недоступен')
    expect(field('car_number').value).toBe('А123ВС77')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('409 pass_not_editable: форма перечитывается и становится только для чтения', async () => {
    const onClose = vi.fn()
    let reads = 0
    getResponse = () => {
      reads += 1
      return reads === 1
        ? json({ pass_details: FILLED, editable: true })
        : json({ pass_details: FILLED, editable: false })
    }
    putResponse = () => json({ detail: 'pass_not_editable' }, 409)
    await render({ onClose })
    await type('car_number', 'К999КК99')
    await click('save')
    expect(text('fbo-pass-save-error')).toBe('Отгрузка проведена или отменена — пропуск менять нельзя.')
    expect(button('save')).toBeNull()
    expect((field('car_number') as HTMLInputElement).readOnly).toBe(true)
    expect((field('car_number') as HTMLInputElement).disabled).toBe(true)
    expect(field('car_number').value).toBe('А123ВС77')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('editable=false: поля только для чтения и кнопки сохранения нет', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: false })
    await render()
    expect(button('save')).toBeNull()
    expect((field('driver_last_name') as HTMLInputElement).readOnly).toBe(true)
    expect(field('driver_last_name').value).toBe('Иванов')
    expect(field('cargo_type').value).toBe('Короб')
    expect(field('arrival_date').value).toBe('12.10.2026')
  })

  it('дважды нажатое «Сохранить» отправляет один запрос', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    putResponse = async (body) => {
      await gate
      return json({ pass_details: body, editable: true })
    }
    await render()
    await fillRequired()
    await act(async () => {
      button('save')!.click()
      button('save')!.click()
    })
    expect(puts()).toHaveLength(1)
    await act(async () => release())
    expect(puts()).toHaveLength(1)
  })
})

describe('FboPassDialog · ответы сервера с указанием поля', () => {
  it('422 проверки схемы подсвечивает поле из loc на русском, окно остаётся открытым', async () => {
    const onClose = vi.fn()
    putResponse = () =>
      json(
        { detail: [{ loc: ['body', 'pass_details', 'car_number'], msg: 'String should have at most 16 characters', type: 'string_too_long' }] },
        422,
      )
    await render({ onClose })
    await fillRequired()
    await click('save')
    expect(document.querySelector('[data-testid="fbo-pass-car_number-field"]')?.textContent).toContain('Проверьте значение')
    expect(document.body.textContent).not.toContain('String should')
    expect(text('fbo-pass-save-error')).toBeNull()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('422 pass_field_required с полем в detail подсвечивает это поле', async () => {
    putResponse = () => json({ detail: { code: 'pass_field_required', field: 'car_brand' } }, 422)
    await render()
    await fillRequired()
    await click('save')
    expect(document.querySelector('[data-testid="fbo-pass-car_brand-field"]')?.textContent).toContain('Заполните поле')
    expect(field('car_brand').value).toBe('Газель Next')
  })

  it('422 pass_field_required без известного поля показывает сообщение над формой', async () => {
    putResponse = () => json({ detail: 'pass_field_required' }, 422)
    await render()
    await fillRequired()
    await click('save')
    expect(text('fbo-pass-save-error')).toBe('Заполните обязательные поля пропуска.')
  })

  it('404 pass_not_filled при скачивании показан по-русски', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: false })
    xlsxResponse = () => json({ detail: 'pass_not_filled' }, 404)
    await render({ mode: 'seller' })
    await click('download')
    expect(text('fbo-pass-download-error')).toBe('Пропуск ещё не внесён.')
  })
})

describe('FboPassDialog · селлер', () => {
  it('видит сохранённые сведения только на чтение, без сохранения', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render({ mode: 'seller' })
    expect(button('save')).toBeNull()
    for (const key of ['driver_last_name', 'driver_first_name', 'driver_phone', 'car_brand', 'car_number']) {
      expect((field(key) as HTMLInputElement).readOnly).toBe(true)
      expect((field(key) as HTMLInputElement).disabled).toBe(true)
    }
    expect(field('car_number').value).toBe('А123ВС77')
    expect(field('driver_phone').value).toBe('+79990001122')
    expect(puts()).toHaveLength(0)
  })

  it('если ФФ не внёс сведения, говорит об этом и не даёт скачать пустой файл', async () => {
    await render({ mode: 'seller' })
    expect(text('fbo-pass-empty')).toBe('Фулфилмент ещё не внёс данные пропуска')
    expect(button('save')).toBeNull()
    expect(button('download')!.disabled).toBe(true)
    expect(field('car_number').value).toBe('')
  })

  it('ошибка загрузки показана в окне, поля остаются закрытыми для записи', async () => {
    getResponse = () => json({ detail: 'not_found' }, 404)
    await render({ mode: 'seller' })
    expect(text('fbo-pass-load-error')).toBe('Документ не найден.')
    expect(button('save')).toBeNull()
  })
})

describe('FboPassDialog · Скачать XLSX', () => {
  it('скачивает файл с токеном и именем из Content-Disposition', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render()
    await click('download')
    const xlsx = calls.find((c) => c.url.endsWith('/pass.xlsx'))!
    expect(xlsx.url).toContain(`/operations/marketplace-unload-requests/${REQUEST_ID}/pass.xlsx`)
    expect(xlsx.headers.Authorization).toBe('Bearer tok')
    expect(downloads).toEqual(['Пропуск.xlsx'])
  })

  it('доступно и селлеру', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: false })
    await render({ mode: 'seller' })
    expect(button('download')!.disabled).toBe(false)
    await click('download')
    expect(downloads).toEqual(['Пропуск.xlsx'])
  })

  it('недоступно у ФФ, пока нет сохранённых сведений', async () => {
    await render()
    expect(button('download')!.disabled).toBe(true)
    await click('download')
    expect(calls.some((c) => c.url.endsWith('/pass.xlsx'))).toBe(false)
  })

  it('недоступно при несохранённой правке: файл строится из сохранённого', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: true })
    await render()
    expect(button('download')!.disabled).toBe(false)
    await type('car_number', 'К999КК99')
    expect(button('download')!.disabled).toBe(true)
  })

  it('ошибка сервера при скачивании показана в окне и не закрывает форму', async () => {
    getResponse = () => json({ pass_details: FILLED, editable: true })
    xlsxResponse = () => json({ detail: 'Нет данных для выгрузки' }, 409)
    await render()
    await click('download')
    expect(text('fbo-pass-download-error')).toContain('Нет данных для выгрузки')
    expect(downloads).toEqual([])
    expect(field('car_number').value).toBe('А123ВС77')
  })
})
