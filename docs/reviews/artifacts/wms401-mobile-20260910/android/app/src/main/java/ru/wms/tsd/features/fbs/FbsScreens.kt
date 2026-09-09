package ru.wms.tsd.features.fbs

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import ru.wms.tsd.AppGraph
import ru.wms.tsd.core.api.fbs.*
import ru.wms.tsd.ui.patterns.ScanScaffold

internal fun displayTime(value: String): String = runCatching {
    DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm").withZone(ZoneId.systemDefault()).format(OffsetDateTime.parse(value).toInstant())
}.getOrDefault(value)

@Composable private fun fbsViewModel(): FbsViewModel = viewModel(factory = FbsViewModel.Factory(AppGraph.apiProvider))
@Composable private fun ErrorPanel(state: FbsState, vm: FbsViewModel) {
    state.error?.let {
        Column(Modifier.fillMaxWidth().background(Color(0xffffebee)).padding(12.dp)) {
            Text(it, color = Color(0xff9c1b24))
            Row { TextButton(onClick = vm::retry) { Text("Повторить") }; TextButton(onClick = vm::dismissError) { Text("Закрыть") } }
        }
    }
    if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
}

@Composable fun FbsOrdersScreen(onBack: () -> Unit, onOpen: (String) -> Unit) {
    val vm = fbsViewModel(); val state by vm.state.collectAsState()
    var createDialog by remember { mutableStateOf(false) }
    var chooseSupply by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var delivery by remember { mutableStateOf("warehouse_sc") }
    LifecycleResumeEffect(Unit) { vm.loadOrders(); onPauseOrDispose {} }
    ScanScaffold(title = "FBS · Заказы", flash = state.flash, onExit = onBack, cameraScanner = false) {
        Column(Modifier.fillMaxSize()) {
            ErrorPanel(state, vm)
            if (state.selected.isNotEmpty()) Row(Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { createDialog = true }, enabled = !state.busy, modifier = Modifier.weight(1f)) { Text("Новая поставка (${state.selected.size})") }
                OutlinedButton(onClick = { chooseSupply = true }, enabled = !state.busy, modifier = Modifier.weight(1f)) { Text("В поставку") }
            }
            LazyColumn(Modifier.weight(1f).padding(horizontal = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Text("Все заказы", fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 8.dp)) }
                items(sortedOrders(state.orders), key = { it.id }) { order ->
                    OrderCard(order, state.selected.contains(order.id), onClick = {
                        if (order.supplyId != null) onOpen(order.supplyId) else vm.toggle(order)
                    }, selectable = order.status == "new" && order.supplyId == null)
                }
                if (state.cursor != null) item { OutlinedButton(onClick = { vm.loadOrders(true) }, enabled = !state.busy, modifier = Modifier.fillMaxWidth()) { Text("Загрузить ещё") } }
                if (state.orders.isEmpty() && !state.busy) item { Text("Заказов пока нет", modifier = Modifier.padding(16.dp)) }
                if (state.supplies.isNotEmpty()) item { Text("Поставки в работе", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp)) }
                items(state.supplies, key = { "supply:${it.id}" }) { supply ->
                    OutlinedButton(onClick = { onOpen(supply.id) }, modifier = Modifier.fillMaxWidth()) { Text("${supply.name} · ${supply.ordersCount} заказов") }
                }
            }
        }
    }
    if (createDialog) AlertDialog(onDismissRequest = { createDialog = false }, title = { Text("Создать поставку") }, text = {
        Column { OutlinedTextField(name, { name = it }, label = { Text("Название") });
            Row { RadioButton(delivery == "warehouse_sc", { delivery = "warehouse_sc" }); Text("Склад / СЦ", modifier = Modifier.padding(top = 12.dp)) }
            Row { RadioButton(delivery == "pvz", { delivery = "pvz" }); Text("ПВЗ", modifier = Modifier.padding(top = 12.dp)) }
        }
    }, confirmButton = { Button(onClick = { createDialog = false; vm.create(name, delivery, onOpen) }, enabled = name.isNotBlank()) { Text("Создать") } }, dismissButton = { TextButton(onClick = { createDialog = false }) { Text("Отмена") } })
    if (chooseSupply) AlertDialog(onDismissRequest = { chooseSupply = false }, title = { Text("Выберите поставку") }, text = {
        LazyColumn { items(state.supplies) { supply -> TextButton(onClick = { chooseSupply = false; vm.addTo(supply.id, onOpen) }) { Text(supply.name) } } }
    }, confirmButton = { TextButton(onClick = { chooseSupply = false }) { Text("Закрыть") } })
}

