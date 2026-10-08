import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import recoveryHistory from '../../../tests/fixtures/wms666AcceptedRecoveryHistory.json'

const WMS_666_CONTRACT = '0e078418bcb7ee45fa654b0d829e5de0ec80ebb0'
const WMS_666_HISTORY_CHECKOUT_CHANGE = {
  commit: '720307d280439e815057ee4fdd78b72134149a39',
  path: '.github/workflows/ci.yml',
  beforeBlob: '621ee62065c67ae66d756b25057d56e780bb411d',
  afterBlob: 'bbec58a4b781913e7792a6718158a9fc4b806c90',
}
const WMS_666_DOCUMENT_HISTORY = [
  {
    commit: '1d34b77874e1b1396d8bdd216bd0053a4a308440',
    changedPaths: ['docs/KANONICHESKIY_BACKLOG.md', 'docs/requirements/WMS-517.md',
      'docs/requirements/WMS-666.md', 'docs/reviews/wms666-replacement-acceptance-20261006.md'],
    files: [{ path: 'docs/requirements/WMS-517.md',
      beforeBlob: 'aca08cc54fce43c7e0987664827e5ec193fff6d5',
      afterBlob: '89a8fb5fbbfe2a823477dbc495fe7b0e78abd6d7' }],
  },
  {
    commit: 'c5d9255e5d912e13398c883961d0c476ee5a1938',
    changedPaths: ['docs/reviews/wms663-666-frontend-rollback-scope-20261006.md'],
    files: [{ path: 'docs/reviews/wms663-666-frontend-rollback-scope-20261006.md',
      beforeBlob: '664aa8ea5e279c04f9b6219a8440142fd7bc142a',
      afterBlob: 'c68d9ac10b045020e651544017d84e574dab5e7a' }],
  },
  {
    commit: '8ec0fcd6c7625a4351e6e9a04dfe80f055ac398a',
    changedPaths: ['docs/reviews/wms663-666-frontend-rollback-scope-20261006.md',
      'docs/reviews/wms666-earlier-frontend-scope-20261006.md'],
    files: [{ path: 'docs/reviews/wms663-666-frontend-rollback-scope-20261006.md',
      beforeBlob: 'c68d9ac10b045020e651544017d84e574dab5e7a',
      afterBlob: '664aa8ea5e279c04f9b6219a8440142fd7bc142a' },
    { path: 'docs/reviews/wms666-earlier-frontend-scope-20261006.md', beforeBlob: null,
      afterBlob: '9dda566e064373fce1e817ce11c8fd5c1b345165' }],
  },
]
const WMS_666_RC7_HISTORY = [
  {
    commit: '603720d6dc4751e6f29593207e4ea7b1219d0509',
    changedPaths: [
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
    ],
    files: [
      {
        path: 'backend/app/services/fbs_print_asset_service.py',
        beforeEntry: '100644 blob 878cdce1c8750b2bce274048c6a6afb9919fcb10\tbackend/app/services/fbs_print_asset_service.py',
        afterEntry: '100644 blob d49ee1ae8ef20c5814001c90046b6c849835dc9b\tbackend/app/services/fbs_print_asset_service.py',
      },
      {
        path: 'backend/app/services/fbs_supply_service.py',
        beforeEntry: '100644 blob 96860f53021e7442d300c1f8e1330ef57181d76d\tbackend/app/services/fbs_supply_service.py',
        afterEntry: '100644 blob 3c5b84686e7ac860257297d60785dc9d867d4614\tbackend/app/services/fbs_supply_service.py',
      },
    ],
  },
  {
    commit: '70c2c2c6cf16aee81292042a9dde6161fb5384e2',
    changedPaths: ['backend/app/services/fbs_print_asset_service.py'],
    files: [
      {
        path: 'backend/app/services/fbs_print_asset_service.py',
        beforeEntry: '100644 blob d49ee1ae8ef20c5814001c90046b6c849835dc9b\tbackend/app/services/fbs_print_asset_service.py',
        afterEntry: '100644 blob 2281ff64b91f1f743c44df746ce16e9e319f8ced\tbackend/app/services/fbs_print_asset_service.py',
      },
    ],
  },
  {
    commit: '739a63343fc38d2a3441d9b613b4652c7f0380e0',
    changedPaths: [
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
    ],
    files: [
      {
        path: 'backend/app/services/fbs_print_asset_service.py',
        beforeEntry: '100644 blob 2281ff64b91f1f743c44df746ce16e9e319f8ced\tbackend/app/services/fbs_print_asset_service.py',
        afterEntry: '100644 blob b6b44641b76dc8516a25614414c8fc4ee5d5e65c\tbackend/app/services/fbs_print_asset_service.py',
      },
      {
        path: 'backend/app/services/fbs_supply_service.py',
        beforeEntry: '100644 blob 3c5b84686e7ac860257297d60785dc9d867d4614\tbackend/app/services/fbs_supply_service.py',
        afterEntry: '100644 blob 80cf3f2ecf333fcb1e60c079bb00b2f8b26856aa\tbackend/app/services/fbs_supply_service.py',
      },
    ],
  },
]
const WMS_517_FINANCIAL_FIXTURE_HISTORY = {
  commit: '30de00e5f70c3fde354036702aa921ebaab7fd65',
  changedPaths: [
    'backend/tests/test_wb_catalog_schedule.py',
    'backend/tests/test_wms666_packing_sticker_request.py',
    'backend/tests/test_withdrawal_ledger.py',
    'docs/requirements/WMS-666.md',
    'docs/requirements/WMS-689.md',
    'guards/PROCESS_CONTRACTS.json',
  ],
  files: [
    {
      path: 'backend/tests/test_wb_catalog_schedule.py',
      beforeEntry: '100644 blob b22007910e910a102105982e3531d36a2930c344\tbackend/tests/test_wb_catalog_schedule.py',
      afterEntry: '100644 blob cce26bacce70ae86c65c1febfd23f915df58958a\tbackend/tests/test_wb_catalog_schedule.py',
    },
    {
      path: 'backend/tests/test_wms666_packing_sticker_request.py',
      beforeEntry: '100644 blob fa797ead6126fa239cdfa39a306a08a02287b222\tbackend/tests/test_wms666_packing_sticker_request.py',
      afterEntry: '100644 blob 7b7bd5bfc36050cc697dd84500255a7dc04a26b7\tbackend/tests/test_wms666_packing_sticker_request.py',
    },
    {
      path: 'backend/tests/test_withdrawal_ledger.py',
      beforeEntry: '100644 blob ac14733de2530eb4e0f4ae285cab806d5eec3755\tbackend/tests/test_withdrawal_ledger.py',
      afterEntry: '100644 blob f20342fe34f3c7d05b96960028087dd2968d0960\tbackend/tests/test_withdrawal_ledger.py',
    },
    {
      path: 'docs/requirements/WMS-666.md',
      beforeEntry: '100644 blob 57577022c980e9efbee01d06cf9e14330eb2a871\tdocs/requirements/WMS-666.md',
      afterEntry: '100644 blob 4a79c1858e870f0e497a17a2a100fc828e23cc63\tdocs/requirements/WMS-666.md',
    },
    {
      path: 'docs/requirements/WMS-689.md',
      beforeEntry: '100644 blob 6a4243254c80844602b57170f8ed716f4f22f2f2\tdocs/requirements/WMS-689.md',
      afterEntry: '100644 blob 0a0a9a8744f1892e9cb330324f8f88674c691592\tdocs/requirements/WMS-689.md',
    },
    {
      path: 'guards/PROCESS_CONTRACTS.json',
      beforeEntry: '100644 blob 4f80f9ea11d7e51c1bd6a64e7e99a4d362472125\tguards/PROCESS_CONTRACTS.json',
      afterEntry: '100644 blob 6daab1ccf12d79d2e462bcb651c55692fbd06151\tguards/PROCESS_CONTRACTS.json',
    },
  ],
}
const WMS_517_FIXTURE_CONTRACT = {
  commit: '3c3c1b69c15cb611c7d256971f9c85ebb9d1ae60',
  subject: 'WMS-517: align recovery tests with finance archive',
  changedPaths: [
    'backend/tests/test_withdrawal_ledger.py',
    'backend/tests/test_wms517_raw_integer_price.py',
    'backend/tests/test_wms517_raw_numeric_price.py',
    'backend/tests/test_wms517_sales_contract.py',
    'backend/tests/test_wms517_sales_partial_decimal_regressions.py',
    'backend/tests/test_wms537_draft_supply_stickers.py',
    'docs/requirements/WMS-517.md',
    'docs/requirements/WMS-537.md',
    'guards/PROCESS_CONTRACTS.json',
  ],
}
const WMS_666_PROOF_FILES = new Set([
  '.github/workflows/wms666-browser-proof.yml',
  'scripts/ci/wms666-browser-proof.mjs',
  'frontend/tests-e2e/wms666-proof/index.html',
  'frontend/tests-e2e/wms666-proof/main.tsx',
  'frontend/tests-e2e/wms666-proof/vite.config.ts',
  'docs/reviews/wms666-priority-progress-20261006.md',
  'docs/reviews/wms666-replacement-acceptance-20261006.md',
  'docs/reviews/wms666-task-scope-correction-20261006.md',
  // These two exact shared proofs were written by the WMS-666 integration merge.
  'docs/reviews/priority-five-progress-20261006.md',
  'docs/reviews/priority-five-source-map-20261006.json',
])

