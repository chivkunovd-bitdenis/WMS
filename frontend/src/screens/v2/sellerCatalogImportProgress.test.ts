import { describe, expect, it, vi } from 'vitest'
import {
  describeImportStage,
  extractCatalogJobId,
  extractCatalogJobInitialStage,
  mapBackgroundJobStatus,
  observeImportJob,
  parseCatalogSyncResponse,
  pollImportJob,
} from './sellerCatalogImportProgress'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('mapBackgroundJobStatus — WMS-615 R14: honest state, not fake success', () => {
  it('reads the backend-mapped state values from CatalogSyncJobOut (queued/running/succeeded/failed)', () => {
    expect(mapBackgroundJobStatus('queued')).toBe('queued')
    expect(mapBackgroundJobStatus('running')).toBe('running')
    expect(mapBackgroundJobStatus('succeeded')).toBe('succeeded')
    expect(mapBackgroundJobStatus('failed')).toBe('failed')
  })

  it('also reads the raw BackgroundJob status for callers that get the legacy field', () => {
    expect(mapBackgroundJobStatus('pending')).toBe('queued')
    expect(mapBackgroundJobStatus('done')).toBe('succeeded')
  })

  it('does not call an unknown code a success — stays running so the selection modal is not opened on a half-ready catalog', () => {
    expect(mapBackgroundJobStatus('cancelled')).toBe('running')
    expect(mapBackgroundJobStatus(null)).toBe('running')
    expect(mapBackgroundJobStatus(undefined)).toBe('running')
  })
})

describe('describeImportStage — compact one-liner, no narrative', () => {
  it('names each stage with a single sentence', () => {
    expect(describeImportStage('queued')).toMatch(/очеред/i)
    expect(describeImportStage('running')).toMatch(/загружа/i)
    expect(describeImportStage('succeeded')).toMatch(/загружен/i)
    expect(describeImportStage('failed')).toMatch(/не удал/i)
  })
})

describe('extractCatalogJobId — WMS-615 R13 contract', () => {
  it('reads catalog_job.id from the backend CatalogSyncJobOut shape', () => {
    expect(
      extractCatalogJobId({
        catalog_job: { id: 'job-123', marketplace: 'wildberries', state: 'queued' },
      }),
    ).toBe('job-123')
  })

  it('trims accidental whitespace from the id', () => {
    expect(
      extractCatalogJobId({
        catalog_job: { id: '  job-123  ', marketplace: 'wildberries', state: 'queued' },
      }),
    ).toBe('job-123')
  })

  it('also accepts a flat catalog_job_id as a legacy fallback (safer than ignoring an id)', () => {
    expect(extractCatalogJobId({ catalog_job_id: 'legacy-job' })).toBe('legacy-job')
  })

  it('returns null when neither shape is present — fallback to the legacy synchronous flow', () => {
    expect(extractCatalogJobId({ validation_ok: true })).toBeNull()
  })

  it('returns null for non-string ids, instead of coercing to a dangerous value', () => {
    expect(extractCatalogJobId({ catalog_job: { id: 42 } })).toBeNull()
    expect(extractCatalogJobId(null)).toBeNull()
    expect(extractCatalogJobId('string body')).toBeNull()
  })
})

describe('extractCatalogJobInitialStage — WMS-615 R13', () => {
  it('reads the stage from catalog_job.state so the UI reflects queued vs running from the first paint', () => {
    expect(
      extractCatalogJobInitialStage({
        catalog_job: { id: 'j', marketplace: 'wildberries', state: 'running' },
      }),
    ).toBe('running')
    expect(
      extractCatalogJobInitialStage({
        catalog_job: { id: 'j', marketplace: 'wildberries', state: 'succeeded' },
      }),
    ).toBe('succeeded')
  })

  it('falls back to queued when the state field is missing (no state → assume just queued)', () => {
    expect(extractCatalogJobInitialStage({ catalog_job: { id: 'j' } })).toBe('queued')
    expect(extractCatalogJobInitialStage({})).toBe('queued')
  })
})

describe('pollImportJob — one round-trip, honest outcome', () => {
  it('prefers the backend-mapped `state` field when present (new BackgroundJobOut)', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { state: 'running', status: 'running' }))
    const result = await pollImportJob(fetchImpl, 'job-1', {})
    expect(result).toEqual({ outcome: 'in_progress', stage: 'running' })
  })

  it('also reads the legacy `status` field when `state` is missing (fallback)', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { status: 'done' }))
    expect(await pollImportJob(fetchImpl, 'job-1', {})).toEqual({ outcome: 'succeeded' })
  })

  it('reports succeeded when backend says succeeded — this is the only state that opens the modal', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { state: 'succeeded' }))
    expect(await pollImportJob(fetchImpl, 'job-1', {})).toEqual({ outcome: 'succeeded' })
  })

  it('surfaces the backend error_message on failed import so the seller can retry with context', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { state: 'failed', error_message: 'ozon_rate_limited' }),
    )
    expect(await pollImportJob(fetchImpl, 'job-1', {})).toEqual({
      outcome: 'failed',
      message: 'ozon_rate_limited',
    })
  })

  it('falls back to the stage description when the backend omits error_message for failed', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { state: 'failed' }))
    const result = await pollImportJob(fetchImpl, 'job-1', {})
    expect(result).toEqual({ outcome: 'failed', message: describeImportStage('failed') })
  })

  it('reports a failure when the poll request itself returns non-200, instead of a fake success', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))
    const result = await pollImportJob(fetchImpl, 'job-1', {})
    expect(result.outcome).toBe('failed')
  })

  it('stays in progress for an unknown code', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { state: 'retrying' }))
    const result = await pollImportJob(fetchImpl, 'job-1', {})
    expect(result).toEqual({ outcome: 'in_progress', stage: 'running' })
  })
})