@Composable private fun OrderCard(order: FbsOrder, selected: Boolean = false, onClick: () -> Unit = {}, selectable: Boolean = false, content: @Composable ColumnScope.() -> Unit = {}) {
    val color = when {
        order.pick.status == "picked" -> Color(0xffe5f4e9)
        isDeadlineNear(order.deadlineAt) -> Color(0xffffebee)
        else -> MaterialTheme.colorScheme.surface
    }
    Surface(color = color, tonalElevation = 1.dp, shape = MaterialTheme.shapes.medium, modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (selectable) Checkbox(selected, { onClick() })
                AsyncImage(order.product.imageUrl, order.product.name, modifier = Modifier.size(66.dp))
                Column(Modifier.weight(1f).padding(start = 10.dp)) {
                    Text("WB ${order.wbOrderId}", fontWeight = FontWeight.Bold, fontSize = 22.sp)
                    Text(order.product.name, fontSize = 17.sp)
                    Text(order.product.sellerArticle ?: order.product.sku.orEmpty(), fontSize = 14.sp)
                }
            }
            Text("ШК: ${order.product.barcode ?: "не указан"}")
            Text("Поступил: ${displayTime(order.createdAt)}")
            Text("Отгрузить до: ${displayTime(order.deadlineAt)}", fontWeight = FontWeight.Medium)
            if (order.pick.status == "picked") Text("Подобран · ${order.pick.locationCode.orEmpty()}", color = Color(0xff176b31))
            content()
        }
    }
}

@Composable fun FbsSupplyScreen(supplyId: String, onBack: () -> Unit, onStep: (String) -> Unit) {
    val vm = fbsViewModel(); val state by vm.state.collectAsState()
    LifecycleResumeEffect(supplyId) { vm.loadSupply(supplyId); onPauseOrDispose {} }
    ScanScaffold(title = "Поставка FBS", flash = state.flash, onExit = onBack, cameraScanner = false) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            ErrorPanel(state, vm)
            state.workspace?.let { ws ->
                Text(ws.supply.name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text("${ws.orders.size} заказов · Подобрано ${ws.progress.picked} · Упаковано ${ws.progress.packed}")
                for ((mode, label) in listOf("pick" to "Подбор", "pack" to "Упаковка и этикетки", "boxes" to "Короба")) {
                    Button(onClick = { onStep(mode) }, modifier = Modifier.fillMaxWidth().height(72.dp)) { Text(label, fontSize = 20.sp) }
                }
                if (ws.supply.marketplace == "wb") {
                    if (ws.deliveryConfirmed()) {
                        Text("Поставка передана в WB", color = Color(0xff176b31), fontWeight = FontWeight.Bold)
                        OutlinedButton(onClick = vm::syncDelivery, enabled = !state.busy, modifier = Modifier.fillMaxWidth()) { Text("Обновить статус WB") }
                    } else {
                        if (state.pendingDelivery != null) Text("Результат передачи пока неизвестен. Проверьте результат перед новой попыткой.")
                        OutlinedButton(onClick = vm::openDeliveryConfirmation, enabled = !state.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) {
                            Text(if (state.pendingDelivery != null) "Проверить результат передачи" else "Передать поставку в WB", fontSize = 20.sp)
                        }
                    }
                }
            }
        }
    }
    if (state.deliveryConfirmationOpen) AlertDialog(
        onDismissRequest = vm::cancelDelivery,
        title = { Text("Передать поставку в WB?") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("После передачи поставку нельзя будет отменить или вернуть в работу.")
                if (state.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text("Проверяем поставку…") }
                state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                state.deliveryPreflight?.let { preflight ->
                    for (check in preflight.checks.filter { it.severity in setOf("blocker", "warning") }) {
                        val order = state.workspace?.orders?.firstOrNull { it.id == check.orderId }
                        Text(check.message + (order?.let { " (WB ${it.wbOrderId})" } ?: ""), color = if (check.severity == "blocker") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
                    }
                    if (preflight.cancelledOrders.isNotEmpty()) {
                        Text("Отменённые заказы: выньте товары из коробов. Они будут исключены из поставки.", fontWeight = FontWeight.Bold)
                        for (order in preflight.cancelledOrders) {
                            Text(listOfNotNull("WB ${order.wbOrderId}", order.article, order.productName).joinToString(" · "))
                            Text(order.boxes.joinToString { "Короб ${it.boxNumber} (${it.boxBarcode})" }.ifEmpty { "Короб не назначен" })
                        }
                    }
                    if (!preflight.canDeliver) Text("Передача сейчас недоступна. Исправьте указанные причины и повторите проверку.")
                }
                if (!state.busy) TextButton(onClick = vm::openDeliveryConfirmation) { Text("Проверить ещё раз") }
            }
        },
        dismissButton = { TextButton(onClick = vm::cancelDelivery, enabled = !state.busy) { Text("Не передавать") } },
        confirmButton = { Button(onClick = vm::confirmDelivery, enabled = !state.busy && state.deliveryPreflight?.canDeliver != false) {
            Text(if (state.deliveryPreflight?.cancelledOrders?.isNotEmpty() == true) "Товары вынуты — передать" else "Передать в WB")
        } },
    )
}

