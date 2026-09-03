package ru.wms.tsd.features.outbound

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.core.api.generated.models.PackagingTaskLineOut
import ru.wms.tsd.core.api.generated.models.PackagingTaskOut
import ru.wms.tsd.ui.patterns.QtyInput
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * T-15b. Панель упаковки внутри сборки отгрузки. Ship невозможен, пока задача
 * упаковки не done (серверный гейт packaging_not_done), а для товаров с ЧЗ —
 * пока напечатанных кодов меньше упакованного (marking_not_done). Печать ЧЗ
 * физически идёт из браузера на рабочем месте упаковки — ТСД только показывает
 * статус печати и ведёт счёт упакованного.
 */
@Composable
fun PackagingPanel(
    task: PackagingTaskOut,
    onLineClick: (PackagingTaskLineOut) -> Unit,
    modifier: Modifier = Modifier,
) {
    val done = task.lines.sumOf { it.qtyDone }
    val total = task.lines.sumOf { it.qtyTotal }
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Упаковка",
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = WmsColors.TextPrimary,
                modifier = Modifier.weight(1f),
            )
            Text(
                if (task.status == "done") "Завершена ✓" else "$done из $total шт",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = if (task.status == "done") WmsColors.Success else WmsColors.Primary,
            )
        }
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 16.dp),
        ) {
            items(
                task.lines.sortedBy { it.isComplete && !markingIncomplete(it) },
                key = { it.id },
            ) { line ->
                PackagingLineCard(
                    line = line,
                    clickable = task.status != "done",
                    onClick = { onLineClick(line) },
                )
            }
        }
    }
}

@Composable
private fun PackagingLineCard(
    line: PackagingTaskLineOut,
    clickable: Boolean,
    onClick: () -> Unit,
) {
    val markingBlocked = markingIncomplete(line)
    val completed = line.isComplete && !markingBlocked
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = if (completed) WmsColors.Background else WmsColors.Surface,
        shadowElevation = if (completed) 0.dp else 1.dp,
        modifier = if (clickable) Modifier.clickable(onClick = onClick) else Modifier,
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        line.skuCode,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (completed) WmsColors.TextSecondary else WmsColors.TextPrimary,
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
                Text(
                    "${line.qtyDone} / ${line.qtyTotal}",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (line.isComplete) WmsColors.Success else WmsColors.TextPrimary,
                )
            }
            if (line.qtyTotal > 0) {
                LinearProgressIndicator(
                    progress = { (line.qtyDone.toFloat() / line.qtyTotal).coerceIn(0f, 1f) },
                    color = if (line.isComplete) WmsColors.Success else WmsColors.Primary,
                    modifier = Modifier.fillMaxWidth().height(4.dp).padding(top = 6.dp),
                )
            }
            if (line.requiresHonestSign) {
                Text(
                    if (markingBlocked) {
                        "⚠ ЧЗ: напечатано ${line.qtyMarkingPrinted} из ${line.qtyDone} — печать в вебе"
                    } else {
                        "ЧЗ: напечатано ${line.qtyMarkingPrinted}"
                    },
                    fontSize = 16.sp,
                    fontWeight = if (markingBlocked) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (markingBlocked) WmsColors.Warning else WmsColors.TextSecondary,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
            line.packagingInstructions?.takeIf { it.isNotBlank() }?.let { instructions ->
                Text(
                    instructions,
                    fontSize = 14.sp,
                    color = WmsColors.TextSecondary,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

/**
 * Шторка строки упаковки: подтвердить «уже упаковано на полке» (suggested)
 * и/или записать упакованное сейчас количество.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PackLineSheet(
    line: PackagingTaskLineOut,
    busy: Boolean,
    onConfirmFromShelf: () -> Unit,
    onPack: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    // Сколько ещё можно записать как «упаковано сейчас» (лимит сервера)
    val packRemaining = (line.qtyNeedPack - line.qtyPackedInTask).coerceAtLeast(0)
    var qty by remember(line.id, packRemaining) { mutableIntStateOf(packRemaining.coerceAtMost(1)) }
    val shelfAvailable = line.qtySuggestedPacked > line.qtyConfirmedPacked

    ModalBottomSheet(onDismissRequest = { if (!busy) onDismiss() }) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(line.skuCode, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WmsColors.TextPrimary)
            Text(
                line.productName,
                fontSize = 16.sp,
                color = WmsColors.TextSecondary,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "Упаковано ${line.qtyDone} из ${line.qtyTotal} шт",
                fontSize = 18.sp,
                color = WmsColors.TextSecondary,
            )
            line.packagingInstructions?.takeIf { it.isNotBlank() }?.let { instructions ->
                Text(
                    instructions,
                    fontSize = 16.sp,
                    color = WmsColors.TextPrimary,
                )
            }
            if (line.requiresHonestSign) {
                Text(
                    "ЧЗ: напечатано ${line.qtyMarkingPrinted}. Печать кодов — на рабочем месте упаковки (веб)",
                    fontSize = 16.sp,
                    color = if (markingIncomplete(line)) WmsColors.Warning else WmsColors.TextSecondary,
                )
            }

            if (shelfAvailable) {
                FilledTonalButton(
                    onClick = onConfirmFromShelf,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().height(WmsDimens.TouchTargetMin),
                ) {
                    Text("На полке уже упаковано ${line.qtySuggestedPacked} — подтвердить", fontSize = 17.sp)
                }
            }

            if (packRemaining > 0) {
                QtyInput(
                    value = qty,
                    onValueChange = { qty = it },
                    min = 0,
                    max = packRemaining,
                    maxHint = "Осталось упаковать $packRemaining",
                )
                Button(
                    onClick = { onPack(qty) },
                    enabled = !busy && qty in 1..packRemaining,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(WmsDimens.PrimaryButtonHeight)
                        .padding(bottom = 16.dp),
                ) {
                    Text("Упаковано $qty шт", fontSize = 20.sp)
                }
            } else {
                Text(
                    "Всё упаковано по этой строке",
                    fontSize = 18.sp,
                    color = WmsColors.Success,
                    modifier = Modifier.padding(bottom = 24.dp),
                )
            }
        }
    }
}
