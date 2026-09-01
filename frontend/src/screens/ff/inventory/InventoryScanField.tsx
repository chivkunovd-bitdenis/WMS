import { useState } from 'react'
import { ScannerField } from '../../../ui-kit'

/**
 * Поле сканера со своим состоянием.
 *
 * Сканер печатает код посимвольно. Значение намеренно живёт здесь, а не рядом
 * с деревом инвентаризации: ни один символ до Enter не перерисовывает сотни
 * строк документа.
 */
export function InventoryScanField({
  expects,
  error,
  notice,
  onScan,
  testId,
}: {
  expects: string
  error?: string | null
  notice?: string | null
  onScan: (code: string) => void
  testId: string
}) {
  const [value, setValue] = useState('')
  return (
    <ScannerField
      value={value}
      onChange={setValue}
      onScan={(code) => {
        setValue('')
        onScan(code)
      }}
      expects={expects}
      error={error ?? null}
      notice={notice ?? null}
      testId={testId}
    />
  )
}
