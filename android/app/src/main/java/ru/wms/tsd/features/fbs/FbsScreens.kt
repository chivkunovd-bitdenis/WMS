package ru.wms.tsd.features.fbs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AllInbox
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import ru.wms.tsd.AppGraph
import ru.wms.tsd.core.api.fbs.FbsBox
import ru.wms.tsd.core.api.fbs.FbsDeliveryCheck
import ru.wms.tsd.core.api.fbs.FbsSupplySummary
import ru.wms.tsd.ui.patterns.ConfirmSheet
import ru.wms.tsd.ui.patterns.EmptyState
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.ListSkeleton
import ru.wms.tsd.ui.patterns.ScanFlash
import ru.wms.tsd.ui.patterns.ScanPrompt
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.ScanTargetBar
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

@Composable
fun FbsSupplyListScreen(
    onBack: () -> Unit,
    onOpenSupply: (String) -> Unit,
) {
    val vm: FbsSupplyListViewModel = viewModel(
        factory = ApiFactory({ FbsSupplyListViewModel(it) }, AppGraph.apiProvider),
    )
    val state by vm.state.collectAsState()
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }

    ScanScaffold(title = "WB FBS", flash = ScanFlash.None, onExit = onBack, cameraScanner = false) {
        when {
            state.loading -> ListSkeleton()
            state.error != null -> FullScreenError(state.error!!, onRetry = { vm.load(initial = true) })
            state.active.isEmpty() && state.delivery.isEmpty() -> EmptyState("Нет поставок WB FBS в работе")
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (state.active.isNotEmpty()) {
                    item { SectionTitle("На складе") }
                    items(state.active, key = { it.id }) { FbsSupplyCard(it, onOpenSupply) }
                }
                if (state.delivery.isNotEmpty()) {
                    item { SectionTitle("В доставке") }
                    items(state.delivery, key = { it.id }) { FbsSupplyCard(it, onOpenSupply) }
                }
                item { Spacer(Modifier.height(12.dp)) }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        fontSize = 18.sp,
        fontWeight = FontWeight.Bold,
        color = WmsColors.TextPrimary,
        modifier = Modifier.padding(top = 14.dp, bottom = 2.dp),
    )
}

@Composable
private fun FbsSupplyCard(supply: FbsSupplySummary, onOpen: (String) -> Unit) {
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clickable { onOpen(supply.id) },
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    supply.name,
                    fontSize = 19.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = WmsColors.TextPrimary,
                    modifier = Modifier.weight(1f),
                )
                StatusPill(fbsStatusRu(supply.status), fbsStatusColor(supply.status))
            }
            Text(
                listOfNotNull(supply.seller.name, supply.wbWarehouse.name).joinToString(" · "),
                fontSize = 15.sp,
                color = WmsColors.TextSecondary,
            )
            Text(
                "${ruCount(supply.ordersCount, "заказ", "заказа", "заказов")} · " +
                    "${supply.unitsCount} шт · ${ruCount(supply.boxesCount, "короб", "короба", "коробов")}",
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                color = WmsColors.TextPrimary,
            )
        }
    }
}

@Composable
private fun StatusPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(50), color = color.copy(alpha = 0.14f)) {
        Text(text, color = color, fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(9.dp, 5.dp))
    }
}

