const API_DETAIL_MESSAGES_RU: Record<string, string> = {
  lines_missing_storage:
    'Назначьте ячейку на каждой строке с количеством перед отправкой заявки.',
  insufficient_available: 'Недостаточно доступного остатка в выбранной ячейке.',
  insufficient_sorting_stock:
    'Нельзя разложить столько: по заявке принято меньше. Проверьте пересчёт в приёмке или укажите меньшее количество.',
  qty_exceeds_accepted: 'Нельзя разложить больше, чем принято по заявке.',
  qty_exceeds_box_remaining: 'В коробе осталось меньше указанного количества.',
  submit_empty: 'Добавьте хотя бы одну строку в заявку.',
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
  insufficient_unpacked: 'Недостаточно неупакованного остатка в выбранном месте.',
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
    return text.slice(0, 200)
  } catch {
    return `Ошибка ${res.status}`
  }
}

