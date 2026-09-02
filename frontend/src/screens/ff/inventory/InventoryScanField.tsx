import { ScannerField } from '../../../ui-kit'

/**
 * Поле сканера на пересчёте — НЕуправляемое.
 *
 * ⛔ Раньше значение жило в состоянии React, и на тяжёлом документе это
 * съедало символы. React рисует родителя раньше ребёнка: пока перерисовывались
 * сотни строк, поле получало на коммите старое значение, а сканер к этому
 * моменту вбивал уже половину кода — и половина стиралась. Оператор видел в
 * строке «46» и дальше ничего, хотя пикнул полный штрихкод, и был уверен, что
 * система не работает. Документ «Империи ФФ» — 480 строк, там это стреляло
 * каждый раз.
 *
 * Неуправляемое поле держит правду в DOM. Перерисовка дерева его не трогает,
 * и потерять символ нельзя в принципе.
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
  return (
    <ScannerField
      onScan={onScan}
      expects={expects}
      error={error ?? null}
      notice={notice ?? null}
      testId={testId}
    />
  )
}
