import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'

const WMS_666_CONTRACT = '0e078418bcb7ee45fa654b0d829e5de0ec80ebb0'
const WMS_666_ACCEPTED_BASE = '322bb46d96178fc25f007aaf2807c9ce7dfe9bc0'
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
  'docs/evidence/WMS-666/release-1008/prod-hotfix-a19d02d31ba57763ce93a29005a95cc3f473e005.diff',
])
const WMS_666_ALLOWED_CODE_FILES = new Set([
  'frontend/src/screens/v2/FbsPackingActionsToolbar.tsx',
  'frontend/src/screens/v2/FbsPackingActionsToolbar.prodIntegration.dom.test.tsx',
  'frontend/src/utils/useMarkingCodePrint.tsx',
  'frontend/src/screens/v2/fbsApi.ts',
  'frontend/src/components/MarkingPrintDialog.tsx',
  'frontend/src/screens/v2/FfFbsStickerPrefetch.wms666.dom.test.tsx',
  'backend/app/api/fbs_supplies.py',
  'backend/app/services/fbs_worklist_service.py',
  'backend/app/services/fbs_workspace_service.py',
  'backend/app/services/marking_code_service.py',

  'frontend/src/screens/v2/FbsPackingScanBar.tsx',
  'frontend/src/screens/v2/FbsScanPrintToggles.tsx',
  'frontend/src/screens/v2/FbsScanPrintToggles.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsOrdersScreen.tsx',
  'frontend/src/screens/v2/FfFbsSupplyAssembly.tsx',
  'frontend/src/screens/v2/FfFbsSupplyAssembly.scanners.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyAssembly.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.scan.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.size.test.ts',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms514.test.ts',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms666.printFreshness.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms666.history.dom.test.tsx',
  'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
  'frontend/tests-e2e/wms652-critical/vite.native.config.ts',
  'frontend/src/screens/v2/fbsSequentialPacking.ts',
  'frontend/src/screens/v2/fbsSupplyAssembly.ts',
  'frontend/src/screens/v2/fbsUx.ts',
  'frontend/src/components/MarkingPrintDialog.availability.dom.test.tsx',
  'frontend/src/components/MarkingPrintDialog.partialAck.wms666.dom.test.tsx',
  'backend/tests/test_fbs_kiz.py',
  'backend/tests/test_fbs_packing_box.py',
  'backend/tests/test_fbs_supply_from_orders.py',
  'backend/tests/test_ozon_box_assembly.py',
  'backend/tests/test_wms666_ozon_quantity_print_bindings.py',
  'backend/tests/test_wms666_workspace_marking_pool.py',
  'backend/app/services/fbs_supply_service.py',
  'backend/tests/test_fbs_create_http_connection.py',
  'backend/tests/test_fbs_ozon_lane.py',
  'backend/app/services/fbs_order_tape_print_service.py',
  'backend/tests/test_fbs_order_tape_print_missing_codes.py',
  'backend/tests/test_fbs_order_tape_qr_only.py',
  'tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json',
  'frontend/src/screens/v2/fbsStickerPrefetch.ts',
  'frontend/src/screens/v2/fbsStickerPrefetch.test.ts',
  'frontend/src/screens/v2/fbsWorkspaceFreshness.ts',
  'frontend/src/screens/v2/fbsWorkspaceFreshness.test.ts',
  'frontend/src/screens/v2/fbsPickingColor.wms673.dom.test.tsx',
  'frontend/src/screens/v2/fbsPickingColor.wms673.pdf.test.ts',
  'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts',
  'frontend/src/utils/printProductThermalLabel.test.ts',
  'frontend/src/utils/wms680PrintContract.test.ts',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms680.test.ts',
  'backend/tests/test_wms537_draft_supply_stickers.py',
  'frontend/src/screens/v2/FfFbsSupplyAssembly.dom.test.tsx',
  'backend/tests/fbs_picking_browser_verify.py',
])
const WMS_666_PROCESS_FILES = new Set([
  'backend/tests/test_wms662_exact_fixture_pairs_contract.py',
  'docs/reviews/WMS-652-step9-draft/etalon.ruleset.disabled.json',
  'docs/reviews/wms666-prod-integration-1009-review.md',
  'AGENTS.md',
  'CLAUDE.md',
  'scripts/ci/backend_shards.py',
  'scripts/ci/build_process_proof.py',
  'scripts/ci/check_regression_guards.py',
  'scripts/ci/check_task_documents.py',
  'scripts/ci/ci_scope.py',
  'scripts/ci/process_contracts.py',
  'scripts/ci/promote_guards.py',
  'scripts/ci/run_release_postgres.sh',
  'scripts/ci/select_process_artifacts.py',
  'scripts/ci/test_check_task_documents.py',
  'scripts/ci/tests/fixtures/wms652_source_binding_transition.json',
  'scripts/ci/tests/test_backend_shard_progress.py',
  'scripts/ci/tests/test_backend_shards.py',
  'scripts/ci/tests/test_ci_release_additions.py',
  'scripts/ci/tests/test_ci_scope.py',
  'scripts/ci/tests/test_process_contracts.py',
  'scripts/ci/tests/test_process_deploy_gate.py',
  'scripts/ci/tests/test_promote_guards.py',
  'scripts/ci/tests/test_regression_guards.py',
  'scripts/ci/tests/test_retain_web_assets.py',
  'scripts/ci/tests/test_reviewed_process_upgrade.py',
  'scripts/ci/tests/test_server_process_gate.py',
  'scripts/ci/tests/test_trusted_process_artifact.py',
  'scripts/ci/tests/test_trusted_process_bootstrap.py',
  'scripts/ci/tests/test_trusted_process_check.py',
  'scripts/ci/tests/test_verify_ci.py',
  'scripts/ci/trusted_process_check.py',
  'scripts/ci/verify_ci.py',
  'scripts/ci/verify_process_ci.py',
  'scripts/ci/verify_server_process_ci.py',
  'scripts/deploy/retain-web-assets.py',
  'scripts/deploy/rollback-wms666-packing.sh',

  '.github/workflows/ci.yml',
  'guards/PROCESS_CONTRACTS.json',
  'frontend/src/screens/v2/wms666ChangeScope.test.ts',
  'frontend/tests-e2e/wms652-critical/browser.mjs',
  'frontend/tests-e2e/fbs-picking/extended.mjs',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.load.test.ts',
  'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms477.test.ts',
  'frontend/tests-e2e/wms652-cdp-cancellation.test.mjs',
  'scripts/ci/tests/fixtures/wms652_source_binding_transition.json',
  'scripts/ci/backend_shards.py',
  'scripts/ci/tests/test_backend_shard_progress.py',
  'scripts/ci/verify_ci.py',
  'scripts/ci/trusted_process_check.py',
  'scripts/ci/tests/test_verify_ci.py',
  'scripts/ci/tests/test_trusted_process_check.py',
])

