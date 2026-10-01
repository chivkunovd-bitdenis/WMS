import { describe, expect, it, vi } from 'vitest'
import {
  describeImportStage,
  extractCatalogJobId,
  extractCatalogJobInitialStage,
  mapBackgroundJobStatus,
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
