import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'

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

export function wms666AcceptedHistoryChange(cwd: string | URL, commit: string, path: string): boolean {
  const accepted = WMS_666_HISTORY_CHECKOUT_CHANGE
  const git = (...args: string[]) => execFileSync('git', args, { cwd, encoding: 'utf8' }).trim()
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
  for (const line of (root + history).trim().split('\n')) {
    const [commit, parents, subject] = line.split('\t')
    // Attribution is by task lineage and primary task number, never allowed paths.
    if (!/^WMS-666(?:\s+WMS-\d+)*:/.test(subject ?? '')) continue
    const merge = parents.trim().split(/\s+/).length > 1
    const changed = git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', '-z',
      ...(merge ? ['--cc'] : ['--root']), commit)
    // A merge's combined diff catches its own resolutions, not imported task trees.
    for (const path of changed.split('\0')) {
      if (path && !wms666AcceptedHistoryChange(cwd, commit, path)) paths.add(path)
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
