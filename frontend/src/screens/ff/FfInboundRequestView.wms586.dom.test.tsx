// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { byId, chooseAct, harness, makeDetail } from '../../test-contracts/inbound684586Harness'

let h: ReturnType<typeof harness>
beforeEach(() => { h = harness() })
afterEach(async () => h.dispose())

describe('WMS-586 act file actions', () => {
  for (const fmt of ['xlsx', 'pdf'] as const) {
    it(`downloads ${fmt} for current document with server MIME and UTF8 name without printing`, async () => {
      await h.render()
      byId('ff-inbound-acceptance-act')
      byId('ff-inbound-print-waybill')
      await chooseAct(fmt)
      expect(h.fileCalls).toEqual([expect.stringContaining(`/A/acceptance-act.${fmt}`)])
      expect(h.downloads).toHaveLength(1)
      expect(h.downloads[0]!.name).toBe(`Акт приёмки №000684 от 28.09.2026.${fmt}`)
      expect(h.downloads[0]!.blob.type).toBe(fmt === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      expect(document.querySelectorAll('iframe')).toHaveLength(0)
      expect(h.fetcher.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true)
    })
    for (const mode of [404, 409, 500, 'network', 'blob'] as const) {
      it(`${fmt} recovers from ${mode}, never downloads an error and can navigate to B`, async () => {
        await h.render()
        h.fileMode = mode
        await chooseAct(fmt)
        expect(h.downloads).toHaveLength(0)
        expect(h.fileCalls).toHaveLength(1)
        const error = typeof mode === 'number' ? `act failure ${mode}` : mode === 'network' ? 'act network failure' : 'act blob read failure'
        expect(document.body.textContent).toContain(error)
        expect((byId('ff-inbound-acceptance-act') as HTMLButtonElement).disabled).toBe(false)
        h.fileMode = 'ok'
        await chooseAct(fmt)
        expect(h.fileCalls).toHaveLength(2)
        expect(h.downloads).toHaveLength(1)
        h.current = { ...makeDetail('B'), display_number: '№009999', created_at: '2026-09-20T00:00:00Z' }
        await h.render()
        await chooseAct(fmt)
        expect(h.fileCalls.at(-1)).toContain(`/B/acceptance-act.${fmt}`)
        expect(h.downloads.at(-1)!.name).toBe(`Акт приёмки №009999 от 20.09.2026.${fmt}`)
        expect(document.querySelectorAll('iframe')).toHaveLength(0)
      })
    }
  }
  it('retains status and nonempty-line visibility without discrepancy-act requests', async () => {
    for (const status of ['draft', 'submitted', 'receiving', 'sorting', 'verified', 'done', 'posted']) {
      h.current = { ...makeDetail(), status }
      await h.remount()
      const closed = ['sorting', 'verified', 'done', 'posted'].includes(status)
      expect(Boolean(document.querySelector('[data-testid="ff-inbound-acceptance-act"]'))).toBe(closed)
      if (!closed) expect(document.body.textContent).not.toMatch(/Акт приёмки|PDF|Excel/)
      expect(document.querySelector('[data-testid="ff-inbound-discrepancy-acts"]')).toBeNull()
    }
    h.current.lines = []
    await h.remount()
    expect(document.querySelector('[data-testid="ff-inbound-acceptance-act"]')).toBeNull()
    expect(h.fetcher.mock.calls.every(([url]) => !String(url).includes('discrepancy-acts'))).toBe(true)
  })
})
