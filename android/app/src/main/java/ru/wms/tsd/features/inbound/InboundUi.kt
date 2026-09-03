package ru.wms.tsd.features.inbound

import androidx.compose.ui.graphics.Color
import ru.wms.tsd.core.api.generated.models.InboundIntakeBoxOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut
import ru.wms.tsd.ui.theme.WmsColors

/**
 * Словарь статусов заявки на поставку — перенос из веба
 * (frontend/src/screens/ff/inboundReceivingHelpers.ts). Не изобретать свои.
 */
fun isReceivingStatus(status: String): Boolean =
    status == "receiving" || status == "primary_accepted" || status == "verifying"

fun isSortingStatus(status: String): Boolean =
    status == "sorting" || status == "verified"

fun isDoneStatus(status: String): Boolean =
    status == "done" || status == "posted"

/**
 * Можно ли создавать короба в этом статусе. Бэкенд (INTAKE_STATUSES) разрешает
 * только submitted и receiving — на verifying/primary_accepted и позже создание
 * короба отбивается («Документ не в том статусе»). ВНИМАНИЕ: это НЕ то же, что
 * isReceivingStatus (та включает verifying).
 */
fun canCreateInboundBox(status: String?): Boolean =
    status == "submitted" || status == "receiving"

fun inboundStatusRu(status: String): String = when {
    status == "draft" -> "Черновик"
    status == "submitted" -> "Передано на склад"
    isReceivingStatus(status) -> "Приёмка"
    isSortingStatus(status) -> "В сортировке"
    isDoneStatus(status) -> "Оприходовано"
    else -> status
}

fun inboundStatusColor(status: String): Color = when {
    status == "submitted" -> WmsColors.Primary
    isReceivingStatus(status) -> WmsColors.Warning
    isSortingStatus(status) -> WmsColors.Primary
    isDoneStatus(status) -> WmsColors.Success
    else -> WmsColors.TextSecondary
}

/** Факт по строке = effective_actual_qty с сервера, иначе loose + сумма по коробам (как в вебе). */
fun effectiveActualQty(
    line: InboundIntakeLineOut,
    boxes: List<InboundIntakeBoxOut>,
    requestStatus: String?,
): Int {
    line.effectiveActualQty?.let { return it }
    val loose = line.actualQty ?: 0
    if (requestStatus != null && (isSortingStatus(requestStatus) || isDoneStatus(requestStatus))) {
        return loose
    }
    val boxTotal = boxes.sumOf { box ->
        box.lines.orEmpty().filter { it.productId == line.productId }.sumOf { it.quantity }
    }
    return loose + boxTotal
}
