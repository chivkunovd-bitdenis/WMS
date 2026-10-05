import { execFileSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'

const WMS_666_BASE = '0f1460b02'

export function wms666ScopeViolations(paths: string[]): string[] {
  return paths.filter((path) => {
    if (!path) return false
    if (path === 'docs/KANONICHESKIY_BACKLOG.md' || path === 'docs/requirements/WMS-666.md') return false
    if (path === 'docs/reviews/contract-corrections/WMS-666.json') return false
    if (path.startsWith('frontend/src/screens/v2/')) return false
    if (path === 'frontend/src/components/LabelSizeSelect.tsx' || path === 'frontend/src/utils/labelSize.ts') return false
    if (path.startsWith('frontend/src/') && /\.test\.[cm]?[jt]sx?$/.test(path)) return false
    if (path.startsWith('backend/tests/') || path.startsWith('frontend/tests/')) return false
    return true
  })
}

describe('WMS-666 C13: narrow UI-only change boundary', () => {
  it('rejects migrations, backend entities, stock logic and guard registry changes', () => {
    expect(wms666ScopeViolations([
      'backend/alembic/versions/2026_new_mode.py',
      'backend/app/models/fbs_packing_group.py',
      'backend/app/services/inventory_service.py',
      'guards/MANIFEST.json',
    ])).toEqual([
      'backend/alembic/versions/2026_new_mode.py',
      'backend/app/models/fbs_packing_group.py',
      'backend/app/services/inventory_service.py',
      'guards/MANIFEST.json',
    ])
    expect(wms666ScopeViolations([
      'frontend/src/screens/v2/FfFbsSupplyAssembly.tsx',
      'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
      'docs/requirements/WMS-666.md',
      'docs/reviews/contract-corrections/WMS-666.json',
    ])).toEqual([])
    expect(wms666ScopeViolations([
      'docs/reviews/contract-corrections/WMS-667.json',
      'docs/reviews/contract-corrections/WMS-666.md',
    ])).toEqual([
      'docs/reviews/contract-corrections/WMS-667.json',
      'docs/reviews/contract-corrections/WMS-666.md',
    ])
  })

  it('keeps the actual task diff inside the approved packing UI/test/document boundary', () => {
    const changed = execFileSync('git', ['diff', '--name-only', WMS_666_BASE, '--'], {
      cwd: new URL('../../../..', import.meta.url), encoding: 'utf8',
    }).trim().split('\n')
    expect(wms666ScopeViolations(changed)).toEqual([])
  })
})
