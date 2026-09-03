package ru.wms.tsd.features.fbs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.util.UUID
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.fbs.AssignOrdersBody
import ru.wms.tsd.core.api.fbs.CreateBoxesBody
import ru.wms.tsd.core.api.fbs.DeliverBody
import ru.wms.tsd.core.api.fbs.FbsBox
import ru.wms.tsd.core.api.fbs.FbsDeliveryPreflight
import ru.wms.tsd.core.api.fbs.FbsPickLocation
import ru.wms.tsd.core.api.fbs.FbsSupplySummary
import ru.wms.tsd.core.api.fbs.FbsWorkspace
import ru.wms.tsd.core.api.fbs.PackProgressBody
import ru.wms.tsd.core.api.fbs.PackagingTask
import ru.wms.tsd.core.api.fbs.ScanLocationBody
import ru.wms.tsd.core.api.fbs.ScanProductBody
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.ui.patterns.ScanFlash

private sealed interface FbsResult<out T> {
    data class Ok<T>(val value: T) : FbsResult<T>
    data class Error(val message: String) : FbsResult<Nothing>
}

private suspend fun <T> fbsCall(block: suspend () -> Response<T>): FbsResult<T> = try {
    val response = block()
    val body = response.body()
    if (response.isSuccessful && body != null) FbsResult.Ok(body)
    else FbsResult.Error(response.readableError())
} catch (_: Exception) {
    FbsResult.Error(networkErrorText())
}

private fun successFlash() = ScanFlash.Success(System.nanoTime())
private fun errorFlash(message: String) = ScanFlash.Error(message, System.nanoTime())

class ApiFactory<T : ViewModel>(
    private val creator: (ApiProvider) -> T,
    private val api: ApiProvider,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <R : ViewModel> create(modelClass: Class<R>): R = creator(api) as R
}

data class FbsListState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val active: List<FbsSupplySummary> = emptyList(),
    val delivery: List<FbsSupplySummary> = emptyList(),
)

class FbsSupplyListViewModel(private val api: ApiProvider) : ViewModel() {
    private val _state = MutableStateFlow(FbsListState())
    val state: StateFlow<FbsListState> = _state

    init { load(initial = true) }

    fun load(initial: Boolean = false) {
        _state.value = _state.value.copy(loading = initial, refreshing = !initial, error = null)
        viewModelScope.launch {
            val active = fbsCall { api.fbs().worklist(statusGroup = "active") }
            val delivery = fbsCall { api.fbs().worklist(statusGroup = "delivery") }
            when {
                active is FbsResult.Error -> _state.value = FbsListState(loading = false, error = active.message)
                delivery is FbsResult.Error -> _state.value = FbsListState(loading = false, error = delivery.message)
                else -> _state.value = FbsListState(
                    loading = false,
                    active = (active as FbsResult.Ok).value.items,
                    delivery = (delivery as FbsResult.Ok).value.items,
                )
            }
        }
    }
}

data class FbsWorkspaceState(
    val loading: Boolean = true,
    val busy: Boolean = false,
    val error: String? = null,
    val workspace: FbsWorkspace? = null,
    val initialTotal: Int? = null,
    val flash: ScanFlash = ScanFlash.None,
)

