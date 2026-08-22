/**
 * Словарь переводов `reason` от Wildberries для вердиктов маркировки.
 * Используется для отображения человеческого текста вместо технических кодов ошибок.
 * Неизвестные коды показываются как есть в мелком тексте.
 */

export const metaStatusReasonTranslations: Record<string, string> = {
  // Коды ошибок для УИН / SGTIN
  uinBadStatus: 'неверный статус УИН',
  sgtinBadStatus: 'неверный статус SGTIN',
  uinDuplicated: 'УИН дублируется в другом заказе',
  sgtinDuplicated: 'SGTIN дублируется в другом заказе',
  uinNotFound: 'УИН не найден в системе',
  sgtinNotFound: 'SGTIN не найден в системе',

  // Коды ошибок для формата и значений
  weightBadFormat: 'вес в неверном формате',
  dimensionsBadFormat: 'габариты в неверном формате',
  invalidValue: 'недопустимое значение',

  // Коды блокировок и проверок
  checkFailed: 'проверка не пройдена',
  verificationFailed: 'верификация не пройдена',
  rejectionCode: 'отклонено по коду ошибки',

  // Добавляйте новые коды по мере встреч с WB
}

export function translateMetaStatusReason(reason: string | null): string | null {
  if (!reason) return null
  const translated = metaStatusReasonTranslations[reason]
  return translated || reason
}
