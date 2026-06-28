import { Navigate } from 'react-router-dom'

/** FINAL-02: канонический импорт — `MarkingImportDialog` на экране списка пулов. */
export function HonestSignImportPage() {
  return <Navigate to="/app/ff/honest-sign" replace />
}
