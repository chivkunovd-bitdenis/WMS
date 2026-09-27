import type { FbsOperatorStageKey } from './fbsUx'

type StageStorage = Pick<Storage, 'getItem' | 'setItem'>

function stageStorageKey(supplyId: string): string {
  // Supply IDs are globally unique UUIDs; this follows the existing per-supply FBS keys.
  return `wms:fbs:${supplyId}:stage`
}

export function readFbsWorkspaceStage(
  supplyId: string,
  storage?: StageStorage,
): FbsOperatorStageKey | null {
  try {
    const value = (storage ?? window.sessionStorage).getItem(stageStorageKey(supplyId))
    return value === 'composition' || value === 'picking' || value === 'packing' || value === 'boxes'
      ? value
      : null
  } catch {
    return null
  }
}

export function saveFbsWorkspaceStage(
  supplyId: string,
  stage: FbsOperatorStageKey,
  storage?: StageStorage,
): void {
  try {
    (storage ?? window.sessionStorage).setItem(stageStorageKey(supplyId), stage)
  } catch {
    // Storage can be unavailable; navigation in the current opening still works.
  }
}
