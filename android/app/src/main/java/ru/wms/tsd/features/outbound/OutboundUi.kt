package ru.wms.tsd.features.outbound

import androidx.compose.ui.graphics.Color
import ru.wms.tsd.ui.theme.WmsColors

/**
 * Словарь статусов marketplace-unload из веба.
 * Не изобретать свои — копировать из фронтенда.
 */
fun unloadStatusRu(status: String): String = when (status) {
    "draft" -> "Черновик"
    "submitted" -> "Запланировано"
    "confirmed" -> "Утверждено"
    "collecting" -> "На сборке"
    "shipped" -> "Отгружено"
    "cancelled" -> "Отменено"
    else -> status
}

fun unloadStatusColor(status: String): Color = when (status) {
    "confirmed" -> WmsColors.Primary
    "collecting" -> WmsColors.Warning
    "shipped" -> WmsColors.Success
    else -> WmsColors.TextSecondary
}
