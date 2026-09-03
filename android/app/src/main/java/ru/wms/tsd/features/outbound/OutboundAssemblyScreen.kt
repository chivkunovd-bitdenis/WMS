package ru.wms.tsd.features.outbound

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.UUID
import ru.wms.tsd.AppGraph
import ru.wms.tsd.ui.patterns.ConfirmSheet
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.LineProgress
import ru.wms.tsd.ui.patterns.LineProgressList
import ru.wms.tsd.ui.patterns.ScanPrompt
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.ScanTargetBar
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * D2+D3. Сборка отгрузки: скан ячейки (опц.) → скан товара → в текущий короб.
 */
@Composable
fun OutboundAssemblyScreen(
    requestId: String,
    onBack: () -> Unit,
) {
    val vm: OutboundAssemblyViewModel = viewModel(
        factory = OutboundAssemblyViewModel.Factory(UUID.fromString(requestId), AppGraph.apiProvider),
    )
    val state by vm.state.collectAsState()

    LaunchedEffect(Unit) {
        AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) }
    }

    val request = state.request
    val lines = request?.lines.orEmpty()
    val boxes = request?.boxes.orEmpty()
    val totalPlan = lines.sumOf { it.quantity }
    val totalPicked = lines.sumOf { it.pickedQty ?: 0 }
    val allCollected = totalPlan > 0 && lines.all { (it.pickedQty ?: 0) >= it.quantity }
    val currentBox = boxes.firstOrNull { it.id == state.currentBoxId }
    val packaging = state.packaging
    // Фаза упаковки: всё собрано, задача упаковки существует и ещё не завершена
    val packagingPhase = allCollected && packaging != null && packaging.status != "done"

    ScanScaffold(
        title = "Сборка ${request?.displayNumber ?: request?.documentNumber ?: ""}".trim(),
        subtitle = request?.sellerName,
        flash = state.flash,
        onExit = onBack,
        progressDone = totalPicked,
        progressTotal = totalPlan,
        primaryActionLabel = when {
            state.loading || state.loadError != null -> null
            currentBox != null -> "Закрыть короб"
            !allCollected -> null
            packagingPhase -> if (packaging?.isComplete == true) "Завершить упаковку" else null
            else -> "Отгрузить"
        },
        primaryActionEnabled = !state.shipping && !state.packBusy,
        onPrimaryAction = {
            when {
                currentBox != null -> vm.requestCloseBox()
                packagingPhase -> vm.requestCompletePackaging()
                else -> vm.requestShip()
            }
        },
    ) {
        when {
            state.loading -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) { CircularProgressIndicator() }

            state.loadError != null -> FullScreenError(state.loadError!!, onRetry = vm::load)

            else -> Column(modifier = Modifier.fillMaxSize()) {
                if (allCollected && packaging != null && currentBox == null) {
                    // Сбор завершён, короб закрыт — экран переключается на упаковку (гейт перед отгрузкой)
                    Text(
                        "Собрано $totalPicked из $totalPlan ✓",
                        fontSize = 16.sp,
                        color = WmsColors.Success,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                    PackagingPanel(
                        task = packaging,
                        onLineClick = { vm.openPackLine(it.id) },
                        modifier = Modifier.weight(1f),
                    )
                    return@Column
                }
                if (currentBox != null) {
                    val boxQty = currentBox.lines.sumOf { it.quantity }
                    ScanTargetBar(
                        text = "Короб · $boxQty шт",
                        hint = state.locationCode
                            ?.let { "Ячейка $it — сканируйте товар" }
                            ?: "Сканируйте ячейку, затем товар",
                        actionLabel = null,
                        onAction = {},
                    )
                } else {
                    ScanPrompt(
                        icon = Icons.Default.LocalShipping,
                        text = "Создайте короб для сборки",
                        hint = if (boxes.isEmpty()) null else "или выберите открытый короб из списка",
                    )
                    // Открытые короба для продолжения работы
                    boxes.filter { it.closedAt == null }.forEach { box ->
                        Surface(
                            shape = RoundedCornerShape(WmsDimens.CornerRadius),
                            color = WmsColors.Surface,
                            shadowElevation = 1.dp,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 4.dp)
                                .clickable { vm.selectBox(box.id) },
                        ) {
                            Row(
                                modifier = Modifier.padding(16.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    "Короб ${box.boxPreset}",
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = WmsColors.TextPrimary,
                                    modifier = Modifier.weight(1f),
                                )
                                Text(
                                    "${box.lines.sumOf { it.quantity }} шт",
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = WmsColors.Primary,
                                )
                            }
                        }
                    }
                    FilledTonalButton(
                        onClick = vm::createBox,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp)
                            .height(WmsDimens.TouchTargetMin),
                    ) { Text("+ Добавить короб", fontSize = 18.sp) }
                }

                LineProgressList(
                    lines = lines.map { ln ->
                        LineProgress(
                            id = ln.productId,
                            title = ln.skuCode,
                            subtitle = ln.productName,
                            done = ln.pickedQty ?: 0,
                            total = ln.quantity,
                        )
                    },
                    activeId = state.activeProductId,
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
    }

    when (state.confirm) {
        "close_box" -> {
            val boxQty = currentBox?.lines.orEmpty().sumOf { it.quantity }
            ConfirmSheet(
                title = "Закрыть короб?",
                facts = listOf("Товаров в коробе: $boxQty шт"),
                confirmLabel = "Закрыть короб",
                onConfirm = vm::confirmCloseBox,
                onDismiss = vm::dismissConfirm,
            )
        }
        "ship" -> {
            val openBoxes = boxes.count { it.closedAt == null }
            ConfirmSheet(
                title = "Отгрузить?",
                facts = buildList {
                    add("Собрано $totalPicked из $totalPlan шт")
                    add("Коробов: ${boxes.size}")
                    if (openBoxes > 0) add("Внимание: $openBoxes коробов не закрыто")
                    if (packaging != null && packaging.status != "done") add("Внимание: упаковка не завершена")
                    add("Товар спишется с остатков")
                },
                confirmLabel = "Отгрузить",
                destructive = true,
                onConfirm = { vm.confirmShip(onDone = onBack) },
                onDismiss = vm::dismissConfirm,
            )
        }
        // Сервер отклонил ship из-за расхождения план/факт — нужно явное подтверждение
        "ship_discrepancy" -> ConfirmSheet(
            title = "Собрано не по плану",
            facts = buildList {
                add("Собрано $totalPicked из $totalPlan шт")
                lines.filter { (it.pickedQty ?: 0) != it.quantity }.take(3).forEach {
                    add("${it.skuCode}: ${it.pickedQty ?: 0} из ${it.quantity}")
                }
                add("Отгрузить с расхождением?")
            },
            confirmLabel = "Отгрузить с расхождением",
            destructive = true,
            onConfirm = { vm.confirmShip(onDone = onBack, acknowledgeDiscrepancy = true) },
            onDismiss = vm::dismissConfirm,
        )
        "complete_packaging" -> {
            val pkgLines = packaging?.lines.orEmpty()
            val markingProblems = pkgLines.filter { markingIncomplete(it) }
            ConfirmSheet(
                title = "Завершить упаковку?",
                facts = buildList {
                    add("Упаковано ${pkgLines.sumOf { it.qtyDone }} из ${pkgLines.sumOf { it.qtyTotal }} шт")
                    if (markingProblems.isNotEmpty()) {
                        add("⚠ ЧЗ не напечатаны: ${markingProblems.joinToString { it.skuCode }}")
                        add("Печать — на рабочем месте упаковки (веб)")
                    }
                },
                confirmLabel = "Завершить упаковку",
                destructive = markingProblems.isNotEmpty(),
                onConfirm = vm::confirmCompletePackaging,
                onDismiss = vm::dismissConfirm,
            )
        }
    }

    val packLine = state.packLine
    if (packLine != null) {
        PackLineSheet(
            line = packLine,
            busy = state.packBusy,
            onConfirmFromShelf = vm::confirmPackedFromShelf,
            onPack = vm::submitPack,
            onDismiss = vm::dismissPackLine,
        )
    }
}
