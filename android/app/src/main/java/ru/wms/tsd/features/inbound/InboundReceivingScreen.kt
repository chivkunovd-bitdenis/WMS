package ru.wms.tsd.features.inbound

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.UUID
import ru.wms.tsd.AppGraph
import ru.wms.tsd.ui.patterns.ConfirmSheet
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.LineProgress
import ru.wms.tsd.ui.patterns.LineProgressList
import ru.wms.tsd.ui.patterns.ScanPrompt
import ru.wms.tsd.ui.patterns.QtyInput
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.ScanTargetBar
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * B3. Приёмка товара — золотой экран проекта (T-07).
 * Все последующие рабочие экраны делаются по его образцу.
 */
@Composable
fun InboundReceivingScreen(
    requestId: String,
    onBack: () -> Unit,
    onOpenBoxes: () -> Unit,
    initialBoxId: String? = null,
) {
    val vm: InboundReceivingViewModel = viewModel(
        factory = InboundReceivingViewModel.Factory(UUID.fromString(requestId), AppGraph.apiProvider, initialBoxId),
    )
    val state by vm.state.collectAsState()

    // Подписка на сканер: активна только пока экран на переднем плане
    LaunchedEffect(Unit) {
        AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) }
    }

    // Возврат с экрана коробов — тихо перечитываем, чтобы подхватить новый короб
    LifecycleResumeEffect(Unit) {
        vm.reloadSilently()
        onPauseOrDispose { }
    }

    val request = state.request
    val lines = request?.lines.orEmpty()
    val boxes = request?.boxes.orEmpty()
    val totalExpected = lines.sumOf { it.expectedQty }
    val totalActual = lines.sumOf { effectiveActualQty(it, boxes, request?.status) }
    val openBox = boxes.firstOrNull { it.id == state.openBoxId }

    // Ручной ввод количества по строке (навал/немаркированный товар)
    var manualQtyLine by remember { mutableStateOf<ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut?>(null) }

    ScanScaffold(
        title = "Приёмка ${request?.displayNumber ?: request?.documentNumber ?: ""}".trim(),
        subtitle = request?.sellerName,
        flash = state.flash,
        onExit = onBack,
        progressDone = totalActual,
        progressTotal = totalExpected,
        primaryActionLabel = when {
            state.loading || state.loadError != null -> null
            openBox != null -> "Закрыть короб №${openBox.boxNumber}"
            else -> "Завершить пересчёт"
        },
        primaryActionEnabled = !state.completing,
        onPrimaryAction = {
            if (openBox != null) vm.requestCloseBox() else vm.requestComplete()
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
                // Зона контекста скана: какой короб открыт / режим без короба / приглашение
                when {
                    openBox != null -> ScanTargetBar(
                        text = "Короб №${openBox.boxNumber}",
                        hint = "Сканируйте товар — плюс одна штука в короб",
                        actionLabel = "Без короба",
                        onAction = { vm.setLooseMode(true) },
                    )
                    state.looseMode -> ScanTargetBar(
                        text = "Приёмка без короба",
                        hint = "Сканируйте товар",
                        actionLabel = "К коробам",
                        onAction = { vm.setLooseMode(false) },
                    )
                    else -> ScanPrompt(
                        icon = if (boxes.isEmpty()) Icons.Default.QrCodeScanner else Icons.Default.Inventory2,
                        text = "Отсканируйте штрихкод короба",
                        hint = if (boxes.isEmpty()) {
                            "В заявке пока нет коробов — создайте их на шаге приёмки по коробам или работайте без короба"
                        } else {
                            "Коробов в заявке: ${boxes.size}"
                        },
                    )
                }

                // «Приёмка без короба» — только в режиме ожидания. Доступ к коробам:
                // если короба есть — всегда (посмотреть ШК/переснять); создать короб —
                // только там, где сервер разрешает (иначе не показываем, чтобы не ловить ошибку).
                val canCreateBox = canCreateInboundBox(request?.status)
                val showBoxesButton = boxes.isNotEmpty() || canCreateBox
                if ((!state.looseMode && openBox == null) || showBoxesButton) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 8.dp),
                        horizontalArrangement = Arrangement.SpaceEvenly,
                    ) {
                        if (!state.looseMode && openBox == null) {
                            TextButton(onClick = { vm.setLooseMode(true) }) {
                                Text("Приёмка без короба", fontSize = 16.sp)
                            }
                        }
                        if (showBoxesButton) {
                            TextButton(onClick = onOpenBoxes) {
                                Text(
                                    if (boxes.isEmpty()) "Создать короб" else "Короба (${boxes.size})",
                                    fontSize = 16.sp,
                                )
                            }
                        }
                    }
                }

                LineProgressList(
                    lines = lines.map { ln ->
                        LineProgress(
                            id = ln.productId,
                            title = ln.skuCode,
                            subtitle = ln.productName,
                            done = effectiveActualQty(ln, boxes, request?.status),
                            total = ln.expectedQty,
                        )
                    },
                    activeId = state.activeProductId,
                    // Тап по строке — ручной ввод количества (когда сканировать нельзя)
                    onLineClick = { productId ->
                        manualQtyLine = lines.firstOrNull { it.productId == productId }
                    },
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
    }

    when (state.confirm) {
        "close_box" -> {
            val boxLines = openBox?.lines.orEmpty()
            ConfirmSheet(
                title = "Закрыть короб №${openBox?.boxNumber ?: ""}?",
                facts = listOf(
                    "Товаров в коробе: ${boxLines.sumOf { it.quantity }} шт (${boxLines.size} позиций)",
                ),
                confirmLabel = "Закрыть короб",
                onConfirm = vm::confirmCloseBox,
                onDismiss = vm::dismissConfirm,
            )
        }
    }

    // B4. Сводка перед завершением — полноэкранный обзор план/факт (вместо ConfirmSheet)
    if (state.confirm == "complete") {
        InboundCompleteSummary(
            displayNumber = request?.displayNumber ?: request?.documentNumber,
            sellerName = request?.sellerName,
            lines = lines,
            boxes = boxes,
            requestStatus = request?.status,
            completing = state.completing,
            onConfirm = { vm.confirmComplete(onDone = onBack) },
            onDismiss = vm::dismissConfirm,
        )
    }

    // Ручной ввод количества по строке. Если открыт короб — пишем В КОРОБ,
    // иначе — «без короба» (loose). Так же, как работает скан.
    manualQtyLine?.let { line ->
        val boxLineQty = openBox?.lines.orEmpty().firstOrNull { it.productId == line.productId }?.quantity ?: 0
        ManualQtySheet(
            line = line,
            boxNumber = openBox?.boxNumber,
            currentQty = if (openBox != null) boxLineQty else (line.actualQty ?: 0),
            onSave = { qty ->
                val box = openBox
                if (box != null) {
                    vm.setBoxLineQuantity(box.id, line.productId, qty)
                } else {
                    vm.setLineActualQty(line.id, line.productId, qty)
                }
                manualQtyLine = null
            },
            onDismiss = { manualQtyLine = null },
        )
    }
}

/**
 * Шторка ручного ввода фактического количества по строке приёмки. Нужна, когда
 * товар навалом или не промаркирован (сканировать по штуке нельзя). Задаёт
 * абсолютный факт «без короба» через PATCH .../actual.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ManualQtySheet(
    line: ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut,
    boxNumber: Int?,
    currentQty: Int,
    onSave: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var qty by remember(line.id, boxNumber) { mutableStateOf(currentQty) }
    // Куда пишем: в открытый короб или «без короба»
    val target = if (boxNumber != null) "в короб №$boxNumber" else "без короба"
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(line.skuCode, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WmsColors.TextPrimary)
            Text(
                line.productName,
                fontSize = 16.sp,
                color = WmsColors.TextSecondary,
                maxLines = 2,
            )
            Text("План: ${line.expectedQty} шт", fontSize = 16.sp, color = WmsColors.TextSecondary)
            QtyInput(
                value = qty,
                onValueChange = { qty = it },
                min = 0,
                maxHint = "Количество $target",
            )
            Button(
                onClick = { onSave(qty) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(WmsDimens.PrimaryButtonHeight)
                    .padding(bottom = 16.dp),
            ) {
                Text("Принято $qty шт $target", fontSize = 18.sp)
            }
        }
    }
}