describe('parseCatalogSyncResponse — Astra P1: 202 is a start, not a completion', () => {
  it('reads a plain CatalogSyncJobOut body with id/state and returns the initial stage', () => {
    expect(
      parseCatalogSyncResponse({ id: 'job-1', marketplace: 'wildberries', state: 'running' }),
    ).toEqual({ jobId: 'job-1', stage: 'running' })
  })

  it('defaults to "queued" when the state field is missing (common for a brand-new job)', () => {
    expect(parseCatalogSyncResponse({ id: 'job-1' })).toEqual({ jobId: 'job-1', stage: 'queued' })
  })

  it('returns null when the id is missing — caller must not confuse this with a job', () => {
    expect(parseCatalogSyncResponse({ marketplace: 'wildberries' })).toBeNull()
    expect(parseCatalogSyncResponse({ id: '' })).toBeNull()
    expect(parseCatalogSyncResponse(null)).toBeNull()
    expect(parseCatalogSyncResponse('string body')).toBeNull()
  })

  it('trims whitespace off the id so URL interpolation never gets a space-padded id', () => {
    expect(parseCatalogSyncResponse({ id: '  job-2  ', state: 'queued' })).toEqual({
      jobId: 'job-2',
      stage: 'queued',
    })
  })
})

describe('observeImportJob — Astra P1: reload only on real success', () => {
  function fetchSequence(responses: Response[]) {
    let i = 0
    return vi.fn(async () => {
      const next = responses[Math.min(i, responses.length - 1)]
      i += 1
      return next
    })
  }

  it('invokes onSucceeded exactly once when the job reaches "done" after one or more polls', async () => {
    const onStage = vi.fn()
    const onSucceeded = vi.fn()
    const onFailed = vi.fn()
    const fetchImpl = fetchSequence([
      jsonResponse(200, { state: 'running' }),
      jsonResponse(200, { state: 'succeeded' }),
    ])

    await observeImportJob(
      fetchImpl,
      'job-1',
      {},
      { onStage, onSucceeded, onFailed },
      new AbortController().signal,
      0, // zero-delay polling for the test
    )

    expect(onStage).toHaveBeenCalledWith('running')
    expect(onSucceeded).toHaveBeenCalledTimes(1)
    expect(onFailed).not.toHaveBeenCalled()
  })

  it('invokes onFailed with the backend-provided error_message on failed state', async () => {
    const onStage = vi.fn()
    const onSucceeded = vi.fn()
    const onFailed = vi.fn()
    const fetchImpl = fetchSequence([
      jsonResponse(200, { state: 'failed', error_message: 'ozon_rate_limited' }),
    ])

    await observeImportJob(
      fetchImpl,
      'job-1',
      {},
      { onStage, onSucceeded, onFailed },
      new AbortController().signal,
      0,
    )

    expect(onFailed).toHaveBeenCalledWith('ozon_rate_limited')
    expect(onSucceeded).not.toHaveBeenCalled()
  })

  it('invokes onFailed instead of onSucceeded when the poll request itself errors — never a fake success', async () => {
    const onStage = vi.fn()
    const onSucceeded = vi.fn()
    const onFailed = vi.fn()
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })

    await observeImportJob(
      fetchImpl,
      'job-1',
      {},
      { onStage, onSucceeded, onFailed },
      new AbortController().signal,
      0,
    )

    expect(onFailed).toHaveBeenCalledWith('Failed to fetch')
    expect(onSucceeded).not.toHaveBeenCalled()
  })

  it('respects AbortSignal: no callbacks after the signal fires mid-polling', async () => {
    const onStage = vi.fn()
    const onSucceeded = vi.fn()
    const onFailed = vi.fn()
    const controller = new AbortController()
    const fetchImpl = vi.fn(async () => {
      controller.abort() // simulate "the component unmounted between poll ticks"
      return jsonResponse(200, { state: 'running' })
    })

    await observeImportJob(
      fetchImpl,
      'job-1',
      {},
      { onStage, onSucceeded, onFailed },
      controller.signal,
      0,
    )

    expect(onStage).not.toHaveBeenCalled()
    expect(onSucceeded).not.toHaveBeenCalled()
    expect(onFailed).not.toHaveBeenCalled()
  })
})
