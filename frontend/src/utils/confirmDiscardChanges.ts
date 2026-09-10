/** WMS-179: only unsaved local input requires confirmation. */
export function confirmDiscardChanges(dirty: boolean): boolean {
  return !dirty || window.confirm('Закрыть без сохранения?')
}
