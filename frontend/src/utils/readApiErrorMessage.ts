const API_DETAIL_MESSAGES_RU: Record<string, string> = {
  // Инвентаризация: находки и пересчёт.
  count_not_found: 'Документ пересчёта не найден.',
  count_not_editable: 'Документ уже проведён или отменён — правки закрыты.',
  storage_location_not_found: 'Ячейка не найдена на складе.',
  container_not_found: 'Тара не найдена на складе документа.',
  container_reference_invalid: 'Тара указана неполностью — нужны и вид, и номер.',
  barcode_is_ambiguous:
    'Один и тот же код у нескольких товаров. Уточните селлера в документе или используйте артикул.',
  barcode_required: 'Не передан код для поиска товара.',

  lines_missing_storage:
    'Назначьте ячейку на каждой строке с количеством перед отправкой заявки.',
  insufficient_available: 'Недостаточно доступного остатка в выбранной ячейке.',
  insufficient_free_fbo:
    'Недостаточно свободного FBO остатка. Уменьшите количество или освободите резерв/FBS-пул.',
  directions_exceed_stock: 'Нельзя распределить больше, чем есть на ФФ.',
  insufficient_sorting_stock:
    'Нельзя разложить столько: по заявке принято меньше. Проверьте пересчёт в приёмке или укажите меньшее количество.',
  qty_exceeds_accepted: 'Нельзя разложить больше, чем принято по заявке.',
  qty_exceeds_box_remaining: 'В коробе осталось меньше указанного количества.',
  submit_empty: 'Добавьте хотя бы одну строку в заявку.',
  planned_boxes_missing: 'Укажите количество грузомест.',
  invalid_planned_box_count: 'Укажите количество грузомест.',
  distribution_incomplete:
    'Распределите всё принятое количество по ячейкам перед завершением — иначе товар не попадёт на склад.',
  distribution_not_completed: 'Распределение ещё не зафиксировано.',
  packaging_instructions_required:
    'Заполните ТЗ на упаковку для всех товаров в составе отгрузки (раздел «Каталог»).',
  packaging_incomplete: 'Упакуйте все строки задания или отметьте «Весь товар уже упакован».',
  packaging_not_done: 'Сначала завершите упаковку товара по этой отгрузке.',
  plan_limit_exceeded: 'Нельзя добавить больше, чем в плане отгрузки.',
  plan_exceeded: 'Нельзя добавить больше, чем в плане отгрузки.',
  linked_unload: 'Нельзя отменить задание, связанное с отгрузкой на МП.',
  not_draft: 'Удалить можно только черновик. Документ уже в работе, поэтому он сохранен в истории.',
  insufficient_unpacked: 'Недостаточно неупакованного остатка в выбранном месте.',
  insufficient_packaging_stock: 'Недостаточно остатка товара в ячейке упаковки.',
  insufficient_codes: 'Недостаточно КМ у селлера для печати по строке.',
  already_printed_use_reprint: 'КМ по этой строке уже напечатаны — используйте «Повтор».',
  marking_not_done: 'Не хватает напечатанных КМ по заданию на упаковку.',
  marking_not_required: 'Для этого товара ЧЗ не требуется.',
  nothing_to_mark: 'По строке нечего маркировать (упаковка уже подтверждена с полки).',
  unsupported_file_type: 'Поддерживаются файлы CSV, TXT или PDF.',
  product_seller_mismatch: 'Товар принадлежит другому селлеру — выберите товар этого селлера.',
  pool_not_found: 'Пул КМ не найден.',
  empty_file: 'В файле не найдено КМ.',
  not_reopenable: 'Нельзя открыть распределение заново на этом статусе заявки.',
  already_posted_partial: 'Часть товара уже оприходована — отмена фиксации недоступна.',
  sorting_stock_unavailable:
    'Нельзя отменить приёмку: в зоне сортировки уже нет нужного остатка (товар могли разложить или списать).',
  not_found: 'Документ не найден.',
  not_editable: 'Документ сейчас недоступен для изменения.',
  bad_status: 'Действие недоступно в текущем статусе документа.',
  open_box_exists: 'Открытый короб уже есть — закройте его перед созданием нового.',
  invalid_quantity: 'Укажите количество больше нуля.',
  product_not_in_shipment: 'Этого товара нет в составе отгрузки.',
  location_not_found: 'Ячейка не найдена на этом складе.',
  location_required:
    'Отсканируйте ячейку — товар хранится в нескольких местах, система не может выбрать автоматически.',
  product_not_found: 'Товар не найден.',
  barcode_empty: 'Отсканируйте штрихкод.',
  barcode_unknown: 'Штрихкод не найден. Проверьте товар или ячейку.',
  pick_required: 'Сначала подберите товар.',
  no_lines: 'В документе нет строк.',
  wb_mp_warehouse_required: 'Выберите склад Wildberries для отгрузки.',
  wb_mp_warehouse_not_supported: 'Склад Wildberries нельзя указать для этого маркетплейса.',
  provider_dispatch_blocked:
    'Передача в Ozon заблокирована: кабинет Ozon недоступен. Документ и остатки не изменены.',
  provider_dispatch_failed:
    'Передача в Ozon не выполнена. Документ и остатки не изменены.',
  seller_required: 'У документа не указан селлер.',
  open_box_required: 'Нет открытого короба.',
  box_not_found: 'Короб не найден.',
  box_closed: 'Короб уже закрыт.',
  planned_shipment_date_required: 'Укажите плановую дату отгрузки.',
  invalid_preset: 'Выберите корректный размер короба.',
  invalid_batch_count: 'Укажите количество коробов от 1 до 50.',
  box_barcode_unknown: 'Штрихкод короба не найден.',
  box_needs_location: 'Укажите ячейку для короба.',
  box_empty: 'В коробе нет товара.',
  line_not_found: 'Строка не найдена.',
  line_empty: 'В строке нет количества.',
  box_already_attached: 'Этот короб уже привязан к другой отгрузке.',
  warehouse_mismatch: 'Короб создан на другом складе.',
  box_not_empty: 'Сначала уберите товар из короба.',
}

export async function readApiErrorMessage(res: Response): Promise<string> {
  try {
    const text = await res.text()
    if (!text) {
      return `Ошибка ${res.status}`
    }
    const data = JSON.parse(text) as { detail?: unknown }
    const d = data.detail
    if (typeof d === 'string') {
      return API_DETAIL_MESSAGES_RU[d] ?? d
    }
    if (Array.isArray(d)) {
      const parts = d
        .map((x: { msg?: string; loc?: unknown }) => {
          const msg = typeof x?.msg === 'string' ? x.msg : null
          const loc = x?.loc
          const field =
            Array.isArray(loc) && loc.length > 0
              ? String(loc[loc.length - 1])
              : null
          if (msg && field) return `${field}: ${msg}`
          if (msg) return msg
          return JSON.stringify(x)
        })
        .filter((p): p is string => Boolean(p))
      // FastAPI/Pydantic часто возвращают много строк — ограничим длину.
      return parts.join('; ').slice(0, 240)
    }
    if (d && typeof d === 'object') {
      const structured = d as { message?: unknown; code?: unknown }
      if (typeof structured.message === 'string' && structured.message.trim()) {
        return structured.message
      }
      if (typeof structured.code === 'string' && structured.code.trim()) {
        return API_DETAIL_MESSAGES_RU[structured.code] ?? structured.code
      }
    }
    return text.slice(0, 200)
  } catch {
    return `Ошибка ${res.status}`
  }
}