@Composable
fun FbsWorkspaceScreen(
    supplyId: String,
    onBack: () -> Unit,
    onPicking: () -> Unit,
    onPacking: () -> Unit,
    onHandoff: () -> Unit,
) {
    val vm: FbsWorkspaceViewModel = viewModel(
        factory = SupplyApiFactory(supplyId, AppGraph.apiProvider, ::FbsWorkspaceViewModel),
    )
    val state by vm.state.collectAsState()
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }
    val workspace = state.workspace

    ScanScaffold(
        title = workspace?.supply?.name ?: "Поставка WB FBS",
        subtitle = workspace?.supply?.seller?.name,
        flash = state.flash,
        onExit = onBack,
        cameraScanner = false,
        primaryActionLabel = if (workspace?.supply?.status == "draft") "Начать работу" else null,
        primaryActionEnabled = !state.busy,
        onPrimaryAction = vm::startWork,
    ) {
        when {
            state.loading -> Loading()
            state.error != null -> FullScreenError(state.error!!, onRetry = vm::load)
            workspace != null -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                val grew = (state.initialTotal ?: workspace.progress.total) < workspace.progress.total
                if (grew) {
                    item { AlertCard("Состав поставки вырос. Добавлены новые заказы — вернитесь в подбор.", WmsColors.Error) }
                } else if (workspace.progress.picked < workspace.progress.total) {
                    item { AlertCard("Есть несобранные заказы: ${workspace.progress.total - workspace.progress.picked} шт", WmsColors.Warning) }
                }
                item {
                    SupplyFactsCard(
                        destination = workspace.supply.wbWarehouse.name ?: "Склад WB не указан",
                        deadline = workspace.supply.nearestDeadlineAt,
                        orders = workspace.orders.size,
                        units = workspace.progress.total,
                    )
                }
                item {
                    ProgressCard(
                        picked = workspace.progress.picked,
                        packed = workspace.progress.packed,
                        total = workspace.progress.total,
                        boxes = workspace.boxes.size,
                    )
                }
                item {
                    ActionCard(
                        title = "1. Подбор",
                        subtitle = "${workspace.progress.picked} из ${workspace.progress.total} шт",
                        icon = Icons.Default.Place,
                        onClick = onPicking,
                    )
                }
                item {
                    ActionCard(
                        title = "2. Упаковка",
                        subtitle = "${workspace.progress.packed} из ${workspace.progress.total} шт",
                        icon = Icons.Default.Inventory2,
                        onClick = onPacking,
                    )
                }
                item {
                    ActionCard(
                        title = "3. Короба и передача",
                        subtitle = "Коробов: ${workspace.boxes.size} · ${fbsStatusRu(workspace.supply.status)}",
                        icon = Icons.Default.LocalShipping,
                        onClick = onHandoff,
                    )
                }
                item {
                    Text(
                        "Этапы не заперты: оператор может открыть любой и вернуться назад.",
                        color = WmsColors.TextSecondary,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(4.dp, 8.dp, 4.dp, 16.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun SupplyFactsCard(destination: String, deadline: String, orders: Int, units: Int) {
    Surface(shape = RoundedCornerShape(WmsDimens.CornerRadius), color = WmsColors.Surface, shadowElevation = 1.dp) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Wildberries · $destination", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text("Срок сдачи: ${deadline.replace('T', ' ').take(16)}", fontSize = 14.sp, color = WmsColors.TextSecondary)
            Text("Заказов: $orders · Товаров: $units", fontSize = 14.sp, color = WmsColors.TextSecondary)
        }
    }
}

@Composable
private fun ProgressCard(picked: Int, packed: Int, total: Int, boxes: Int) {
    Surface(shape = RoundedCornerShape(WmsDimens.CornerRadius), color = WmsColors.Surface, shadowElevation = 1.dp) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceAround) {
            Metric("Собрано", "$picked/$total")
            Metric("Упаковано", "$packed/$total")
            Metric("Короба", boxes.toString())
        }
    }
}

@Composable private fun Metric(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WmsColors.Primary)
        Text(label, fontSize = 13.sp, color = WmsColors.TextSecondary)
    }
}

@Composable
private fun ActionCard(title: String, subtitle: String, icon: ImageVector, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = WmsColors.Primary)
            Column(Modifier.padding(start = 16.dp).weight(1f)) {
                Text(title, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                Text(subtitle, fontSize = 15.sp, color = WmsColors.TextSecondary)
            }
            Text("›", fontSize = 30.sp, color = WmsColors.Primary)
        }
    }
}

@Composable
private fun AlertCard(message: String, color: Color) {
    Surface(shape = RoundedCornerShape(WmsDimens.CornerRadius), color = color) {
        Text(message, color = WmsColors.Surface, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp))
    }
}