export function wms666AcceptedHistoryChange(
  cwd: string | URL,
  commit: string,
  path: string,
  recoveryReads = new Map<string, boolean>(),
  recoveryEntries = recoveryHistory.entries,
): boolean {
  const accepted = WMS_666_HISTORY_CHECKOUT_CHANGE
  const git = (...args: string[]) => execFileSync('git', args, { cwd, encoding: 'utf8' }).trim()
  const recovery = recoveryEntries.find((entry) => entry.commit === commit)
  const recoveredFile = recovery?.files.find((entry) => entry.path === path)
  if (recovery && recoveredFile) {
    // Exact independently reviewed history only. No future change of these paths
    // is permitted, even with identical content or the same task number.
    if (!recoveryReads.has(commit)) {
      const changed = git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', commit)
        .split('\n').filter(Boolean).sort()
      const paths = recovery.files.map((file) => file.path)
      const entries = (ref: string) => git('ls-tree', '--full-tree', ref, '--', ...paths)
        .split('\n').filter(Boolean).sort()
      const expected = (side: 'beforeEntry' | 'afterEntry') => recovery.files
        .map((file) => file[side]).filter(Boolean).sort()
      const isRc7History = WMS_666_RC7_HISTORY.some((entry) => entry.commit === commit)
      // RC7's exception is limited to commits whose every changed path has an
      // exact before/after tree entry. Other legacy recovery records intentionally
      // describe only the task-owned paths in broader commits.
      const completeRc7FileList = !isRc7History
        || JSON.stringify([...paths].sort()) === JSON.stringify(changed)
      recoveryReads.set(commit, completeRc7FileList
        && JSON.stringify(changed) === JSON.stringify([...recovery.changedPaths].sort())
        && JSON.stringify(entries(`${commit}^`)) === JSON.stringify(expected('beforeEntry'))
        && JSON.stringify(entries(commit)) === JSON.stringify(expected('afterEntry')))
    }
    return recoveryReads.get(commit) === true
  }
  const documents = WMS_666_DOCUMENT_HISTORY.find((entry) => entry.commit === commit)
  const file = documents?.files.find((entry) => entry.path === path)
  if (documents && file) {
    // Immutable doc-only history, not permission for any future edit of these paths.
    const changed = git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', commit)
      .split('\n').filter(Boolean).sort()
    if (JSON.stringify(changed) !== JSON.stringify([...documents.changedPaths].sort())) return false
    const treeEntry = (sha: string) => git('ls-tree', '--full-tree', sha, '--', path)
    return treeEntry(`${commit}^`) === (file.beforeBlob === null ? '' : `100644 blob ${file.beforeBlob}\t${path}`)
      && treeEntry(commit) === `100644 blob ${file.afterBlob}\t${path}`
  }
  if (commit !== accepted.commit || path !== accepted.path) return false
  // Only the immutable four-line fetch-depth fix is already accepted.
  // Future commits and pending edits of this path receive no exemption.
  return git('rev-parse', `${commit}^:${path}`) === accepted.beforeBlob
    && git('rev-parse', `${commit}:${path}`) === accepted.afterBlob
}

