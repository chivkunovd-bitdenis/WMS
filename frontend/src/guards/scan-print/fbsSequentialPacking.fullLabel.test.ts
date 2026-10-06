// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('../../utils/czLabelPng', () => ({ renderCzLabelPng: vi.fn(async () => 'full-label-png') }))
vi.mock('../../utils/printPreparedQr', () => ({ dispatchPreparedQrInKiosk: vi.fn(async () => undefined) }))
vi.mock('../../screens/v2/fbsApi', async (original) => ({
  ...(await original<typeof import('../../screens/v2/fbsApi')>()),
  saveFbsDirectKizReprint: vi.fn(),
  claimFbsDirectKizPrint: vi.fn(async () => ({ claimed: true, row: { print_started_at: null } })),
  markFbsDirectKizPrintStarted: vi.fn(async () => ({ print_started_at: 'now' })),
  releaseFbsDirectKizPrintClaim: vi.fn(async () => undefined),
  claimFbsScanAutoPrintReprint: vi.fn(),
  claimFbsScanAutoPrintTarget: vi.fn(async () => ({ claimed: true, started: false })),
  markFbsScanAutoPrintTargetStarted: vi.fn(async () => ({ claimed: false, started: true })),
  releaseFbsScanAutoPrintTargetClaim: vi.fn(async () => undefined),
}))

import { renderCzLabelPng } from '../../utils/czLabelPng'
import { dispatchPreparedQrInKiosk } from '../../utils/printPreparedQr'
import { claimFbsScanAutoPrintReprint, saveFbsDirectKizReprint, type FbsScanAutoPrintResult, type FbsWorkspace } from '../../screens/v2/fbsApi'
import { makePackingScanDeps } from '../../screens/v2/fbsSequentialPacking'

const workspace = { supply: { id: 'supply-1' }, orders: [], boxes: [] } as unknown as FbsWorkspace
const result = { scan_id: 'scan-1', printed_codes: [{ id: 'code-1', cis_code: 'cis', has_label_artifact: true }] } as FbsScanAutoPrintResult
const deps = () => makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(renderCzLabelPng).mockResolvedValue('full-label-png')
})

it.each([true, false])('direct reprint preserves artifact metadata and token (artifact=%s)', async (hasArtifact) => {
  vi.mocked(saveFbsDirectKizReprint).mockResolvedValue({
    id: 'reprint-1', seller_id: 'seller-1', kiz: 'cis', created_at: 'now', print_started_at: null,
    code_id: 'code-1', has_label_artifact: hasArtifact,
  })
  await deps().directReprint('cis')
  expect(renderCzLabelPng).toHaveBeenCalledWith(
    { cis: 'cis', codeId: 'code-1', hasLabelArtifact: hasArtifact }, expect.any(Object), 'token')
  expect(dispatchPreparedQrInKiosk).toHaveBeenCalledTimes(1)
})

it.each([true, false])('exact copies preserve artifact metadata, token and copy count (artifact=%s)', async (hasArtifact) => {
  vi.mocked(claimFbsScanAutoPrintReprint).mockResolvedValue({
    claimed: true, started: false, kiz: 'canonical-cis', code_id: 'code-2', has_label_artifact: hasArtifact,
  })
  await deps().printCopy(result, '58x40', 2)
  expect(renderCzLabelPng).toHaveBeenCalledWith(
    { cis: 'canonical-cis', codeId: 'code-2', hasLabelArtifact: hasArtifact }, expect.any(Object), 'token')
  expect(dispatchPreparedQrInKiosk).toHaveBeenCalledTimes(2)
  expect(vi.mocked(dispatchPreparedQrInKiosk).mock.calls.map(([job]) => job.idempotencyKey))
    .toEqual(['scan-1:copy', 'scan-1:copy:c2'])
})

it('does not print a substitute when the saved artifact cannot be rendered', async () => {
  vi.mocked(claimFbsScanAutoPrintReprint).mockResolvedValue({
    claimed: true, started: false, kiz: 'cis', code_id: 'code-1', has_label_artifact: true,
  })
  vi.mocked(renderCzLabelPng).mockRejectedValueOnce(new Error('Artifact unavailable'))
  await expect(deps().printCopy(result, '58x40', 2)).rejects.toThrow('Artifact unavailable')
  expect(dispatchPreparedQrInKiosk).not.toHaveBeenCalled()
})

it('keeps the ordinary full KIZ and separate order QR print unchanged', async () => {
  await deps().printChz(result, '58x40', 1)
  expect(renderCzLabelPng).toHaveBeenCalledWith(
    { cis: 'cis', codeId: 'code-1', hasLabelArtifact: true }, expect.any(Object), 'token')
  await deps().print(result, 'order-qr-png', '58x40', 'scan-1')
  expect(renderCzLabelPng).toHaveBeenCalledTimes(1)
  expect(dispatchPreparedQrInKiosk).toHaveBeenLastCalledWith(expect.objectContaining({
    imageDataUrl: 'order-qr-png', idempotencyKey: 'scan-1',
  }))
})
