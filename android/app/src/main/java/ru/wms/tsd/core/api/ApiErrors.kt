package ru.wms.tsd.core.api

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.Response

/**
 * Человекочитаемые тексты ошибок API. Бэкенд кладёт в detail либо строку-код
 * (например 'product_not_on_request'), либо текст, либо список ошибок валидации.
 * Известные коды переводим (перенос словаря из веба: inboundReceivingHelpers.ts).
 */
private val ERROR_CODES_RU = mapOf(
    // Приёмка (inbound_intake)
    "product_not_on_request" to "Товар не найден в этой поставке",
    "barcode_unknown" to "Штрихкод не найден в этой заявке",
    "barcode_empty" to "Пустой штрихкод",
    "open_box_exists" to "Сначала закройте открытый короб",
    "box_not_empty" to "Нельзя удалить короб с товарами",
    "box_closed" to "Короб уже закрыт",
    "box_not_found" to "Короб не найден",
    // Сортировка (distributions)
    "location_not_found" to "Ячейка не найдена",
    "box_not_closed" to "Сначала закройте короб в приёмке",
    "qty_exceeds_accepted" to "Больше, чем принято",
    "qty_exceeds_box_remaining" to "Больше, чем осталось в коробе",
    "insufficient_sorting_stock" to "Недостаточно товара в сортировке",
    "nothing_to_putaway" to "Нечего размещать",
    // Сборка отгрузки (marketplace_unload, найдены на живом прогоне T-18)
    "location_required" to "Сначала отсканируйте ячейку",
    "plan_limit_exceeded" to "Больше плана — товар уже собран",
    "product_not_in_shipment" to "Товара нет в этой отгрузке",
    "insufficient_available" to "Недостаточно остатка в ячейке",
    "warehouse_mismatch" to "Ячейка другого склада",
    "box_needs_location" to "Сначала отсканируйте ячейку",
    "box_empty" to "Короб пуст",
    "seller_required" to "У заявки не указан селлер",
    "planned_shipment_date_required" to "Не указана плановая дата отгрузки",
    "not_editable" to "Заявка не в том статусе",
    // Упаковка + Честный Знак (packaging_tasks, гейт перед ship — T-15b)
    "packaging_not_done" to "Сначала завершите упаковку",
    "packaging_incomplete" to "Упаковано не всё — завершить нельзя",
    "marking_not_done" to "Не все коды ЧЗ напечатаны. Печать — на рабочем месте упаковки",
    "task_not_done" to "Задача упаковки не завершена",
    "invalid_qty" to "Недопустимое количество",
    "insufficient_unpacked" to "Недостаточно неупакованного товара",
    "line_not_found" to "Строка не найдена",
    "no_lines" to "В документе нет строк",
    "unload_not_confirmed" to "Отгрузка не подтверждена",
    "wb_mp_warehouse_required" to "Не указан склад маркетплейса",
    "distribution_incomplete" to ERROR_DISTRIBUTION_INCOMPLETE_RU,
    "bad_status" to "Документ не в том статусе",
)

/** Отдельная константа: по этой ошибке ship предлагает подтвердить расхождение. */
const val ERROR_DISTRIBUTION_INCOMPLETE_RU = "Собрано не по плану — проверьте короба"

private val lenientJson = Json { ignoreUnknownKeys = true }

fun <T> Response<T>.readableError(): String {
    if (code() == 401) return "Сессия истекла. Войдите заново"
    val raw = runCatching { errorBody()?.string() }.getOrNull()
        ?: return "Ошибка сервера (HTTP ${code()})"
    val detail = runCatching {
        val el = lenientJson.parseToJsonElement(raw).jsonObject["detail"] ?: return@runCatching null
        when {
            el is kotlinx.serialization.json.JsonPrimitive -> el.jsonPrimitive.content
            else -> el.jsonArray.firstOrNull()?.jsonObject?.get("msg")?.jsonPrimitive?.content
        }
    }.getOrNull() ?: return "Ошибка сервера (HTTP ${code()})"
    return ERROR_CODES_RU[detail] ?: detail
}

/** Единый текст для сетевых исключений (нет связи/таймаут). */
fun networkErrorText(): String = "Нет связи с сервером"
