/** Russian labels for marking code statuses (pool/codes UI). */
export const CODE_STATUS_LABELS: Record<string, string> = {
  available: 'Доступен',
  reserved: 'Зарезервирован',
  printed: 'Напечатан',
  applied: 'Нанесён',
  introduced: 'Введён в оборот',
  shipped: 'Отгружен',
  transferred: 'Передан',
  defective: 'Брак',
  replaced: 'Заменён',
  void: 'Аннулирован',
}

/** Russian labels for marking ledger event types. */
export const LEDGER_EVENT_LABELS: Record<string, string> = {
  imported: 'Импорт',
  printed: 'Печать',
  reprinted: 'Повторная печать',
  applied: 'Нанесение',
  introduced: 'Ввод в оборот',
  shipped: 'Отгрузка',
  transferred: 'Передача',
  defective: 'Брак',
  replaced: 'Замена',
  voided: 'Аннулирование',
}

export function codeStatusLabel(status: string): string {
  return CODE_STATUS_LABELS[status] ?? status
}

export function ledgerEventLabel(eventType: string): string {
  return LEDGER_EVENT_LABELS[eventType] ?? eventType
}