class FbsWorkspaceViewModel(
    private val supplyId: String,
    private val api: ApiProvider,
) : ViewModel() {
    private val _state = MutableStateFlow(FbsWorkspaceState())
    val state: StateFlow<FbsWorkspaceState> = _state

    init { load() }

    fun load() {
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            when (val result = fbsCall { api.fbs().workspace(supplyId) }) {
                is FbsResult.Ok -> setWorkspace(result.value)
                is FbsResult.Error -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }

    fun startWork() {
        if (_state.value.busy) return
        _state.value = _state.value.copy(busy = true)
        viewModelScope.launch {
            when (val result = fbsCall { api.fbs().startWork(supplyId) }) {
                is FbsResult.Ok -> setWorkspace(result.value, successFlash())
                is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            }
        }
    }

    private fun setWorkspace(workspace: FbsWorkspace, flash: ScanFlash = _state.value.flash) {
        _state.value = _state.value.copy(
            loading = false,
            busy = false,
            error = null,
            workspace = workspace,
            initialTotal = _state.value.initialTotal ?: workspace.progress.total,
            flash = flash,
        )
    }
}

data class FbsPickingState(
    val loading: Boolean = true,
    val error: String? = null,
    val workspace: FbsWorkspace? = null,
    val location: FbsPickLocation? = null,
    val locationBarcode: String? = null,
    val busy: Boolean = false,
    val flash: ScanFlash = ScanFlash.None,
)

class FbsPickingViewModel(
    private val supplyId: String,
    private val api: ApiProvider,
) : ViewModel() {
    private val _state = MutableStateFlow(FbsPickingState())
    val state: StateFlow<FbsPickingState> = _state
    private val scans = Channel<String>(Channel.UNLIMITED)

    init {
        load()
        viewModelScope.launch { for (barcode in scans) processScan(barcode) }
    }

    fun load() {
        viewModelScope.launch {
            when (val result = fbsCall { api.fbs().workspace(supplyId) }) {
                is FbsResult.Ok -> _state.value = _state.value.copy(loading = false, error = null, workspace = result.value)
                is FbsResult.Error -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }

    fun onScan(barcode: String) { scans.trySend(barcode) }

    fun clearLocation() {
        _state.value = _state.value.copy(location = null, locationBarcode = null)
    }

    private suspend fun processScan(barcode: String) {
        if (_state.value.busy) return
        _state.value = _state.value.copy(busy = true)
        val location = _state.value.location
        if (location == null) {
            when (val result = fbsCall { api.fbs().scanLocation(supplyId, ScanLocationBody(barcode)) }) {
                is FbsResult.Ok -> _state.value = _state.value.copy(
                    busy = false,
                    location = result.value,
                    locationBarcode = barcode,
                    flash = successFlash(),
                )
                is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            }
            return
        }

        val result = fbsCall {
            api.fbs().scanProduct(
                supplyId,
                ScanProductBody(location.id, barcode, idempotencyKey = UUID.randomUUID().toString()),
            )
        }
        when (result) {
            is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            is FbsResult.Ok -> {
                val refreshedLocation = _state.value.locationBarcode?.let {
                    fbsCall { api.fbs().scanLocation(supplyId, ScanLocationBody(it)) }
                }
                _state.value = _state.value.copy(
                    busy = false,
                    workspace = result.value,
                    location = (refreshedLocation as? FbsResult.Ok)?.value ?: location,
                    flash = successFlash(),
                )
            }
        }
    }
}

data class FbsPackingState(
    val loading: Boolean = true,
    val error: String? = null,
    val workspace: FbsWorkspace? = null,
    val task: PackagingTask? = null,
    val busy: Boolean = false,
    val flash: ScanFlash = ScanFlash.None,
)

class FbsPackingViewModel(
    private val supplyId: String,
    private val api: ApiProvider,
) : ViewModel() {
    private val _state = MutableStateFlow(FbsPackingState())
    val state: StateFlow<FbsPackingState> = _state
    private val scans = Channel<String>(Channel.UNLIMITED)

    init {
        load()
        viewModelScope.launch { for (barcode in scans) packBarcode(barcode) }
    }

    fun load() {
        viewModelScope.launch {
            when (val workspaceResult = fbsCall { api.fbs().workspace(supplyId) }) {
                is FbsResult.Error -> _state.value = _state.value.copy(loading = false, error = workspaceResult.message)
                is FbsResult.Ok -> {
                    val workspace = workspaceResult.value
                    val taskId = workspace.supply.packagingTaskId
                    if (taskId == null) {
                        _state.value = _state.value.copy(loading = false, workspace = workspace, task = null)
                    } else when (val taskResult = fbsCall { api.fbs().packagingTask(taskId) }) {
                        is FbsResult.Ok -> _state.value = _state.value.copy(
                            loading = false, error = null, workspace = workspace, task = taskResult.value,
                        )
                        is FbsResult.Error -> _state.value = _state.value.copy(loading = false, error = taskResult.message)
                    }
                }
            }
        }
    }

    fun onScan(barcode: String) { scans.trySend(barcode) }

    fun packOne(lineId: String, orderId: String? = null) {
        if (_state.value.busy) return
        viewModelScope.launch { submitPack(lineId, orderId) }
    }

    private suspend fun packBarcode(barcode: String) {
        val state = _state.value
        if (state.busy) return
        val order = state.workspace?.orders?.firstOrNull { order ->
            order.pack.status != "packed" && listOfNotNull(
                order.sticker.code,
                order.externalOrderId,
                order.wbOrderId.toString(),
                order.product.barcode,
                order.product.sku,
                order.product.sellerArticle,
            ).any { it.equals(barcode, ignoreCase = true) }
        }
        if (order == null) {
            _state.value = state.copy(flash = errorFlash("Заказ или товар не найден среди неупакованных"))
            return
        }
        val productIds = buildSet {
            order.product.id?.let(::add)
            order.positions.mapNotNullTo(this) { it.productId }
        }
        val line = state.task?.lines?.firstOrNull { it.productId in productIds && !it.isComplete }
        if (line == null) {
            _state.value = state.copy(flash = errorFlash("Для заказа нет строки упаковки"))
            return
        }
        submitPack(line.id, order.id)
    }

    private suspend fun submitPack(lineId: String, orderId: String?) {
        val task = _state.value.task ?: return
        _state.value = _state.value.copy(busy = true)
        when (val result = fbsCall {
            api.fbs().pack(
                task.id,
                lineId,
                PackProgressBody(1, orderId, UUID.randomUUID().toString()),
            )
        }) {
            is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            is FbsResult.Ok -> {
                val workspace = (fbsCall { api.fbs().workspace(supplyId) } as? FbsResult.Ok)?.value
                _state.value = _state.value.copy(
                    busy = false,
                    task = result.value.packagingTask,
                    workspace = workspace ?: _state.value.workspace,
                    flash = successFlash(),
                )
            }
        }
    }
}

data class FbsHandoffState(
    val loading: Boolean = true,
    val error: String? = null,
    val workspace: FbsWorkspace? = null,
    val selectedBox: FbsBox? = null,
    val preflight: FbsDeliveryPreflight? = null,
    val confirmDeliver: Boolean = false,
    val busy: Boolean = false,
    val flash: ScanFlash = ScanFlash.None,
)

class FbsHandoffViewModel(
    private val supplyId: String,
    private val api: ApiProvider,
) : ViewModel() {
    private val _state = MutableStateFlow(FbsHandoffState())
    val state: StateFlow<FbsHandoffState> = _state
    private val scans = Channel<String>(Channel.UNLIMITED)

    init {
        load()
        viewModelScope.launch { for (barcode in scans) processScan(barcode) }
    }

    fun load() {
        viewModelScope.launch {
            when (val result = fbsCall { api.fbs().workspace(supplyId) }) {
                is FbsResult.Ok -> setWorkspace(result.value)
                is FbsResult.Error -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }

    fun onScan(barcode: String) { scans.trySend(barcode) }
    fun selectBox(box: FbsBox) { _state.value = _state.value.copy(selectedBox = box) }

    fun createBox() {
        mutate(invalidatePreflight = true) {
            api.fbs().createBoxes(supplyId, CreateBoxesBody(idempotencyKey = UUID.randomUUID().toString()))
        }
    }

    fun checkDelivery() {
        if (_state.value.busy) return
        _state.value = _state.value.copy(busy = true)
        viewModelScope.launch {
            when (val result = fbsCall { api.fbs().deliveryPreflight(supplyId) }) {
                is FbsResult.Ok -> _state.value = _state.value.copy(busy = false, preflight = result.value)
                is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            }
        }
    }

    fun requestDeliver() { _state.value = _state.value.copy(confirmDeliver = true) }
    fun dismissDeliver() { _state.value = _state.value.copy(confirmDeliver = false) }

    fun deliver() {
        val preflight = _state.value.preflight ?: return
        if (_state.value.busy) return
        _state.value = _state.value.copy(busy = true, confirmDeliver = false)
        viewModelScope.launch {
            when (val result = fbsCall {
                api.fbs().deliver(supplyId, DeliverBody(UUID.randomUUID().toString(), preflight.version))
            }) {
                is FbsResult.Ok -> setWorkspace(result.value, successFlash())
                is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            }
        }
    }

    fun syncTracking() {
        mutate { api.fbs().syncTracking(supplyId) }
    }

    private suspend fun processScan(barcode: String) {
        if (_state.value.busy) return
        if (_state.value.workspace?.supply?.status == "in_delivery") {
            _state.value = _state.value.copy(flash = errorFlash("Поставка уже передана в WB"))
            return
        }
        val ownBox = _state.value.workspace?.boxes?.firstOrNull { it.barcode == barcode }
        if (ownBox != null) {
            _state.value = _state.value.copy(selectedBox = ownBox, flash = successFlash())
            return
        }
        val box = _state.value.selectedBox
        if (box == null) {
            _state.value = _state.value.copy(flash = errorFlash("Сначала отсканируйте или выберите короб"))
            return
        }
        val order = _state.value.workspace?.orders?.firstOrNull { order ->
            listOfNotNull(order.sticker.code, order.externalOrderId, order.wbOrderId.toString())
                .any { it.equals(barcode, ignoreCase = true) }
        }
        if (order == null) {
            _state.value = _state.value.copy(flash = errorFlash("Заказ не найден в этой поставке"))
            return
        }
        mutate(invalidatePreflight = true) {
            api.fbs().assignOrders(supplyId, box.id, AssignOrdersBody(listOf(order.id)))
        }
    }

    private fun mutate(
        invalidatePreflight: Boolean = false,
        block: suspend () -> Response<FbsWorkspace>,
    ) {
        if (_state.value.busy) return
        _state.value = _state.value.copy(busy = true)
        viewModelScope.launch {
            when (val result = fbsCall(block)) {
                is FbsResult.Ok -> setWorkspace(result.value, successFlash(), invalidatePreflight)
                is FbsResult.Error -> _state.value = _state.value.copy(busy = false, flash = errorFlash(result.message))
            }
        }
    }

    private fun setWorkspace(
        workspace: FbsWorkspace,
        flash: ScanFlash = _state.value.flash,
        clearPreflight: Boolean = false,
    ) {
        val selected = _state.value.selectedBox?.id?.let { id -> workspace.boxes.firstOrNull { it.id == id } }
        _state.value = _state.value.copy(
            loading = false,
            busy = false,
            error = null,
            workspace = workspace,
            selectedBox = selected,
            preflight = if (clearPreflight) null else workspace.deliveryPreflight ?: _state.value.preflight,
            flash = flash,
        )
    }
}

class SupplyApiFactory<T : ViewModel>(
    private val supplyId: String,
    private val api: ApiProvider,
    private val creator: (String, ApiProvider) -> T,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <R : ViewModel> create(modelClass: Class<R>): R = creator(supplyId, api) as R
}
