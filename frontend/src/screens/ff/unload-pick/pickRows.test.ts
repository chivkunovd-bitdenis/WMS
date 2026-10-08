import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// WMS-709 · C10: лист подбора (печать) не зависит от строк вида подбора. Этап 2
// меняет только вид по ячейкам; если печать начнёт брать функции из pickRows,
// порядок и скрытие строк уйдут в бумагу без проверки.
const PRINT_MODULES = ['../../v2/FfFbsPickList.tsx', '../../v2/fbs-pick-list-preview.tsx']

describe('WMS-709 · печать листа подбора', () => {
  it('C10: печать листа подбора не импортирует pickRows', () => {
    for (const path of PRINT_MODULES) {
      const source = readFileSync(new URL(path, import.meta.url), 'utf8')
      expect(source, path).not.toMatch(/from\s+['"][^'"]*pickRows['"]/)
    }
  })
})