export function wms666TaskChangedPaths(
  cwd: string | URL,
  contract = WMS_666_CONTRACT,
): string[] {
  const git = (...args: string[]) => execFileSync('git', args, { cwd, encoding: 'utf8' })
  // Missing history must fail, rather than quietly produce an empty task diff.
  git('merge-base', '--is-ancestor', contract, 'HEAD')
  const head = git('rev-parse', 'HEAD').trim()
  const history = git('log', '--ancestry-path', '--format=%H%x09%P%x09%s', `${contract}..${head}`)
  const root = git('show', '-s', '--format=%H%x09%P%x09%s', contract)
  const paths = new Set<string>()
  // Reuse only immutable commit verification within this single history walk.
  const recoveryReads = new Map<string, boolean>()
  for (const line of (root + history).trim().split('\n')) {
    const [commit, parents, subject] = line.split('\t')
    // Attribution is by task lineage and primary task number, never allowed paths.
    if (!/^WMS-666(?:\s+WMS-\d+)*:/.test(subject ?? '')) continue
    const merge = parents.trim().split(/\s+/).length > 1
    const changed = git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', '-z',
      ...(merge ? ['--cc'] : ['--root']), commit)
    // A merge's combined diff catches its own resolutions, not imported task trees.
    for (const path of changed.split('\0')) {
      if (path && !wms666AcceptedHistoryChange(cwd, commit, path, recoveryReads)) paths.add(path)
    }
  }
  // Include unstaged, staged and new files. Uncommitted changes cannot hide a defect.
  for (const changed of [
    git('diff', '--name-only', '-z', head, '--'),
    git('diff', '--cached', '--name-only', '-z', head, '--'),
    git('ls-files', '--others', '--exclude-standard', '-z'),
  ]) {
    for (const path of changed.split('\0')) if (path) paths.add(path)
  }
  expect(git('rev-parse', 'HEAD').trim()).toBe(head)
  return [...paths].sort()
}

