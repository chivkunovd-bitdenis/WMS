export type WorkspaceWriteIdentity = {
  isCurrent: () => boolean
  isLatest: () => boolean
}

// A later silent refresh may supersede UI application without changing which
// supply opening owns an already-started operator action.
export function isWorkspaceWriteScreenCurrent(
  write: WorkspaceWriteIdentity,
  shownSupplyId: string | null,
  targetSupplyId: string,
): boolean {
  return write.isCurrent() && shownSupplyId === targetSupplyId
}
