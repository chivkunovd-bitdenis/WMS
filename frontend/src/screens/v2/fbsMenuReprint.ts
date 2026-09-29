import type { FbsWorkspace } from './fbsApi'

type MarkingState = FbsWorkspace['orders'][number]['metadata']['states'][number]

/** The inline FBS reprint is intentionally only for an operator-bound KIZ.
 * A pool code continues to use the existing order-level repeat flow. */
export function hasOperatorKiz(
  state: MarkingState | undefined,
  marketplace: 'wb' | 'ozon',
) {
  return Boolean(
    state?.id &&
      state.kind === 'sgtin' &&
      state.source === 'operator' &&
      state.status !== 'missing' &&
      (marketplace === 'wb' || state.status !== 'rejected'),
  )
}

/**
 * WMS-575, R10: что печатает «Перепечатать» из меню ⋮ строки заказа.
 *
 * Действующий ЧЗ, внесённый оператором сканом, сервер печатает только как
 * перепечатку (иначе operator_kiz_print_forbidden). Хотфикс «Перепечатать»
 * перестал всегда просить перепечатку: флаг стал «заказ напечатан», а он ложен,
 * пока WB не подтвердил код, — и у такого заказа печать падала сырым кодом
 * ошибки. Поэтому у действующего кода оператора WB «Перепечатать» — всегда
 * перепечатка этого же кода; если экран знает id кода, он передаётся явно, как
 * у круговой стрелки «Перепечатать ЧЗ» (WMS-519).
 *
 * Всё остальное — как после хотфикса: напечатанный заказ перепечатывается, а у
 * заказа без действующего кода (после «Очистить ЧЗ», код отклонён WB)
 * печатается новый код. Ozon не меняется.
 */
export function fbsMenuReprintRequest(
  order: { metadata: { states: MarkingState[] } },
  marketplace: 'wb' | 'ozon',
  printDone: boolean,
): { reprint: boolean; reprintMarkingId?: string } {
  if (marketplace === 'wb') {
    const state = order.metadata.states.find((item) => item.kind === 'sgtin')
    const activeOperatorCode = state?.source === 'operator'
      && state.status !== 'missing'
      && state.status !== 'rejected'
    if (activeOperatorCode) {
      return state.id ? { reprint: true, reprintMarkingId: state.id } : { reprint: true }
    }
  }
  return { reprint: printDone }
}
