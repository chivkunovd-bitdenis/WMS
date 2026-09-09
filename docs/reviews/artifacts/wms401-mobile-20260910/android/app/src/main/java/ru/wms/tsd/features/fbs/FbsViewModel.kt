package ru.wms.tsd.features.fbs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.fbs.*
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.ui.patterns.ScanFlash

fun oldestMatchingOrder(orders: List<FbsOrder>, barcode: String): FbsOrder? = orders
    .filter { it.pick.status != "picked" && it.status !in setOf("cancelled", "done", "in_delivery") }
    .filter { barcode in listOfNotNull(it.product.barcode, it.product.sku, it.product.sellerArticle) }
    .minWithOrNull(compareBy<FbsOrder> { runCatching { OffsetDateTime.parse(it.createdAt).toInstant() }.getOrDefault(Instant.MAX) }.thenBy { it.wbOrderId })

/**
 * Первый экран показывает заказы в порядке старейших сначала (WMS-401): точка отсчёта —
 * createdAt в Instant. Если сервер вернул нечитаемую дату, такой заказ уходит в конец,
 * но его позиция не меняется относительно других нечитаемых дат (stable sort по wbOrderId).
 */
fun sortedOrders(orders: List<FbsOrder>): List<FbsOrder> = orders.sortedWith(
    compareBy<FbsOrder> { runCatching { OffsetDateTime.parse(it.createdAt).toInstant() }.getOrDefault(Instant.MAX) }.thenBy { it.wbOrderId }
)

fun isDeadlineNear(deadline: String, now: Instant = Instant.now()): Boolean =
    runCatching { OffsetDateTime.parse(deadline).toInstant().isBefore(now.plusSeconds(6 * 3600)) }.getOrDefault(false)

fun isKizScan(value: String): Boolean = value.startsWith("]d2", true) || value.startsWith("(01)") ||
    (value.startsWith("01") && value.length >= 20 && value.substring(2, 16).all(Char::isDigit) && value.substring(16, 18) == "21")

data class FbsPickChoice(val source: FbsScanResult, val label: String, val available: Int)

/** Same physical-source selection as web WMS-058; available is computed only by WMS. */
fun availablePickSources(locations: List<FbsPickOptionLocation>): List<FbsPickChoice> = locations.flatMap { location ->
    val sources = location.sources.ifEmpty { listOf(FbsPickOptionSource(location.available, "Россыпь")) }
    sources.filter { it.available >= 1 }.map { source ->
        val leaf = source.containerPath.lastOrNull()
        FbsPickChoice(
            FbsScanResult(if (leaf == null) "location" else "container", location.locationId, location.locationCode, leaf?.kind, leaf?.id, leaf?.code),
            "${location.locationCode} · ${source.label}", source.available,
        )
    }
}

data class FbsState(
    val busy: Boolean = false,
    val error: String? = null,
    val flash: ScanFlash = ScanFlash.None,
    val orders: List<FbsOrder> = emptyList(),
    val cursor: String? = null,
    val supplies: List<FbsSupplySummary> = emptyList(),
    val selected: Set<String> = emptySet(),
    val workspace: FbsWorkspace? = null,
    val source: FbsScanResult? = null,
    val pickChoices: List<FbsPickChoice> = emptyList(),
    val pickChoiceProduct: String? = null,
    val selectedBoxId: String? = null,
    val kizOrder: KizLookup? = null,
    val pendingKiz: String? = null,
    val kizResult: String? = null,
    val printDocument: String? = null,
    val deliveryConfirmationOpen: Boolean = false,
    val deliveryPreflight: FbsDeliveryPreflight? = null,
    val pendingDelivery: DeliverBody? = null,
)

class FbsViewModel(private val api: ApiProvider) : ViewModel() {
    private class PickSourceCancelled : Exception()
    private val mutable = MutableStateFlow(FbsState())
    val state: StateFlow<FbsState> = mutable
    private val scans = Channel<Triple<String, String, String>>(Channel.UNLIMITED)
    private var openedSupplyId: String? = null
    private var retryAction: (suspend () -> Unit)? = null
    private var pickChoiceReply: CompletableDeferred<FbsScanResult?>? = null
    init { viewModelScope.launch { for ((mode, text, supplyId) in scans) {
        val key = UUID.randomUUID().toString()
        state.first { !it.busy && it.error == null }
        if (supplyId != openedSupplyId || supplyId != state.value.workspace?.supply?.id) continue
        val action: suspend () -> Unit = when (mode) {
            "pick" -> pickAction(text, key)
            "pack" -> kizAction(text, key)
            else -> { { scanBox(text) } }
        }
        perform(action)
    } } }

