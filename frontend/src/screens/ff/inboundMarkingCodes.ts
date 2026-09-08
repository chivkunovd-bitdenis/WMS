export type InboundMarkingCode = {
  id: string
  line_id: string
  product_id: string
  article: string
  cis_code: string
  cz_status: 'pending' | 'introduced' | 'problem' | 'unavailable'
  cz_reason: string
  outer_status: string | null
  checked_at: string | null
}

// Classify the GS1 product+serial envelope only; the server validates the code.
// A damaged KIZ must never fall through to the product quantity endpoint.
export function isInboundMarkingScan(value: string): boolean {
  const code = value.trim().replace(/^\]d2/i, '')
  return /^01\d{14}21/.test(code) || /^\(01\)\d{14}\(21\)/.test(code) || code.includes('\x1d')
}

export function inboundMarkingStatusLabel(status: InboundMarkingCode['cz_status']): string {
  switch (status) {
    case 'introduced': return 'Введён в оборот'
    case 'problem': return 'Проблема с кодом'
    case 'unavailable': return 'Не удалось проверить'
    default: return 'Ожидает проверки'
  }
}

export function inboundMarkingNeedsAttention(code: InboundMarkingCode): boolean {
  return code.cz_status === 'problem' || code.cz_status === 'unavailable'
}

export function inboundMarkingError(message: string): string {
  const messages: Record<string, string> = {
    marking_code_not_found: 'Код уже убран из приёмки. Обновите документ.',
    marking_invalid_code: 'Код Честного знака не распознан. Отсканируйте его целиком ещё раз.',
    marking_code_other_product: 'Этот код записан для другого товара. Проверьте товар и маркировку.',
    marking_code_other_receipt: 'Этот код уже записан в другой приёмке.',
    marking_quantity_exceeded: 'Коды уже записаны для всех принятых единиц товара. Сначала отсканируйте следующий товар.',
    marking_code_in_pool: 'Этот код уже зарегистрирован в запасе для печати. Проверьте код товара.',
    marking_code_already_used: 'Этот код уже использован. Проверьте маркировку товара.',
    not_verifying: 'Приёмка уже завершена. Обновите документ.',
    line_not_found: 'Товар отсутствует в приёмке. Обновите документ и отсканируйте товар снова.',
    invalid_cis_code: 'Код Честного знака не распознан. Отсканируйте его целиком ещё раз.',
    not_a_kiz: 'Код Честного знака не распознан. Отсканируйте его целиком ещё раз.',
    duplicate_kiz: 'Этот код уже записан. Проверьте маркировку товара.',
    marking_code_already_attached: 'Этот код уже записан для другого товара или приёмки.',
    product_gtin_mismatch: 'Код Честного знака относится к другому товару. Проверьте товар и маркировку.',
    receiving_not_active: 'Приёмка уже завершена. Обновите документ.',
  }
  return messages[message] ?? (message.includes(' ') ? message : 'Не удалось сохранить код Честного знака. Повторите сканирование.')
}