@Composable fun FbsOperationScreen(supplyId: String, mode: String, onBack: () -> Unit) {
    val vm = fbsViewModel(); val state by vm.state.collectAsState(); val context = LocalContext.current
    val encoder = remember { context.assets.open("bwip-js-min.js").bufferedReader().use { it.readText() } }
    var printing by remember { mutableStateOf<List<String>?>(null) }
    var editing by remember { mutableStateOf<Triple<FbsBox, String, Int>?>(null) }
    LifecycleResumeEffect(supplyId) { vm.loadSupply(supplyId); onPauseOrDispose {} }
    LaunchedEffect(mode) { AppGraph.scannerManager.scans.collect { vm.scan(mode, it.barcode) } }
    LaunchedEffect(state.printDocument) { state.printDocument?.let { printLabels(context, it); vm.clearPrint() } }
    val workspace = state.workspace
    ScanScaffold(title = when (mode) { "pick" -> "Подбор FBS"; "pack" -> "Упаковка FBS"; else -> "Короба FBS" }, flash = state.flash, onExit = onBack) {
        Column(Modifier.fillMaxSize()) {
            ErrorPanel(state, vm)
            if (mode == "pick") Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(state.source?.let { it.containerCode ?: it.locationCode }.let { if (it == null) "Сканируйте источник или товар" else "Источник: $it" }, modifier = Modifier.weight(1f))
                TextButton(onClick = vm::clearSource, enabled = !state.busy) { Text("Сменить") }
            }
            if (mode == "pack") {
                Text(state.kizOrder?.let { "Заказ WB ${it.wbOrderId}: сканируйте ЧЗ" } ?: "QR заказа → код ЧЗ", modifier = Modifier.padding(10.dp), fontWeight = FontWeight.Bold)
                state.kizResult?.let { Text(it, modifier = Modifier.padding(horizontal = 10.dp)) }
                Row(Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { vm.printOrders(encoder, workspace?.orders.orEmpty().map { it.id }, 0, 0, true) }, enabled = !state.busy) { Text("Все QR") }
                    Button(onClick = { printing = workspace?.orders.orEmpty().map { it.id } }, enabled = !state.busy) { Text("Печать всего") }
                }
            }
            if (mode == "boxes") Row(Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = vm::createBox, enabled = !state.busy) { Text("Новый короб") }
                OutlinedButton(onClick = { vm.printBoxes(encoder, workspace?.boxes.orEmpty().map { it.id }) }, enabled = !state.busy) { Text("Все QR WB") }
            }
            LazyColumn(Modifier.weight(1f).padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (mode != "boxes") items(workspace?.orders.orEmpty().sortedWith(compareBy<FbsOrder> { it.pick.status == "picked" }.thenBy { it.createdAt }), key = { it.id }) { order ->
                    OrderCard(order) {
                        if (mode == "pack") {
                            Text(order.wbOrderId.toString().takeLast(4), fontSize = 36.sp, fontWeight = FontWeight.Black)
                            Button(onClick = { printing = listOf(order.id) }, enabled = !state.busy, modifier = Modifier.fillMaxWidth().height(56.dp)) { Text("Печатать этикетки", fontSize = 20.sp) }
                            OutlinedButton(onClick = { vm.packOrder(order) }, enabled = !state.busy && order.pack.status != "packed", modifier = Modifier.fillMaxWidth()) { Text(if (order.pack.status == "packed") "Упакован" else "Отметить упакованным") }
                        }
                    }
                }
                if (mode == "boxes") items(workspace?.boxes.orEmpty(), key = { it.id }) { box ->
                    Surface(color = if (state.selectedBoxId == box.id) Color(0xffe5f4e9) else MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
                        Column(Modifier.padding(12.dp)) {
                            Text("Короб №${box.boxNumber} · ${box.assignedOrderIds.size} шт", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                            Text(box.barcode)
                            Row { Button(onClick = { vm.selectBox(if (state.selectedBoxId == box.id) null else box.id) }) { Text(if (state.selectedBoxId == box.id) "Закрыть короб" else "Открыть") }
                                TextButton(onClick = { vm.printBoxes(encoder, listOf(box.id)) }, enabled = !state.busy) { Text("QR WB") } }
                            if (state.selectedBoxId == box.id) {
                                Text("Сканируйте товары или QR заказов")
                                for ((productId, orders) in workspace?.orders.orEmpty().groupBy { it.product.id }) {
                                    if (productId != null) TextButton(onClick = { editing = Triple(box, productId, orders.count { it.id in box.assignedOrderIds }) }) {
                                        Text("${orders.first().product.name}: ${orders.count { it.id in box.assignedOrderIds }} · изменить")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (state.pendingKiz != null && state.kizOrder?.needsConfirmation == true) AlertDialog(onDismissRequest = vm::cancelKiz, dismissButton = { TextButton(onClick = vm::cancelKiz, enabled = !state.busy) { Text("Отмена") } }, title = { Text("Подтвердите привязку ЧЗ") }, text = { Text("Код будет отправлен для заказа WB ${state.kizOrder?.wbOrderId}") }, confirmButton = { Button(onClick = vm::confirmKiz, enabled = !state.busy) { Text("Подтвердить") } })
    if (state.pickChoices.isNotEmpty()) AlertDialog(
        onDismissRequest = vm::cancelPickSource,
        title = { Text("Откуда подобрать товар") },
        text = {
            Column {
                Text(state.pickChoiceProduct.orEmpty())
                LazyColumn(Modifier.heightIn(max = 320.dp)) {
                    items(state.pickChoices) { choice ->
                        TextButton(onClick = { vm.choosePickSource(choice) }, modifier = Modifier.fillMaxWidth()) {
                            Text("${choice.label} · доступно ${choice.available}")
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = vm::cancelPickSource) { Text("Отмена") } },
    )
    printing?.let { ids -> PrintOptionsDialog({ printing = null }) { barcodes, codes, qr -> printing = null; vm.printOrders(encoder, ids, barcodes, codes, qr) } }
    editing?.let { target -> QuantityDialog(target.third, { editing = null }) { qty -> editing = null; vm.setBoxQuantity(target.first, target.second, qty) } }
}

@Composable private fun PrintOptionsDialog(onClose: () -> Unit, onPrint: (Int, Int, Boolean) -> Unit) {
    var barcodes by remember { mutableStateOf("1") }; var codes by remember { mutableStateOf("0") }; var qr by remember { mutableStateOf(true) }
    AlertDialog(onDismissRequest = onClose, title = { Text("Этикетки на каждый заказ") }, text = {
        Column { OutlinedTextField(barcodes, { barcodes = it.filter(Char::isDigit).take(3) }, label = { Text("Товарных ШК") }); OutlinedTextField(codes, { codes = it.filter(Char::isDigit).take(3) }, label = { Text("Копий ЧЗ") }); Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(qr, { qr = it }); Text("Включить QR заказа") } }
    }, confirmButton = { Button(onClick = { onPrint(barcodes.toIntOrNull() ?: 0, codes.toIntOrNull() ?: 0, qr) }, enabled = (barcodes.toIntOrNull() ?: 0) in 0..100 && (codes.toIntOrNull() ?: 0) in 0..100 && (qr || (barcodes.toIntOrNull() ?: 0) + (codes.toIntOrNull() ?: 0) > 0)) { Text("Выбрать принтер") } }, dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
}
@Composable private fun QuantityDialog(initial: Int, onClose: () -> Unit, onSave: (Int) -> Unit) {
    var value by remember { mutableStateOf(initial.toString()) }
    AlertDialog(onDismissRequest = onClose, title = { Text("Количество товара в коробе") }, text = { OutlinedTextField(value, { value = it.filter(Char::isDigit) }, label = { Text("Штук") }) }, confirmButton = { Button(onClick = { onSave(value.toIntOrNull() ?: 0) }, enabled = value.toIntOrNull() != null) { Text("Сохранить") } }, dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
}