    private suspend fun <T> required(block: suspend () -> Response<T>): T {
        val response = block()
        return if (response.isSuccessful) response.body() ?: error("Сервер вернул пустой ответ")
        else error(response.readableError())
    }
    private suspend fun perform(action: suspend () -> Unit) {
        mutable.value = state.value.copy(busy = true, error = null)
        try {
            action()
            retryAction = null
            mutable.value = state.value.copy(busy = false, flash = ScanFlash.Success(System.nanoTime()))
        } catch (_: PickSourceCancelled) {
            retryAction = null
            mutable.value = state.value.copy(busy = false, flash = ScanFlash.None)
        } catch (cancel: CancellationException) { throw cancel }
        catch (error: Exception) {
            retryAction = action
            val message = error.message ?: "Не удалось связаться с сервером. Повторите запрос."
            mutable.value = state.value.copy(busy = false, error = message, flash = ScanFlash.Error(message, System.nanoTime()))
        }
    }
    private fun launch(action: suspend () -> Unit) {
        if (state.value.busy) return
        mutable.value = state.value.copy(busy = true)
        viewModelScope.launch { perform(action) }
    }
    fun retry() { retryAction?.let(::launch) }
    fun dismissError() { retryAction = null; mutable.value = state.value.copy(error = null) }
    fun loadOrders(append: Boolean = false) = launch {
        val page = required { api.fbs().orders(group = null, cursor = if (append) state.value.cursor else null) }
        val supplies = required { api.fbs().worklist(statusGroup = "active") }
        mutable.value = state.value.copy(orders = ((if (append) state.value.orders else emptyList()) + page.items).distinctBy { it.id }, cursor = page.nextCursor, supplies = supplies.items)
    }
    fun toggle(order: FbsOrder) {
        if (order.status != "new" || order.supplyId != null) return
        mutable.value = state.value.copy(selected = state.value.selected.let { if (order.id in it) it - order.id else it + order.id })
    }
    fun create(name: String, delivery: String, onOpen: (String) -> Unit) {
        val ids = state.value.selected.toList(); if (ids.isEmpty() || name.isBlank()) return
        val body = SupplyCreateBody(name.trim(), ids, delivery, UUID.randomUUID().toString())
        launch { val workspace = required { api.fbs().createSupply(body) }; mutable.value = state.value.copy(selected = emptySet()); onOpen(workspace.supply.id) }
    }
    fun addTo(supplyId: String, onOpen: (String) -> Unit) {
        val body = SupplyOrdersBody(state.value.selected.toList(), UUID.randomUUID().toString())
        launch { val workspace = required { api.fbs().addOrders(supplyId, body) }; mutable.value = state.value.copy(selected = emptySet()); onOpen(workspace.supply.id) }
    }
    fun loadSupply(supplyId: String) {
        if (openedSupplyId != supplyId) {
            openedSupplyId = supplyId
            cancelPickSource()
            retryAction = null
            mutable.value = state.value.copy(workspace = null, source = null, selectedBoxId = null, kizOrder = null, pendingKiz = null, error = null, deliveryConfirmationOpen = false, deliveryPreflight = null, pendingDelivery = null)
        }
        viewModelScope.launch {
            state.first { !it.busy }
            if (openedSupplyId == supplyId) perform { refresh(supplyId) }
        }
    }
    private suspend fun refresh(supplyId: String) {
        val workspace = required { api.fbs().workspace(supplyId) }
        if (openedSupplyId == supplyId) {
            var pending = api.pendingFbsDelivery(supplyId)
            if (workspace.deliveryConfirmed() && pending != null) {
                api.saveFbsDelivery(supplyId, null)
                pending = null
            }
            mutable.value = state.value.copy(workspace = workspace, pendingDelivery = pending)
        }
    }
    private suspend fun prepareDelivery(supplyId: String) {
        if (openedSupplyId != supplyId) return
        mutable.value = state.value.copy(deliveryConfirmationOpen = true, deliveryPreflight = null)
        val preflight = required { api.fbs().deliveryPreflight(supplyId) }
        if (openedSupplyId == supplyId) mutable.value = state.value.copy(deliveryPreflight = preflight)
    }
    fun openDeliveryConfirmation() {
        val ws = state.value.workspace ?: return
        if (ws.deliveryConfirmed() || ws.supply.marketplace != "wb") return
        val pending = state.value.pendingDelivery
        if (pending != null) launch(deliveryAction(ws.supply.id, pending))
        else launch { prepareDelivery(ws.supply.id) }
    }
    fun cancelDelivery() {
        if (state.value.busy) return
        dismissError()
        mutable.value = state.value.copy(deliveryConfirmationOpen = false, deliveryPreflight = null)
    }
    fun confirmDelivery() {
        val current = state.value
        val ws = current.workspace ?: return
        if (current.busy || !current.deliveryConfirmationOpen || ws.deliveryConfirmed() || ws.supply.marketplace != "wb" || current.deliveryPreflight?.canDeliver == false) return
        val body = current.pendingDelivery ?: DeliverBody(UUID.randomUUID().toString(), current.deliveryPreflight?.version)
        mutable.value = current.copy(deliveryConfirmationOpen = false)
        launch(deliveryAction(ws.supply.id, body))
    }
    private fun deliveryAction(supplyId: String, body: DeliverBody): suspend () -> Unit {
        var needsConfirmation = false
        return action@{
            if (openedSupplyId != supplyId || state.value.workspace?.deliveryConfirmed() == true) return@action
            if (needsConfirmation) { prepareDelivery(supplyId); return@action }
            // Disk write must succeed BEFORE sending; a process restart reuses key AND version.
            api.saveFbsDelivery(supplyId, body)
            mutable.value = state.value.copy(pendingDelivery = body)
            val result = try {
                api.fbs().deliver(supplyId, body).deliveryBody()
            } catch (cancel: CancellationException) { throw cancel }
            catch (error: Exception) {
                if (error is FbsDeliveryError && !error.keepRequest) {
                    api.saveFbsDelivery(supplyId, null)
                    needsConfirmation = true
                    if (openedSupplyId == supplyId) mutable.value = state.value.copy(pendingDelivery = null, deliveryPreflight = null)
                }
                if (openedSupplyId != supplyId) return@action
                if (error is FbsDeliveryError) throw error
                throw FbsDeliveryError("Нет подтверждённого ответа сервера. Результат передачи неизвестен. Повторите проверку.", true)
            }
            if (openedSupplyId == supplyId) mutable.value = state.value.copy(workspace = result)
            if (!result.deliveryConfirmed()) {
                if (openedSupplyId != supplyId) return@action
                throw FbsDeliveryError("WB ещё не подтвердил передачу. Повторите проверку результата.", true)
            }
            api.saveFbsDelivery(supplyId, null)
            if (openedSupplyId == supplyId) mutable.value = state.value.copy(pendingDelivery = null, deliveryPreflight = null)
        }
    }
    fun syncDelivery() {
        val ws = state.value.workspace ?: return
        if (!ws.deliveryConfirmed()) return
        launch {
            val result = required { api.fbs().syncTracking(ws.supply.id) }
            if (openedSupplyId == ws.supply.id) mutable.value = state.value.copy(workspace = result)
        }
    }
    fun scan(mode: String, value: String) {
        val supplyId = state.value.workspace?.supply?.id ?: return
        if (value.isNotBlank() && supplyId == openedSupplyId) scans.trySend(Triple(mode, value.trimEnd('\r','\n'), supplyId))
    }
    fun clearSource() { mutable.value = state.value.copy(source = null) }
    fun choosePickSource(choice: FbsPickChoice) {
        if (choice in state.value.pickChoices) pickChoiceReply?.complete(choice.source)
    }
    fun cancelPickSource() { pickChoiceReply?.complete(null) }
    private suspend fun chooseSource(product: String, choices: List<FbsPickChoice>): FbsScanResult? {
        val reply = CompletableDeferred<FbsScanResult?>()
        pickChoiceReply = reply
        mutable.value = state.value.copy(pickChoices = choices, pickChoiceProduct = product)
        return try { reply.await() } finally {
            pickChoiceReply = null
            mutable.value = state.value.copy(pickChoices = emptyList(), pickChoiceProduct = null)
        }
    }
    private fun pickAction(value: String, key: String): suspend () -> Unit {
        val workspace = state.value.workspace ?: return { error("Откройте поставку перед сканированием") }
        val order = oldestMatchingOrder(workspace.orders, value)
        val source = state.value.source
        var body = FbsScanBody(value, order?.product?.id, source?.locationId, source?.containerKind, source?.containerId, order?.id)
        var sourceResolved = source != null || order?.product?.id == null
        // Retain this scan's identity if the response is lost; retry never manufactures another scan.
        val action: suspend () -> Unit = action@{
            if (!sourceResolved) {
                val options = required { api.fbs().pickOptions(workspace.supply.id) }
                if (openedSupplyId != workspace.supply.id) return@action
                val choices = availablePickSources(options.firstOrNull { it.productId == body.productId }?.locations.orEmpty())
                require(choices.isNotEmpty()) { "Для ${order?.product?.name} нет доступного места подбора" }
                // Waiting keeps this scan (oldest order + key) at the head of the queue.
                val chosen = choices.singleOrNull()?.source
                    ?: chooseSource(order?.product?.name.orEmpty(), choices) ?: throw PickSourceCancelled()
                body = body.copy(locationId = chosen.locationId, containerKind = chosen.containerKind, containerId = chosen.containerId)
                sourceResolved = true
                mutable.value = state.value.copy(source = chosen)
            }
            if (openedSupplyId != workspace.supply.id) return@action
            val result = required { api.fbs().scan(workspace.supply.id, body, key) }
            if (result.kind == "product") refresh(workspace.supply.id)
            else if (openedSupplyId == workspace.supply.id) mutable.value = state.value.copy(source = result)
        }
        return action
    }
    fun packOrder(order: FbsOrder) {
        val supply = state.value.workspace?.supply ?: return
        val key = UUID.randomUUID().toString()
        launch {
            val taskId = supply.packagingTaskId ?: required { api.fbs().startWork(supply.id) }.supply.packagingTaskId ?: error("Не удалось открыть упаковку поставки")
            val task = required { api.fbs().packagingTask(taskId) }
            val line = task.lines.firstOrNull { it.productId == order.product.id } ?: error("Для товара нет строки упаковки")
            required { api.fbs().pack(task.id, line.id, PackProgressBody(1, order.id, key)) }
            refresh(supply.id)
        }
    }
    private fun kizAction(value: String, key: String): suspend () -> Unit {
        val supplyId = state.value.workspace?.supply?.id ?: return { error("Откройте поставку") }
        if (!isKizScan(value)) return {
            val found = required { api.fbs().lookupKiz(supplyId, value) }
            require(found.canBind) { found.blockReason ?: "Для заказа нельзя записать этот код" }
            mutable.value = state.value.copy(kizOrder = found, pendingKiz = null, kizResult = null)
        }
        val order = state.value.kizOrder ?: return { error("Сначала отсканируйте QR заказа WB") }
        var validated = false
        val commit = commitAction(order, value, false, key, supplyId)
        return {
            if (!validated) {
                val result = required { api.fbs().validateKiz(KizValidateBody(order.orderId, value)) }
                require(result.ok) { result.hints.joinToString(". ").ifBlank { "Код не прошёл проверку" } }
                validated = true
            }
            mutable.value = state.value.copy(pendingKiz = value)
            if (!order.needsConfirmation) commit()
        }
    }
    fun cancelKiz() { mutable.value = state.value.copy(pendingKiz = null, kizOrder = null) }
    fun confirmKiz() {
        val current = state.value
        val order = current.kizOrder ?: return
        val value = current.pendingKiz ?: return
        val supplyId = current.workspace?.supply?.id ?: return
        launch(commitAction(order, value, true, UUID.randomUUID().toString(), supplyId))
    }
    private fun commitAction(order: KizLookup, value: String, confirmed: Boolean, key: String, supplyId: String): suspend () -> Unit {
        val body = KizCommitBody(listOf(KizPair(order.orderId, value, confirmed)), key)
        var answer: KizCommitResult? = null
        return {
            val result = answer ?: required { api.fbs().commitKiz(body) }.single().also { if (it.status == "ok") answer = it }
            require(result.status == "ok") { result.message ?: "WB не подтвердил запись кода" }
            refresh(supplyId)
            val notice = when (result.metaStatus) {
                "accepted" -> "КИЗ сохранён. WB принял код."
                "allowed_without_check" -> "КИЗ сохранён. WB разрешил код без проверки."
                "pending" -> "КИЗ сохранён. WB ещё проверяет код."
                "assigned", "sending" -> "КИЗ сохранён. Передача в WB ещё не подтверждена."
                "rejected" -> "КИЗ сохранён. WB отклонил код."
                "replacement_required" -> "КИЗ сохранён. WB требует заменить код."
                else -> "КИЗ сохранён. Результат проверки WB неизвестен."
            }
            mutable.value = state.value.copy(kizOrder = null, pendingKiz = null, kizResult = notice)
        }
    }
    fun selectBox(boxId: String?) { mutable.value = state.value.copy(selectedBoxId = boxId) }
    fun createBox() {
        val supplyId = state.value.workspace?.supply?.id ?: return
        val body = CreateBoxesBody(idempotencyKey = UUID.randomUUID().toString())
        launch {
            val oldIds = state.value.workspace?.boxes.orEmpty().map { it.id }.toSet()
            val workspace = required { api.fbs().createBoxes(supplyId, body) }
            mutable.value = state.value.copy(workspace = workspace, selectedBoxId = workspace.boxes.firstOrNull { it.id !in oldIds }?.id)
        }
    }
    private suspend fun scanBox(value: String) {
        val workspace = state.value.workspace ?: return
        workspace.boxes.firstOrNull { value == it.barcode || value == it.wbTrbxId }?.let { selectBox(it.id); return }
        val boxId = state.value.selectedBoxId ?: error("Откройте или отсканируйте короб")
        val assigned = workspace.boxes.flatMap { it.assignedOrderIds }.toSet()
        val unassigned = workspace.orders.filter { it.id !in assigned }
        val order = unassigned.sortedBy { it.createdAt }.firstOrNull {
            value in listOfNotNull(it.sticker.code, it.wbOrderId.toString(), it.product.barcode, it.product.sku, it.product.sellerArticle)
        } ?: run {
            val found = required { api.fbs().lookupKiz(workspace.supply.id, value) }
            unassigned.firstOrNull { it.id == found.orderId }
                ?: error("Нет нераспределённого заказа с таким кодом")
        }
        val updated = required { api.fbs().assignOrders(workspace.supply.id, boxId, AssignOrdersBody(listOf(order.id))) }
        mutable.value = state.value.copy(workspace = updated)
    }
    fun setBoxQuantity(box: FbsBox, productId: String, quantity: Int) = launch {
        val supplyId = state.value.workspace?.supply?.id ?: return@launch
        // A prior removal may have reached the server before its response was lost.
        refresh(supplyId)
        val workspace = state.value.workspace ?: return@launch
        val currentBox = workspace.boxes.firstOrNull { it.id == box.id } ?: error("Короб не найден")
        val inBox = workspace.orders.filter { it.id in currentBox.assignedOrderIds && it.product.id == productId }
        if (quantity < inBox.size) {
            for (order in inBox.drop(quantity.coerceAtLeast(0))) {
                mutable.value = state.value.copy(workspace = required { api.fbs().removeBoxOrder(workspace.supply.id, box.id, order.id) })
            }
        } else {
            val assigned = workspace.boxes.flatMap { it.assignedOrderIds }.toSet()
            val add = workspace.orders.filter { it.id !in assigned && it.product.id == productId }.sortedBy { it.createdAt }.take(quantity - inBox.size)
            require(add.size == quantity - inBox.size) { "Не хватает свободных заказов этого товара" }
            if (add.isNotEmpty()) mutable.value = state.value.copy(workspace = required { api.fbs().assignOrders(workspace.supply.id, box.id, AssignOrdersBody(add.map { it.id })) })
        }
    }
    private suspend fun assetImage(asset: FbsPrintAsset): String {
        require(asset.status == "ready") { "Этикетка WB ещё не готова" }
        val path = asset.previewUrl?.removePrefix("/api/")?.removePrefix("/") ?: error("WB не вернул файл этикетки")
        require(Regex("operations/fbs-print-assets/[a-fA-F0-9-]+/content").matches(path)) { "Неизвестный адрес файла этикетки" }
        val body = required { api.fbs().asset(path) }
        return body.use { inlineImage(it.bytes(), it.contentType()?.toString() ?: "") }
    }
    fun printOrders(encoder: String, ids: List<String>, barcodeCopies: Int, kizCopies: Int, includeQr: Boolean) {
        val workspace = state.value.workspace ?: return
        require(barcodeCopies in 0..100 && kizCopies in 0..100)
        var tape: FbsPrintTape? = null
        val qrAssets = mutableMapOf<String, FbsPrintAsset>()
        launch {
            val pages = mutableListOf<String>()
            if (kizCopies > 0 && tape == null) tape = required { api.fbs().printTape(workspace.supply.id, PrintTapeBody(ids, includeQr)) }
            if (kizCopies > 0) {
                val currentTape = tape ?: error("Не получены данные для печати ЧЗ")
                if (currentTape.orderErrors.isNotEmpty()) {
                    tape = null
                    error(currentTape.orderErrors.joinToString("\n") { failure ->
                        val reason = when (failure.code) {
                            "operator_kiz_print_forbidden" -> "Печать введённого оператором кода ЧЗ запрещена."
                            else -> failure.message.takeIf { it.isNotBlank() && it != failure.code }
                                ?: "Не удалось подготовить этикетки. Обновите поставку и повторите печать."
                        }
                        "WB ${failure.wbOrderId}: $reason"
                    })
                }
                val absent = ids.filter { id -> currentTape.orders.none { it.orderId == id } || workspace.orders.none { it.id == id } }
                if (absent.isNotEmpty()) {
                    tape = null
                    error("Не получены данные для печати ЧЗ: " + absent.joinToString { id ->
                        workspace.orders.firstOrNull { it.id == id }?.let { "WB ${it.wbOrderId}" } ?: "заказ $id"
                    })
                }
            }
            if ((tape?.missing ?: 0) != 0 || (tape?.failed ?: 0) != 0) {
                tape = null
                error("WB не вернул все этикетки. Повторите печать после обновления поставки.")
            }
            if ((tape?.shortage ?: 0) != 0) {
                tape = null
                error("Недостаточно кодов ЧЗ для печати; проверьте пул в WMS")
            }
            for (id in ids) {
                val order = workspace.orders.firstOrNull { it.id == id } ?: continue
                val entry = tape?.orders?.firstOrNull { it.orderId == id }
                if (includeQr) {
                    val asset = if (entry != null) entry.qrAsset ?: error("Не получен QR заказа WB ${order.wbOrderId}")
                    else qrAssets[id] ?: required { api.fbs().printAssets(workspace.supply.id, PrintBatchBody("order_sticker", listOf(id))) }.let { batch ->
                        require(batch.missing == 0 && batch.failed == 0 && batch.assets.size == 1) { "WB не вернул QR заказа ${order.wbOrderId}" }
                        batch.assets.single().also { qrAssets[id] = it }
                    }
                    pages += labelPage("WB ${order.wbOrderId}", image = assetImage(asset))
                }
                if (barcodeCopies > 0) {
                    val barcode = order.product.barcode ?: error("У ${order.product.name} не указан товарный штрихкод")
                    repeat(barcodeCopies) { pages += labelPage(order.product.name + " · " + (order.product.sellerArticle ?: order.product.sku.orEmpty()), barcode) }
                }
                for (code in entry?.codes.orEmpty()) repeat(kizCopies) { pages += labelPage(order.product.name, code, dataMatrix = true) }
            }
            require(pages.isNotEmpty()) { "Выберите хотя бы один вид этикетки" }
            mutable.value = state.value.copy(printDocument = labelsDocument(encoder, pages))
        }
    }
    fun printBoxes(encoder: String, boxIds: List<String>) = launch {
        val workspace = state.value.workspace ?: return@launch
        val pages = workspace.boxes.filter { it.id in boxIds }.map { box ->
            val asset = box.qrAsset ?: error("WB ещё не вернул QR для короба №${box.boxNumber}")
            labelPage("Короб №${box.boxNumber}", image = assetImage(asset))
        }
        require(pages.isNotEmpty()) { "Нет коробов для печати" }
        mutable.value = state.value.copy(printDocument = labelsDocument(encoder, pages))
    }
    fun clearPrint() { mutable.value = state.value.copy(printDocument = null) }

    class Factory(private val api: ApiProvider) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T = FbsViewModel(api) as T
    }
}