export function wms666ScopeViolations(paths: string[]): string[] {
  return paths.filter((path) => {
    if (!path) return false
    if (path === 'docs/KANONICHESKIY_BACKLOG.md' || path === 'docs/requirements/WMS-666.md') return false
    // Only this task's machine-readable correction record belongs to its scope.
    if (path === 'docs/reviews/contract-corrections/WMS-666.json') return false
    if (WMS_666_PROOF_FILES.has(path) || path.startsWith('docs/evidence/WMS-666/')) return false
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
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
      'guards/MANIFEST.json',
    ])).toEqual([
      'backend/alembic/versions/2026_new_mode.py',
      'backend/app/models/fbs_packing_group.py',
      'backend/app/services/inventory_service.py',
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
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
    const changed = wms666TaskChangedPaths(new URL('../../../..', import.meta.url))
    expect(wms666ScopeViolations(changed)).toEqual([])
  })

  it('accepts exact task proofs and rejects adjacent proof and correction namespaces', () => {
    expect(wms666ScopeViolations([...WMS_666_PROOF_FILES, 'docs/evidence/WMS-666/result.json'])).toEqual([])
    const adjacent = [
      '.github/workflows/wms663-remote-proof.yml',
      'scripts/ci/wms667-proof.mjs',
      'frontend/tests-e2e/wms667-proof/main.tsx',
      'docs/evidence/WMS-667/result.json',
      'docs/reviews/contract-corrections/WMS-667.json',
    ]
    expect(wms666ScopeViolations(adjacent)).toEqual(adjacent)
  })

  it('reads advancing task history: foreign backend passes, new task backend or guards fail', () => {
    const repo = fixtureRepository()
    try {
      repo.write('backend/app/services/ozon_documents.py', 'foreign task\n')
      repo.commit('WMS-663: independent document action')
      repo.write('frontend/src/screens/v2/packing.ts', 'approved task UI\n')
      const accepted = repo.commit('WMS-666: approved packing UI')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([])
      const forbidden = [
        'backend/app/services/ozon_documents.py',
        'backend/alembic/versions/2026_new_mode.py',
        'backend/app/models/fbs_packing_group.py',
        'backend/app/services/inventory_service.py',
        'guards/MANIFEST.json',
        'docs/reviews/contract-corrections/WMS-667.json',
      ]
      for (const path of forbidden) {
        repo.git('reset', '--hard', accepted)
        repo.write(path, 'new forbidden task change\n')
        repo.commit('WMS-666: new task delta')
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      }
      repo.git('reset', '--hard', accepted)
      const path = 'backend/app/services/inventory_service.py'
      repo.write(path, 'uncommitted forbidden change\n')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.git('add', path)
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.git('reset', '--hard', accepted)
      repo.write(path, 'existing foreign inventory\n')
      repo.commit('WMS-663: independent existing inventory fixture')
      repo.write(path, 'forbidden staged inventory\n')
      repo.git('add', path)
      repo.write(path, 'existing foreign inventory\n')
      expect(repo.git('diff', '--name-only', 'HEAD', '--', path)).toBe('')
      expect(repo.git('diff', '--cached', '--name-only', '--', path)).toBe(path)
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
    } finally {
      repo.close()
    }
  })

  it('checks task merge resolutions while ignoring an imported foreign backend tree', () => {
    const repo = fixtureRepository()
    try {
      repo.git('checkout', '-b', 'foreign')
      repo.write('backend/app/services/foreign.py', 'independent backend\n')
      repo.commit('WMS-663: foreign backend')
      repo.git('checkout', '-b', 'task', repo.contract)
      repo.write('frontend/src/screens/v2/packing.ts', 'own UI\n')
      repo.commit('WMS-666: own UI')
      repo.git('merge', '--no-ff', '--no-commit', 'foreign')
      repo.write('backend/app/services/inventory_service.py', 'forbidden merge resolution\n')
      repo.commit('WMS-666: resolve integration')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([
        'backend/app/services/inventory_service.py',
      ])
    } finally {
      repo.close()
    }
  })

  it('rejects a new task workflow edit and pending CI changes independently', () => {
    const repo = fixtureRepository()
    const path = '.github/workflows/ci.yml'
    expect(wms666ScopeViolations([path])).toEqual([path])
    try {
      repo.write(path, 'new untracked workflow\n')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.write(path, 'accepted independent CI\n')
      const baseline = repo.commit('WMS-652: independent workflow')
      repo.write(path, 'skip mandatory checks\n')
      repo.commit('WMS-666: new forbidden workflow edit')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.git('reset', '--hard', baseline)
      repo.write(path, 'unstaged forbidden workflow\n')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.git('add', path)
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      repo.write(path, 'accepted independent CI\n')
      expect(repo.git('diff', '--name-only', 'HEAD', '--', path)).toBe('')
      expect(repo.git('diff', '--cached', '--name-only', 'HEAD', '--', path)).toBe(path)
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
    } finally {
      repo.close()
    }
  })

  it('accepts only reviewed recovery commit/path/blob triples and rejects adjacent paths', () => {
    const cwd = new URL('../../../..', import.meta.url)
    expect(recoveryHistory.productCommit).toBe('d420f8db1e7d69212ad2ea4529a02044689363b0')
    expect(recoveryHistory.reviewCommit).toBe('154cdb1ff3e84ed4e592d883688c7df560579015')
    for (const entry of recoveryHistory.entries) {
      for (const file of entry.files) {
        expect(wms666AcceptedHistoryChange(cwd, entry.commit, file.path)).toBe(true)
        expect(wms666AcceptedHistoryChange(cwd, WMS_666_CONTRACT, file.path)).toBe(false)
      }
      expect(wms666AcceptedHistoryChange(cwd, entry.commit, 'guards/MANIFEST.json')).toBe(false)
      expect(wms666AcceptedHistoryChange(cwd, entry.commit, 'backend/app/services/inventory_service.py')).toBe(false)
    }
  })

  it('accepts only the exact immutable history checkout delta', () => {
    const cwd = new URL('../../../..', import.meta.url)
    const accepted = WMS_666_HISTORY_CHECKOUT_CHANGE
    expect(wms666AcceptedHistoryChange(cwd, accepted.commit, accepted.path)).toBe(true)
    expect(wms666AcceptedHistoryChange(cwd, '5ddd09aac4df17e7ecdefaf1625462c05f8039ce', accepted.path)).toBe(false)
    expect(wms666AcceptedHistoryChange(cwd, accepted.commit, 'guards/MANIFEST.json')).toBe(false)
  })

  it('fails an accepted history lookup if its immutable source is missing', () => {
    const repo = fixtureRepository()
    try {
      const accepted = WMS_666_HISTORY_CHECKOUT_CHANGE
      expect(() => wms666AcceptedHistoryChange(repo.cwd, accepted.commit, accepted.path)).toThrow()
    } finally {
      repo.close()
    }
  })

  it('accepts only exact doc-only historical commits and keeps their paths forbidden generally', () => {
    const cwd = new URL('../../../..', import.meta.url)
    for (const entry of WMS_666_DOCUMENT_HISTORY) {
      for (const file of entry.files) {
        expect(wms666AcceptedHistoryChange(cwd, entry.commit, file.path)).toBe(true)
        expect(wms666AcceptedHistoryChange(cwd, WMS_666_CONTRACT, file.path)).toBe(false)
        expect(wms666AcceptedHistoryChange(cwd, entry.commit, `${file.path}.new`)).toBe(false)
        expect(wms666ScopeViolations([file.path])).toEqual([file.path])
      }
      expect(wms666AcceptedHistoryChange(cwd, entry.commit, 'backend/app/services/inventory_service.py')).toBe(false)
      expect(wms666AcceptedHistoryChange(cwd, entry.commit, 'guards/MANIFEST.json')).toBe(false)
    }
  })

  it('records only the five exact RC7 service blob pairs and each commit full path list', () => {
    const cwd = new URL('../../../..', import.meta.url)
    for (const expected of WMS_666_RC7_HISTORY) {
      const actual = recoveryHistory.entries.find((entry) => entry.commit === expected.commit)
      expect(actual && {
        commit: actual.commit,
        changedPaths: actual.changedPaths,
        files: actual.files,
      }).toEqual(expected)
      for (const file of expected.files) {
        expect(wms666AcceptedHistoryChange(cwd, expected.commit, file.path)).toBe(true)
      }
      expect(wms666AcceptedHistoryChange(cwd, expected.commit, 'backend/app/services/inventory_service.py'))
        .toBe(false)
    }

    // WMS-517 and WMS-689 are not yet recorded as resolved, so their mixed
    // commit cannot be admitted through this WMS-666-only history exception.
    expect(wms666AcceptedHistoryChange(
      cwd,
      '30de00e5f70c3fde354036702aa921ebaab7fd65',
      'backend/app/services/fbs_print_asset_service.py',
    )).toBe(false)
    expect(wms666ScopeViolations([
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
    ])).toEqual([
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
    ])
  })

  it('rejects RC7 history when commit, path, blob, mode, or complete path list differs', () => {
    const cwd = new URL('../../../..', import.meta.url)
    const expected = WMS_666_RC7_HISTORY[0]
    const exactFixture = JSON.parse(JSON.stringify(expected)) as (typeof recoveryHistory.entries)[number]

    expect(wms666AcceptedHistoryChange(
      cwd,
      expected.commit,
      expected.files[0].path,
      new Map(),
      [exactFixture],
    )).toBe(true)

    expect(wms666AcceptedHistoryChange(cwd, 'ad10b48adb04a9bdb3e1197a9dd11a65050a32a5', expected.files[0].path))
      .toBe(false)
    expect(wms666AcceptedHistoryChange(cwd, expected.commit, `${expected.files[0].path}.renamed`)).toBe(false)

    const clone = () => JSON.parse(JSON.stringify(exactFixture)) as typeof exactFixture
    const wrongBlob = clone()
    wrongBlob.files[0].afterEntry = wrongBlob.files[0].afterEntry.replace(
      'd49ee1ae8ef20c5814001c90046b6c849835dc9b',
      '0000000000000000000000000000000000000000',
    )
    const wrongMode = clone()
    wrongMode.files[0].beforeEntry = wrongMode.files[0].beforeEntry.replace('100644 blob', '100755 blob')
    const wrongPathList = clone()
    wrongPathList.changedPaths = [...wrongPathList.changedPaths, 'backend/app/services/unlisted.py']
    const incompleteFileList = clone()
    incompleteFileList.files = [incompleteFileList.files[0]]

    for (const corrupted of [wrongBlob, wrongMode, wrongPathList, incompleteFileList]) {
      expect(wms666AcceptedHistoryChange(
        cwd,
        expected.commit,
        expected.files[0].path,
        new Map(),
        [corrupted],
      )).toBe(false)
    }
  })

  it('accepts only the exact WMS-517 financial fixture correction history', () => {
    const cwd = new URL('../../../..', import.meta.url)
    const git = (...args: string[]) => execFileSync('git', args, { cwd, encoding: 'utf8' }).trim()
    const correction = WMS_517_FINANCIAL_FIXTURE_HISTORY
    const actual = recoveryHistory.entries.find((entry) => entry.commit === correction.commit)

    expect(git('rev-parse', `${correction.commit}^`)).toBe('f2f9b9b835e7e11cabcce1c693e283072417bac2')
    expect(execFileSync('git', [
      'merge-base', '--is-ancestor', WMS_517_FIXTURE_CONTRACT.commit, correction.commit,
    ], { cwd, encoding: 'utf8' })).toBe('')
    expect(git('show', '-s', '--format=%s', WMS_517_FIXTURE_CONTRACT.commit))
      .toBe(WMS_517_FIXTURE_CONTRACT.subject)
    expect(git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', WMS_517_FIXTURE_CONTRACT.commit)
      .split('\n').filter(Boolean)).toEqual(WMS_517_FIXTURE_CONTRACT.changedPaths)

    expect(actual && {
      commit: actual.commit,
      changedPaths: actual.changedPaths,
      files: actual.files,
    }).toEqual(correction)

    for (const file of correction.files) {
      expect(wms666AcceptedHistoryChange(cwd, correction.commit, file.path)).toBe(true)
    }
    expect(wms666AcceptedHistoryChange(
      cwd,
      correction.commit,
      'backend/tests/test_wms517_sales_contract.py',
    )).toBe(false)
    expect(wms666AcceptedHistoryChange(
      cwd,
      WMS_517_FIXTURE_CONTRACT.commit,
      'backend/tests/test_withdrawal_ledger.py',
    )).toBe(false)
  })

  it('rejects adjacent WMS-517 correction commits and mutated exact-history entries', () => {
    const cwd = new URL('../../../..', import.meta.url)
    const expected = WMS_517_FINANCIAL_FIXTURE_HISTORY
    const check = (
      commit: string,
      path: string,
      entry: typeof expected,
    ) => wms666AcceptedHistoryChange(cwd, commit, path, new Map(), [entry])
    const clone = () => JSON.parse(JSON.stringify(expected)) as typeof expected

    expect(check(
      '28671d78ce431a6fc32c357a6eee34f769ce6192',
      'backend/tests/test_withdrawal_ledger.py',
      { ...expected, commit: '28671d78ce431a6fc32c357a6eee34f769ce6192' },
    )).toBe(false)
    expect(check(
      '86df6d2a8122c7e43ad14e6aa40d8303f3eb4fa3',
      'backend/tests/test_withdrawal_ledger.py',
      { ...expected, commit: '86df6d2a8122c7e43ad14e6aa40d8303f3eb4fa3' },
    )).toBe(false)
    expect(wms666AcceptedHistoryChange(
      cwd,
      expected.commit,
      'backend/tests/test_withdrawal_orchestration.py',
      new Map(),
      [expected],
    )).toBe(false)

    const wrongBlob = clone()
    wrongBlob.files[2].afterEntry = wrongBlob.files[2].afterEntry.replace(
      'f20342fe34f3c7d05b96960028087dd2968d0960',
      '0000000000000000000000000000000000000000',
    )
    const wrongMode = clone()
    wrongMode.files[2].beforeEntry = wrongMode.files[2].beforeEntry.replace('100644 blob', '100755 blob')
    const wrongPath = clone()
    wrongPath.files[2].path = 'backend/tests/test_withdrawal_orchestration.py'
    const extraCommitPath = clone()
    extraCommitPath.changedPaths = [...extraCommitPath.changedPaths, 'backend/tests/unlisted.py']
    const missingFile = clone()
    missingFile.files = missingFile.files.slice(1)

    const corruptedEntries = [
      ['after blob', wrongBlob],
      ['mode', wrongMode],
      ['path', wrongPath],
      ['complete commit path list', extraCommitPath],
      ['all changed files have exact records', missingFile],
    ] as const
    for (const [label, corrupted] of corruptedEntries) {
      expect(check(expected.commit, 'backend/tests/test_withdrawal_ledger.py', corrupted), label).toBe(false)
    }

    const repo = fixtureRepository()
    try {
      repo.write('backend/tests/test_withdrawal_ledger.py', 'new nearby correction\n')
      const future = repo.commit('WMS-666: future WMS-517 fixture edit')
      expect(wms666AcceptedHistoryChange(
        repo.cwd,
        future,
        'backend/tests/test_withdrawal_ledger.py',
      )).toBe(false)
    } finally {
      repo.close()
    }
  })

  it('rejects future WMS-517 path commits and dirty, staged, or untracked changes', () => {
    const repo = fixtureRepository()
    const protectedPaths = [
      'backend/app/services/fbs_print_asset_service.py',
      'backend/app/services/fbs_supply_service.py',
      'docs/requirements/WMS-689.md',
      'guards/PROCESS_CONTRACTS.json',
    ]
    try {
      for (const path of protectedPaths) {
        repo.git('reset', '--hard', repo.contract)
        repo.write(path, 'foreign baseline\n')
        const baseline = repo.commit('WMS-663: independent baseline')
        repo.write(path, 'future WMS-517 path change\n')
        repo.commit('WMS-666: nearby fixture path change')
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])

        repo.git('reset', '--hard', baseline)
        repo.write(path, 'unstaged correction path change\n')
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
        repo.git('add', path)
        repo.write(path, 'foreign baseline\n')
        expect(repo.git('diff', '--name-only', 'HEAD', '--', path)).toBe('')
        expect(repo.git('diff', '--cached', '--name-only', '--', path)).toBe(path)
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      }

      repo.git('reset', '--hard', repo.contract)
      const untracked = 'backend/app/services/fbs_print_asset_service_neighbor.py'
      repo.write(untracked, 'untracked neighboring path\n')
      expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([untracked])
    } finally {
      repo.close()
    }
  })

  it('fails closed when an exact RC7 source commit cannot be resolved', () => {
    const repo = fixtureRepository()
    try {
      const expected = WMS_666_RC7_HISTORY[0]
      expect(() => wms666AcceptedHistoryChange(
        repo.cwd,
        expected.commit,
        expected.files[0].path,
        new Map(),
        [expected as (typeof recoveryHistory.entries)[number]],
      )).toThrow()
    } finally {
      repo.close()
    }
  })

  it('rejects future committed, dirty and staged edits of every historical document path', () => {
    const repo = fixtureRepository()
    try {
      for (const path of new Set(WMS_666_DOCUMENT_HISTORY.flatMap((entry) => entry.files.map((file) => file.path)))) {
        repo.git('reset', '--hard', repo.contract)
        repo.write(path, 'independent document before future mutation\n')
        const baseline = repo.commit('WMS-517: independent documentation')
        repo.write(path, 'future forbidden task document\n')
        const future = repo.commit('WMS-666: future documentation edit')
        expect(wms666AcceptedHistoryChange(repo.cwd, future, path)).toBe(false)
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
        repo.git('reset', '--hard', baseline)
        repo.write(path, 'unstaged forbidden document\n')
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
        repo.git('add', path)
        repo.write(path, 'independent document before future mutation\n')
        expect(repo.git('diff', '--name-only', 'HEAD', '--', path)).toBe('')
        expect(repo.git('diff', '--cached', '--name-only', 'HEAD', '--', path)).toBe(path)
        expect(wms666ScopeViolations(wms666TaskChangedPaths(repo.cwd, repo.contract))).toEqual([path])
      }
    } finally {
      repo.close()
    }
  })

  it('fails exact doc-history lookup when immutable objects are absent', () => {
    const repo = fixtureRepository()
    try {
      for (const entry of WMS_666_DOCUMENT_HISTORY) {
        expect(() => wms666AcceptedHistoryChange(repo.cwd, entry.commit, entry.files[0].path)).toThrow()
      }
    } finally {
      repo.close()
    }
  })
})

function fixtureRepository() {
  const cwd = mkdtempSync(join(tmpdir(), 'wms666-scope-'))
  const git = (...args: string[]) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  const write = (path: string, value: string) => {
    mkdirSync(dirname(join(cwd, path)), { recursive: true })
    writeFileSync(join(cwd, path), value)
  }
  const commit = (subject: string) => {
    git('add', '.')
    git('commit', '-m', subject)
    return git('rev-parse', 'HEAD')
  }
  git('init', '--quiet')
  git('config', 'user.email', 'scope-test@example.invalid')
  git('config', 'user.name', 'WMS-666 isolated scope test')
  git('config', 'commit.gpgsign', 'false')
  write('frontend/src/screens/v2/packing.ts', 'original task contract\n')
  const contract = commit('WMS-666: контракт тестов')
  return { cwd, git, write, commit, contract, close: () => rmSync(cwd, { recursive: true, force: true }) }
}