@Composable
fun FbsPickingScreen(supplyId: String, onBack: () -> Unit) {
    val vm: FbsPickingViewModel = viewModel(
        factory = SupplyApiFactory(supplyId, AppGraph.apiProvider, ::FbsPickingViewModel),
    )
    val state by vm.state.collectAsState()
    LaunchedEffect(vm) { AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) } }
    val progress = state.workspace?.progress

    ScanScaffold(
        title = "Подбор WB FBS",
        subtitle = state.workspace?.supply?.name,
        flash = state.flash,
        onExit = onBack,
        progressDone = progress?.picked,
        progressTotal = progress?.total,
    ) {
        when {
            state.loading -> Loading()
            state.error != null -> FullScreenError(state.error!!, onRetry = vm::load)
            state.location == null -> ScanPrompt(
                icon = Icons.Default.Place,
                text = "Сканируйте ячейку",
                hint = "После ячейки сканируйте товары из неё",
            )
            else -> Column(Modifier.fillMaxSize()) {
                ScanTargetBar(
                    text = "Ячейка ${state.location!!.code}",
                    hint = if (state.busy) "Проверяем скан…" else "Сканируйте товар",
                    actionLabel = "Сменить",
                    onAction = vm::clearLocation,
                )
                LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (state.location!!.expectedProducts.isEmpty()) {
                        item { AlertCard("В этой ячейке больше нет товаров для поставки", WmsColors.Success) }
                    } else {
                        items(state.location!!.expectedProducts, key = { it.productId }) { product ->
                            Surface(shape = RoundedCornerShape(10.dp), color = WmsColors.Surface) {
                                Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f)) {
                                        Text(product.name, fontSize = 17.sp, fontWeight = FontWeight.Medium)
                                        product.barcode?.let { Text(it, fontSize = 13.sp, color = WmsColors.TextSecondary) }
                                    }
                                    Text("${product.remainingQty} шт", fontSize = 19.sp, fontWeight = FontWeight.Bold, color = WmsColors.Primary)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun FbsPackingScreen(supplyId: String, onBack: () -> Unit) {
    val vm: FbsPackingViewModel = viewModel(
        factory = SupplyApiFactory(supplyId, AppGraph.apiProvider, ::FbsPackingViewModel),
    )
    val state by vm.state.collectAsState()
    LaunchedEffect(vm) { AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) } }
    val progress = state.workspace?.progress

    ScanScaffold(
        title = "Упаковка WB FBS",
        subtitle = state.workspace?.supply?.name,
        flash = state.flash,
        onExit = onBack,
        progressDone = progress?.packed,
        progressTotal = progress?.total,
    ) {
        when {
            state.loading -> Loading()
            state.error != null -> FullScreenError(state.error!!, onRetry = vm::load)
            state.task == null -> EmptyState("Задача упаковки ещё не создана. Вернитесь на поставку и нажмите «Начать работу».")
            else -> Column(Modifier.fillMaxSize()) {
                Surface(color = WmsColors.Primary.copy(alpha = 0.10f), modifier = Modifier.fillMaxWidth()) {
                    Text(
                        "1. Сканируйте стикер WB или товар  2. Прикрепите стикер  3. Дождитесь подтверждения сервера",
                        color = WmsColors.Primary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.padding(12.dp),
                    )
                }
                ScanTargetBar(
                    text = "Сканируйте стикер заказа или товар",
                    hint = if (state.busy) "Записываем упаковку…" else "Сервер подтвердит каждый скан",
                    actionLabel = null,
                    onAction = {},
                )
                LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.task!!.lines, key = { it.id }) { line ->
                        Surface(shape = RoundedCornerShape(10.dp), color = WmsColors.Surface, shadowElevation = 1.dp) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(line.productName, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                                Text("${line.skuCode} · ${line.qtyDone} из ${line.qtyTotal}", color = WmsColors.TextSecondary)
                                line.packagingInstructions?.takeIf { it.isNotBlank() }?.let {
                                    AlertCard(it, WmsColors.Warning)
                                }
                                if (!line.isComplete) {
                                    FilledTonalButton(
                                        onClick = { vm.packOne(line.id) },
                                        enabled = !state.busy,
                                        modifier = Modifier.fillMaxWidth().height(WmsDimens.TouchTargetMin),
                                    ) { Text("Упаковать 1 шт", fontSize = 17.sp) }
                                } else {
                                    Text("Упаковано ✓", color = WmsColors.Success, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun FbsHandoffScreen(supplyId: String, onBack: () -> Unit) {
    val vm: FbsHandoffViewModel = viewModel(
        factory = SupplyApiFactory(supplyId, AppGraph.apiProvider, ::FbsHandoffViewModel),
    )
    val state by vm.state.collectAsState()
    LaunchedEffect(vm) { AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) } }
    val workspace = state.workspace

    ScanScaffold(
        title = "Короба и передача",
        subtitle = workspace?.supply?.name,
        flash = state.flash,
        onExit = onBack,
        progressDone = workspace?.boxes?.sumOf { it.assignedOrderIds.size },
        progressTotal = workspace?.orders?.size,
        primaryActionLabel = when {
            workspace == null -> null
            workspace.supply.status == "in_delivery" -> "Обновить статус WB"
            state.preflight?.canDeliver == true -> "Передать в WB"
            state.preflight != null -> "Повторить проверку"
            else -> "Проверить передачу"
        },
        primaryActionEnabled = !state.busy,
        onPrimaryAction = {
            when {
                workspace?.supply?.status == "in_delivery" -> vm.syncTracking()
                state.preflight?.canDeliver == true -> vm.requestDeliver()
                else -> vm.checkDelivery()
            }
        },
    ) {
        when {
            state.loading -> Loading()
            state.error != null -> FullScreenError(state.error!!, onRetry = vm::load)
            workspace != null -> LazyColumn(
                Modifier.fillMaxSize().padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (workspace.supply.status != "in_delivery") {
                    item {
                        ScanPrompt(
                            icon = Icons.Default.AllInbox,
                            text = state.selectedBox?.let { "Короб №${it.boxNumber} выбран" } ?: "Сканируйте короб",
                            hint = state.selectedBox?.let { "Теперь сканируйте стикеры заказов" } ?: "или выберите его ниже",
                        )
                    }
                }
                items(workspace.boxes, key = { it.id }) { box ->
                    BoxCard(
                        box,
                        selected = state.selectedBox?.id == box.id,
                        onClick = { if (workspace.supply.status != "in_delivery") vm.selectBox(box) },
                    )
                }
                if (workspace.supply.status != "in_delivery") {
                    item {
                        FilledTonalButton(
                            onClick = vm::createBox,
                            enabled = !state.busy,
                            modifier = Modifier.fillMaxWidth().height(WmsDimens.TouchTargetMin),
                        ) { Text("+ Добавить короб", fontSize = 18.sp) }
                    }
                }
                if (workspace.supply.status == "in_delivery") {
                    item { AlertCard("Поставка передана в WB", WmsColors.Success) }
                } else {
                    state.preflight?.let { preflight ->
                        items(preflight.checks, key = { "${it.code}:${it.orderId}" }) { check -> DeliveryCheckCard(check) }
                    }
                }
                item { Spacer(Modifier.height(12.dp)) }
            }
        }
    }

    if (state.confirmDeliver) {
        val warnings = state.preflight?.checks.orEmpty().count { !it.ok && it.severity != "blocker" }
        ConfirmSheet(
            title = "Передать поставку в WB?",
            facts = buildList {
                add("Заказов: ${workspace?.orders?.size ?: 0}")
                add("Коробов: ${workspace?.boxes?.size ?: 0}")
                if (warnings > 0) add("Предупреждений: $warnings")
            },
            confirmLabel = "Передать в WB",
            destructive = warnings > 0,
            onConfirm = vm::deliver,
            onDismiss = vm::dismissDeliver,
        )
    }
}

@Composable
private fun BoxCard(box: FbsBox, selected: Boolean, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = if (selected) WmsColors.Primary.copy(alpha = 0.12f) else WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Inventory2, contentDescription = null, tint = WmsColors.Primary)
            Column(Modifier.padding(start = 12.dp).weight(1f)) {
                Text("Короб №${box.boxNumber}", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(box.barcode, fontSize = 13.sp, color = WmsColors.TextSecondary)
            }
            Text(
                ruCount(box.assignedOrderIds.size, "заказ", "заказа", "заказов"),
                fontWeight = FontWeight.Bold,
                color = WmsColors.Primary,
            )
        }
    }
}

@Composable
private fun DeliveryCheckCard(check: FbsDeliveryCheck) {
    val color = when (check.severity) {
        "blocker" -> WmsColors.Error
        "warning" -> WmsColors.Warning
        else -> if (check.ok) WmsColors.Success else WmsColors.TextSecondary
    }
    Surface(shape = RoundedCornerShape(10.dp), color = color.copy(alpha = 0.12f)) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.CheckCircle, contentDescription = null, tint = color)
            Text(check.message, color = WmsColors.TextPrimary, fontSize = 15.sp, modifier = Modifier.padding(start = 10.dp))
        }
    }
}

@Composable private fun Loading() {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        CircularProgressIndicator()
    }
}

private fun fbsStatusRu(status: String): String = when (status) {
    "draft" -> "Черновик"
    "assembling" -> "В работе"
    "packed" -> "Собрано"
    "in_delivery" -> "В доставке"
    "delivered" -> "Доставлено"
    else -> status
}

private fun fbsStatusColor(status: String): Color = when (status) {
    "in_delivery", "delivered" -> WmsColors.Success
    "packed" -> WmsColors.Warning
    else -> WmsColors.Primary
}

private fun ruCount(value: Int, one: String, few: String, many: String): String {
    val lastTwo = value % 100
    val word = when {
        lastTwo in 11..14 -> many
        value % 10 == 1 -> one
        value % 10 in 2..4 -> few
        else -> many
    }
    return "$value $word"
}
