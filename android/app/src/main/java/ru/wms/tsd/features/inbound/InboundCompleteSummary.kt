package ru.wms.tsd.features.inbound

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.core.api.generated.models.InboundIntakeBoxOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * B4. Полноэкранная сводка перед завершением пересчёта приёмки. Показывает
 * план/факт по каждой позиции с подсветкой расхождений (недостача — красным,
 * излишек — оранжевым), итог по коробам и общий итог. Заменяет терпкий
 * ConfirmSheet: перед необратимым «Завершить» оператор видит полную картину.
 *
 * Кнопка «Завершить» краснеет при расхождениях (destructive-семантика).
 */
@Composable
fun InboundCompleteSummary(
    displayNumber: String?,
    sellerName: String?,
    lines: List<InboundIntakeLineOut>,
    boxes: List<InboundIntakeBoxOut>,
    requestStatus: String?,
    completing: Boolean,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val totalExpected = lines.sumOf { it.expectedQty }
    val totalActual = lines.sumOf { effectiveActualQty(it, boxes, requestStatus) }
    val discrepancyCount = lines.count { effectiveActualQty(it, boxes, requestStatus) != it.expectedQty }
    val openBoxes = boxes.count { it.intakeClosedAt == null }

    Surface(color = WmsColors.Background, modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Шапка
            Surface(color = WmsColors.Surface, shadowElevation = 2.dp) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    Text(
                        "Итоги пересчёта",
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = WmsColors.TextPrimary,
                    )
                    val sub = listOfNotNull(
                        displayNumber?.let { "Поставка $it" },
                        sellerName,
                    ).joinToString(" · ")
                    if (sub.isNotBlank()) {
                        Text(sub, fontSize = 14.sp, color = WmsColors.TextSecondary)
                    }
                }
            }

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(16.dp),
            ) {
                // Сводка по коробам
                item {
                    SummaryCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "Коробов: ${boxes.size}",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = WmsColors.TextPrimary,
                                modifier = Modifier.weight(1f),
                            )
                            if (openBoxes > 0) {
                                Text(
                                    "⚠ не закрыто: $openBoxes",
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = WmsColors.Warning,
                                )
                            } else {
                                Text("все закрыты ✓", fontSize = 16.sp, color = WmsColors.Success)
                            }
                        }
                    }
                }

                // Строки план/факт
                items(lines, key = { it.id }) { line ->
                    LineSummaryRow(line, effectiveActualQty(line, boxes, requestStatus))
                }
            }

            // Итог + действия
            Surface(color = WmsColors.Surface, shadowElevation = 8.dp) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            "Итого принято",
                            fontSize = 18.sp,
                            color = WmsColors.TextSecondary,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            "$totalActual из $totalExpected шт",
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                            color = if (discrepancyCount > 0) WmsColors.Warning else WmsColors.Success,
                        )
                    }
                    if (discrepancyCount > 0) {
                        Text(
                            "Расхождения по $discrepancyCount ${positionsWord(discrepancyCount)}",
                            fontSize = 16.sp,
                            color = WmsColors.Error,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                    Text(
                        "После завершения заявка уйдёт в сортировку",
                        fontSize = 14.sp,
                        color = WmsColors.TextSecondary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    Button(
                        onClick = onConfirm,
                        enabled = !completing,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (discrepancyCount > 0) WmsColors.Error else WmsColors.Success,
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 12.dp)
                            .height(WmsDimens.PrimaryButtonHeight),
                    ) {
                        Text(
                            if (discrepancyCount > 0) "Завершить с расхождениями" else "Завершить пересчёт",
                            fontSize = 20.sp,
                        )
                    }
                    TextButton(
                        onClick = onDismiss,
                        enabled = !completing,
                        modifier = Modifier.fillMaxWidth().height(WmsDimens.TouchTargetMin),
                    ) {
                        Text("Продолжить пересчёт", fontSize = 18.sp, color = WmsColors.TextSecondary)
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryCard(content: @Composable () -> Unit) {
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) { content() }
    }
}

@Composable
private fun LineSummaryRow(line: InboundIntakeLineOut, actual: Int) {
    val diff = actual - line.expectedQty
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    line.skuCode,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = WmsColors.TextPrimary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    line.productName,
                    fontSize = 14.sp,
                    color = WmsColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            // план / факт
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    "план ${line.expectedQty}",
                    fontSize = 14.sp,
                    color = WmsColors.TextSecondary,
                )
                Text(
                    "факт $actual",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = WmsColors.TextPrimary,
                )
            }
            // расхождение
            val diffColor = when {
                diff == 0 -> WmsColors.Success
                diff < 0 -> WmsColors.Error   // недостача
                else -> WmsColors.Warning     // излишек
            }
            Text(
                text = if (diff == 0) "✓" else if (diff > 0) "+$diff" else "$diff",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = diffColor,
            )
        }
    }
}

/** «1 позиции / 2 позициям / 5 позициям» — падеж для расхождений. */
private fun positionsWord(n: Int): String {
    val mod100 = n % 100
    val mod10 = n % 10
    return when {
        mod100 in 11..14 -> "позициям"
        mod10 == 1 -> "позиции"
        else -> "позициям"
    }
}
