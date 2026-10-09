// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DeadlinePill } from '../../components/fbs/FbsChips'
import { flush, headers, installNetwork, json, mount, order, page, refresh, row, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'

const NOW = Date.parse(SERVER_NOW)
const iso = (ms: number) => new Date(ms).toISOString()
let dispose: (() => Promise<void>) | undefined
let hidden = false
const hiddenDescriptor = Object.getOwnPropertyDescriptor(document, 'hidden')
beforeEach(() => {
  vi.stubEnv('TZ', 'America/Los_Angeles')
  vi.useFakeTimers()
  vi.setSystemTime('2030-01-01T00:00:00.000Z')
  hidden = false
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
})
afterEach(async () => {
  await dispose?.(); dispose = undefined
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks()
  if (hiddenDescriptor) Object.defineProperty(document, 'hidden', hiddenDescriptor)
  else delete (document as unknown as Record<string, unknown>).hidden
})

async function open(item: FbsWorklistOrder, state = { now: SERVER_NOW, fail: false }) {
  dispose = await mount(installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return state.fail
      ? json({ detail: 'Test read failed' }, 500)
      : json({ ...page([item]), server_now: state.now })
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: state.now })
    throw new Error(`Unexpected request: ${url}`)
  }))
}
function pill() {
  const element = row().querySelector('[data-testid="fbs-deadline-pill"]')
  expect(element, 'the order age remains visible').toBeTruthy()
  return element as HTMLElement
}
async function advance(ms: number) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }); await flush() }