export function wms666TaskChangedPaths(
  cwd: string | URL,
  contract = WMS_666_CONTRACT,
): string[] {
  const git = (...args: string[]) => execFileSync('git', args, {
    cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  })
  // Missing history must fail, rather than quietly produce an empty task diff.
  git('merge-base', '--is-ancestor', contract, 'HEAD')
  const head = git('rev-parse', 'HEAD').trim()
  const historyStart = wms666AcceptedTaskBase(git, contract, head)
  // Include side-branch commits later merged into this task range.
  const history = git('log', '--format=%H%x09%P%x09%s', `${historyStart}..${head}`)
  const paths = new Set<string>()
  for (const line of history.trim().split('\n')) {
    const [commit, parents, subject] = line.split('\t')
    // Attribution is by task lineage and primary task number, never allowed paths.
    if (!/^WMS-666(?:\s+WMS-\d+)*:/.test(subject ?? '')) continue
    const merge = parents.trim().split(/\s+/).length > 1
    const changed = git('diff-tree', '--no-commit-id', '--name-only', '--no-renames', '-r', '-z',
      ...(merge ? ['--cc'] : []), commit)
    // Ordinary review assesses content; this gate checks only task scope.
    for (const path of changed.split('\0')) if (path) paths.add(path)
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

function wms666AcceptedTaskBase(
  git: (...args: string[]) => string, contract: string, head: string,
): string {
  try {
    git('merge-base', '--is-ancestor', contract, WMS_666_ACCEPTED_BASE)
    git('merge-base', '--is-ancestor', WMS_666_ACCEPTED_BASE, head)
    return WMS_666_ACCEPTED_BASE
  } catch {
    // Synthetic/older checkouts lack this already accepted milestone; inspect
    // the full task history rather than relying on a main-only source pin.
    return contract
  }
}

export function wms666ScopeViolations(paths: string[]): string[] {
  return paths.filter((path) => {
    if (!path) return false
    if (path === 'docs/KANONICHESKIY_BACKLOG.md' || path === 'docs/requirements/WMS-666.md') return false
    // Only this task's machine-readable correction record belongs to its scope.
    if (path === 'docs/reviews/contract-corrections/WMS-666.json') return false
    if (WMS_666_PROOF_FILES.has(path) || path.startsWith('docs/evidence/WMS-666/')) return false
    if (WMS_666_ALLOWED_CODE_FILES.has(path) || WMS_666_PROCESS_FILES.has(path)) return false
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
      'frontend/tests-e2e/wms652-critical/vite.native.config.ts',
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

  it('allows only named WMS-666 package files, including sticker-source coverage', () => {
    const allowed = [
      'backend/app/services/fbs_supply_service.py',
      'backend/tests/test_fbs_create_http_connection.py',
      'backend/tests/test_fbs_ozon_lane.py',
      'backend/app/services/fbs_order_tape_print_service.py',
      'backend/tests/test_fbs_order_tape_print_missing_codes.py',
      'backend/tests/test_fbs_order_tape_qr_only.py',
      'tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json',
      'frontend/src/screens/v2/fbsStickerPrefetch.ts',
      'frontend/src/screens/v2/fbsStickerPrefetch.test.ts',
      'frontend/src/screens/v2/fbsWorkspaceFreshness.ts',
      'frontend/src/screens/v2/fbsWorkspaceFreshness.test.ts',
      'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx',
      'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms514.test.ts',
      'frontend/src/screens/v2/FfFbsSupplyAssembly.tsx',
      'frontend/src/screens/v2/FfFbsSupplyAssembly.dom.test.tsx',
      'frontend/tests-e2e/wms652-critical/vite.native.config.ts',
      'frontend/src/screens/v2/fbsPickingColor.wms673.dom.test.tsx',
      'frontend/src/utils/wms680PrintContract.test.ts',
      'frontend/src/screens/v2/FfFbsSupplyWorkspace.wms680.test.ts',
      'backend/tests/test_wms537_draft_supply_stickers.py',
      'backend/tests/fbs_picking_browser_verify.py',
    ]
    expect(wms666ScopeViolations(allowed)).toEqual([])
    const adjacent = [
      'backend/app/services/other_service.py',
      'backend/tests/test_unrelated.py',
      'frontend/src/screens/v2/UnrelatedScreen.tsx',
      'frontend/src/screens/v2/UnrelatedScreen.test.tsx',
    ]
    expect(wms666ScopeViolations(adjacent)).toEqual(adjacent)
  })

  it('reads advancing task history: foreign backend passes, new task backend or guards fail', () => {
    const repo = fixtureRepository()
    try {
      repo.write('backend/app/services/ozon_documents.py', 'foreign task\n')
      repo.commit('WMS-663: independent document action')
      repo.write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'approved task UI\n')
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
      repo.write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'own UI\n')
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

  it('allows reviewed CI preparation paths and rejects unrelated deployment changes', () => {
    const repo = fixtureRepository()
    const path = '.github/workflows/deploy.yml'
    expect(wms666ScopeViolations([path])).toEqual([path])
    expect(wms666ScopeViolations([
      '.github/workflows/ci.yml',
      'guards/PROCESS_CONTRACTS.json',
      'frontend/tests-e2e/fbs-picking/extended.mjs',
      'scripts/ci/backend_shards.py',
    ])).toEqual([])
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

  it('checks the full task range and still includes later changes', () => {
    const repo = fixtureRepository()
    try {
      repo.write('base.txt', 'reviewed base\n')
      repo.commit('WMS-652: reviewed base')
      repo.write('backend/app/services/inventory_service.py', 'reviewed historical backend change\n')
      repo.commit('WMS-666: source history before review')
      repo.write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'reviewed source\n')
      const source = repo.commit('WMS-666: independently reviewed source')

      repo.git('checkout', '-b', 'task', source)
      repo.write('backend/app/services/inventory_service.py', 'unreviewed future backend change\n')
      repo.commit('WMS-666: future task change')
      expect(wms666TaskChangedPaths(repo.cwd, repo.contract)).toEqual([
        'backend/app/services/inventory_service.py',
        'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
      ])
      const unstagedPath = 'backend/app/services/untracked_after_review.py'
      repo.write(unstagedPath, 'untracked forbidden change\n')
      expect(wms666TaskChangedPaths(repo.cwd, repo.contract)).toEqual([
        'backend/app/services/inventory_service.py',
        unstagedPath, 'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
      ])
      repo.git('add', unstagedPath)
      const stagedPath = 'backend/app/services/staged_after_review.py'
      repo.write(stagedPath, 'staged forbidden change\n')
      repo.git('add', stagedPath)
      expect(wms666TaskChangedPaths(repo.cwd, repo.contract)).toEqual([
        'backend/app/services/inventory_service.py', stagedPath, unstagedPath,
        'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
      ])
    } finally {
      repo.close()
    }
  })

  it('checks WMS-666 side-branch commits merged into task history', () => {
    const repo = fixtureRepository()
    try {
      repo.write('base.txt', 'reviewed base\n')
      const base = repo.commit('WMS-652: reviewed base')
      repo.write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'reviewed source\n')
      const source = repo.commit('WMS-666: independently reviewed source')

      repo.git('checkout', '-b', 'side', base)
      repo.write('backend/app/services/inventory_service.py', 'unreviewed side-branch change\n')
      repo.commit('WMS-666: forbidden side-branch backend edit')
      repo.git('checkout', '-b', 'task', source)
      repo.git('merge', '--no-ff', '--no-edit', 'side')
      expect(wms666TaskChangedPaths(repo.cwd, repo.contract)).toEqual([
        'backend/app/services/inventory_service.py',
        'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx',
      ])
    } finally {
      repo.close()
    }
  })

  it('ignores external history metadata and keeps the non-empty task diff', () => {
    const repo = fixtureRepository()
    try {
      repo.write('base.txt', 'reviewed base\n')
      const base = repo.commit('WMS-652: reviewed base')
      repo.git('checkout', '-b', 'task', base)
      repo.write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'task change\n')
      repo.commit('WMS-666: checked-out task')
      repo.write('scripts/ci/process_bootstrap.json', 'malformed history metadata')
      expect(wms666TaskChangedPaths(repo.cwd, repo.contract)).toEqual([
        'frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'scripts/ci/process_bootstrap.json',
      ])
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
  write('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'original task contract\n')
  const contract = commit('WMS-666: контракт тестов')
  return { cwd, git, write, commit, contract, close: () => rmSync(cwd, { recursive: true, force: true }) }
}