describe('WMS-717 real order age with a server clock', () => {
  it('C1 starts at 2 ч 05 мин from marketplace creation despite client calendar skew', async () => {
    const item = order(); item.created_at_wb = iso(NOW - 125 * 60_000)
    await open(item)
    expect(pill().textContent).toBe('2 ч 05 мин')
  })

  it('C1 displays 125 ч 07 мин without wrapping elapsed hours', async () => {
    const item = order(); item.created_at_wb = iso(NOW - (125 * 60 + 7) * 60_000)
    await open(item)
    expect(pill().textContent).toBe('125 ч 07 мин')
  })

  it.each([59, 1439, 7199])('C1 carries elapsed minute %i without resetting days or the 120-hour limit', async (minutes) => {
    const item = order(); item.created_at_wb = iso(NOW - minutes * 60_000)
    await open(item)
    const age = (value: number) => `${Math.floor(value / 60)} ч ${String(value % 60).padStart(2, '0')} мин`
    expect(pill().textContent).toBe(age(minutes))
    // Prevent polling from reusing an intentionally stationary server fixture.
    hidden = true
    await advance(60_000)
    expect(pill().textContent).toBe(age(minutes + 1))
  })

  it.each([[49, 'Success'], [48, 'Info'], [13, 'Info'], [12, 'Warning'], [0, 'Error'], [-1, 'Error']] as const)(
    'C2 retains WB urgency at %i hours left while keeping numeric age', async (hours, color) => {
      const item = order(); item.deadline_at = iso(NOW + hours * 3_600_000)
      const before = structuredClone(item)
      await open(item)
      expect(pill().className).toContain(`MuiChip-color${color}`)
      expect(pill().textContent).toBe('2 ч 05 мин')
      expect((row().querySelector('input[type="checkbox"]') as HTMLInputElement).disabled).toBe(false)
      expect(item).toEqual(before)
    },
  )

  it('C2 crosses the WB deadline without replacing numeric age or blocking selection', async () => {
    const item = order(); item.deadline_at = iso(NOW + 30_000)
    await open(item); hidden = true
    await advance(30_000)
    expect(pill().className).toContain('MuiChip-colorError')
    expect(pill().textContent).toBe('2 ч 05 мин')
    expect((row().querySelector('input[type="checkbox"]') as HTMLInputElement).disabled).toBe(false)
  })

  it.each([1, -1])('C3 shows Ozon processing age with deadline offset %i hours', async (offset) => {
    const item = order(); item.marketplace = 'ozon'
    item.created_at_wb = iso(NOW - 192 * 60_000)
    item.deadline_at = iso(NOW + offset * 3_600_000)
    await open(item)
    expect(pill().textContent).toBe('3 ч 12 мин')
    if (offset < 0) expect(pill().className).toContain('MuiChip-colorDefault')
    expect((row().querySelector('input[type="checkbox"]') as HTMLInputElement).disabled).toBe(false)
    hidden = true; await advance(60_000)
    expect(pill().textContent).toBe('3 ч 13 мин')
  })

  it.each([
    ['absent', undefined, SERVER_NOW, '—'],
    ['null', null, SERVER_NOW, '—'],
    ['invalid', 'not-a-date', SERVER_NOW, '—'],
    ['future', iso(NOW + 60_000), SERVER_NOW, '0 ч 00 мин'],
    ['no deadline', iso(NOW - 125 * 60_000), null, '2 ч 05 мин'],
    ['invalid deadline', iso(NOW - 125 * 60_000), 'not-a-date', '2 ч 05 мин'],
  ])('C4 handles %s creation/deadline without inventing an age', async (_case, start, deadline, expected) => {
    const item = order()
    if (start === undefined) delete (item as Partial<FbsWorklistOrder>).created_at_wb
    else item.created_at_wb = start as string
    item.deadline_at = deadline as string
    await open(item)
    expect(pill().textContent).toBe(expected)
    if (deadline === null || deadline === 'not-a-date') expect(pill().className).toContain('MuiChip-colorDefault')
    expect(document.body.textContent).not.toContain('NaN')
    item.created_at_wb = iso(NOW - 125 * 60_000); item.deadline_at = iso(NOW + 3_600_000)
    await refresh()
    expect(pill().textContent).toBe('2 ч 05 мин')
  })

  it('C4 retains dash for cancelled orders', async () => {
    const item = order(); item.status = 'cancelled'
    await open(item); await tab('Отменённые')
    expect(pill().textContent).toBe('—')
  })

  it('C5 advances offline, catches up after hidden time and survives errors, refresh and reopening', async () => {
    const item = order()
    const state = { now: SERVER_NOW, fail: false }
    await open(item, state)
    hidden = true
    await advance(60_000)
    expect(pill().textContent).toBe('2 ч 06 мин')
    await advance(5 * 60_000)
    state.now = iso(NOW + 6 * 60_000); state.fail = true; hidden = false
    await act(async () => document.dispatchEvent(new Event('visibilitychange'))); await flush()
    expect(pill().textContent).toBe('2 ч 11 мин')
    expect(document.querySelector('[role="alert"]')).toBeTruthy()
    state.fail = false; await refresh()
    expect(pill().textContent).toBe('2 ч 11 мин')
    await dispose?.(); dispose = undefined
    await open(item, state)
    expect(pill().textContent).toBe('2 ч 11 мин')
  })

  it('C6 preserves the shared deadline-only call used by the supply workspace', async () => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    const host = document.createElement('div'); document.body.append(host)
    const root = createRoot(host)
    dispose = async () => { await act(async () => root.unmount()); host.remove() }
    await act(async () => root.render(<DeadlinePill deadlineAt={iso(NOW + 49 * 3_600_000)} serverNow={SERVER_NOW} />))
    const element = host.querySelector('[data-testid="fbs-deadline-pill"]')!
    expect(element.textContent).toBe('49 ч')
    expect(element.className).toContain('MuiChip-colorSuccess')
  })

  it('C6 preserves the supply shipment date column while orders show elapsed age', async () => {
    await open(order())
    expect(pill().textContent).toBe('2 ч 05 мин')
    for (const label of ['В работе', 'В доставке', 'Завершённые']) {
      await tab(label)
      expect(headers()).toContain('Дата отгрузки')
      expect(headers()).not.toContain('Отгрузить до')
    }
  })
})
