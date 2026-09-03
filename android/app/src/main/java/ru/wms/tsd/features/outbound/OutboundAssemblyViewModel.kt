package ru.wms.tsd.features.outbound

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
import ru.wms.tsd.core.api.ERROR_DISTRIBUTION_INCOMPLETE_RU
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.core.api.generated.models.CompletePackagingIn
import ru.wms.tsd.core.api.generated.models.ConfirmPackedIn
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadBoxCreate
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadRequestDetailOut
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadScanBody
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadShipBody
import ru.wms.tsd.core.api.generated.models.PackProgressIn
import ru.wms.tsd.core.api.generated.models.PackagingTaskLineOut
import ru.wms.tsd.core.api.generated.models.PackagingTaskOut
import ru.wms.tsd.ui.patterns.ScanFlash

data class AssemblyUiState(
    val loading: Boolean = true,
    val loadError: String? = null,
    val request: MarketplaceUnloadRequestDetailOut? = null,
    /** Текущий короб, в который идёт сборка. */
    val currentBoxId: String? = null,
    /** Контекст ячейки после её скана (сервер вернул kind=location). */
    val locationId: String? = null,
    val locationCode: String? = null,
    val flash: ScanFlash = ScanFlash.None,
    val activeProductId: String? = null,
    /** "close_box" | "ship" | "ship_discrepancy" | "complete_packaging" | null */
    val confirm: String? = null,
    val shipping: Boolean = false,
    /** Задача упаковки (гейт перед ship). null = ещё не создана сервером. */
    val packaging: PackagingTaskOut? = null,
    /** Строка упаковки, для которой открыт ввод количества. */
    val packLineId: String? = null,
    val packBusy: Boolean = false,
) {
    val packLine: PackagingTaskLineOut?
        get() = packaging?.lines?.firstOrNull { it.id == packLineId }
}

/** Зеркало серверного assert_packaging_line_marking_done: чем блокируется complete. */
fun markingIncomplete(line: PackagingTaskLineOut): Boolean =
    line.requiresHonestSign && line.qtyDone > 0 && line.qtyMarkingPrinted < line.qtyDone

/**
 * T-14. Сборка отгрузки (объединённые D2+D3 из UX-спеки — так устроено серверное
 * API: pick/scan deprecated, актуальный флоу — скан сразу в короб).
 *
 * Сканы шлются в POST .../boxes/{box}/scan как есть — сервер сам различает:
 * kind=location (запоминаем контекст ячейки), kind=product (+quantity в короб),
 * kind=ready_box (собран готовый короб целиком). Построен по образцу золотого
 * экрана: Channel для последовательности, refresh после каждой мутации.
 */
class OutboundAssemblyViewModel(
    private val requestId: UUID,
    private val api: ApiProvider,
) : ViewModel() {

    private val _state = MutableStateFlow(AssemblyUiState())
    val state: StateFlow<AssemblyUiState> = _state

    private val scanQueue = Channel<String>(capacity = 16)
    private var flashStamp = 0L

    init {
        load()
        viewModelScope.launch {
            for (barcode in scanQueue) processScan(barcode)
        }
    }

    fun load() {
        _state.value = _state.value.copy(loading = true, loadError = null)
        viewModelScope.launch {
            when (val r = apiCall { api.operations().getMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdGet(requestId) }) {
                is ApiResult.Ok -> {
                    val openBox = r.value.boxes.orEmpty().lastOrNull { it.closedAt == null }?.id
                    _state.value = _state.value.copy(
                        loading = false,
                        request = r.value,
                        currentBoxId = _state.value.currentBoxId ?: openBox,
                    )
                    refreshPackaging()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(loading = false, loadError = r.message)
            }
        }
    }

    /**
     * 404 = сервер ещё не создал задачу упаковки (создаётся при confirm отгрузки) — не ошибка.
     * Двухшаговый GET обязателен: by-unload только читает, а GET по id ещё и синкает
     * строки задачи с фактическим отбором (sync_lines_from_pick_allocations) —
     * без него у задачи, созданной после начала сборки, будет 0 строк.
     */
    private suspend fun refreshPackaging() {
        val byUnload = runCatching {
            api.operations().getPackagingTaskForUnloadOperationsPackagingTasksByUnloadUnloadIdGet(requestId)
        }.getOrNull() ?: return // сеть: оставляем прошлое состояние, сборку не блокируем
        if (byUnload.code() == 404) {
            _state.value = _state.value.copy(packaging = null)
            return
        }
        val taskId = byUnload.body()?.id ?: return
        runCatching {
            api.operations().getPackagingTaskOperationsPackagingTasksTaskIdGet(UUID.fromString(taskId))
        }.onSuccess { resp ->
            if (resp.isSuccessful) _state.value = _state.value.copy(packaging = resp.body())
        }
    }

    fun onScan(barcode: String) {
        scanQueue.trySend(barcode)
    }

    fun selectBox(boxId: String) {
        _state.value = _state.value.copy(currentBoxId = boxId, locationId = null, locationCode = null)
    }

    fun createBox() {
        viewModelScope.launch {
            val result = apiCall {
                api.operations().createMarketplaceUnloadBoxOperationsMarketplaceUnloadRequestsRequestIdBoxesPost(
                    requestId, MarketplaceUnloadBoxCreate(boxPreset = "60_40_40"),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(currentBoxId = result.value.id, flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    fun requestCloseBox() {
        if (_state.value.currentBoxId != null) _state.value = _state.value.copy(confirm = "close_box")
    }

    fun requestShip() {
        _state.value = _state.value.copy(confirm = "ship")
    }

    fun dismissConfirm() {
        _state.value = _state.value.copy(confirm = null)
    }

    fun confirmCloseBox() {
        val boxId = _state.value.currentBoxId ?: return
        _state.value = _state.value.copy(confirm = null)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().closeMarketplaceUnloadBoxOperationsMarketplaceUnloadRequestsRequestIdBoxesBoxIdClosePost(
                    requestId, UUID.fromString(boxId),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(
                        currentBoxId = null, locationId = null, locationCode = null, flash = successFlash(),
                    )
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    // ---- Упаковка (T-15b): ship невозможен, пока packaging task не done ----

    fun openPackLine(lineId: String) {
        _state.value = _state.value.copy(packLineId = lineId)
    }

    fun dismissPackLine() {
        _state.value = _state.value.copy(packLineId = null)
    }

    /** Подтвердить «уже упаковано на полке» (серверный suggested). */
    fun confirmPackedFromShelf() {
        val task = _state.value.packaging ?: return
        val line = _state.value.packLine ?: return
        packagingMutation {
            api.operations().confirmPackedFromShelfOperationsPackagingTasksTaskIdLinesLineIdConfirmPackedPost(
                UUID.fromString(task.id), UUID.fromString(line.id), ConfirmPackedIn(),
            )
        }
    }

    /** Записать упакованное сейчас количество по строке. */
    fun submitPack(qty: Int) {
        val task = _state.value.packaging ?: return
        val line = _state.value.packLine ?: return
        if (qty < 1) return
        packagingMutation {
            api.operations().recordPackProgressOperationsPackagingTasksTaskIdLinesLineIdPackPost(
                UUID.fromString(task.id), UUID.fromString(line.id), PackProgressIn(quantity = qty),
            )
        }
    }

    fun requestCompletePackaging() {
        _state.value = _state.value.copy(confirm = "complete_packaging")
    }

    fun confirmCompletePackaging() {
        val task = _state.value.packaging ?: return
        _state.value = _state.value.copy(confirm = null)
        packagingMutation {
            api.operations().completePackagingTaskOperationsPackagingTasksTaskIdCompletePost(
                UUID.fromString(task.id), CompletePackagingIn(acknowledgeAllPacked = false),
            )
        }
    }

    private fun packagingMutation(block: suspend () -> Response<PackagingTaskOut>) {
        if (_state.value.packBusy) return
        _state.value = _state.value.copy(packBusy = true)
        viewModelScope.launch {
            when (val result = apiCall(block)) {
                is ApiResult.Ok -> {
                    val line = result.value.lines.firstOrNull { it.id == _state.value.packLineId }
                    _state.value = _state.value.copy(
                        packaging = result.value,
                        packBusy = false,
                        flash = successFlash(),
                        // строка допакована — закрываем её шторку
                        packLineId = if (line != null && !line.isComplete) line.id else null,
                    )
                }
                is ApiResult.Err -> _state.value = _state.value.copy(packBusy = false, flash = errorFlash(result.message))
            }
        }
    }

    /**
     * Отгрузить (списание остатков). onDone — навигация назад.
     * acknowledgeDiscrepancy — повтор после подтверждения расхождения план/факт.
     */
    fun confirmShip(onDone: () -> Unit, acknowledgeDiscrepancy: Boolean = false) {
        _state.value = _state.value.copy(confirm = null, shipping = true)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().shipMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdShipPost(
                    requestId, MarketplaceUnloadShipBody(acknowledgeDiscrepancy = acknowledgeDiscrepancy),
                )
            }
            when (result) {
                is ApiResult.Ok -> onDone()
                is ApiResult.Err -> {
                    // Расхождение план/факт: сервер требует явного подтверждения — спрашиваем
                    val discrepancy = !acknowledgeDiscrepancy && result.message == ERROR_DISTRIBUTION_INCOMPLETE_RU &&
                        hasPlanFactMismatch()
                    _state.value = _state.value.copy(
                        shipping = false,
                        confirm = if (discrepancy) "ship_discrepancy" else _state.value.confirm,
                        flash = if (discrepancy) ScanFlash.None else errorFlash(result.message),
                    )
                }
            }
        }
    }

    private fun hasPlanFactMismatch(): Boolean {
        val lines = _state.value.request?.lines.orEmpty()
        return lines.any { (it.pickedQty ?: 0) != it.quantity }
    }

    private suspend fun processScan(barcode: String) {
        val st = _state.value
        val request = st.request ?: return

        // Скан ШК существующего открытого короба — переключение на него (клиентская логика)
        val ownBox = request.boxes.orEmpty().firstOrNull { it.internalBarcode == barcode }
        if (ownBox != null) {
            if (ownBox.closedAt != null) {
                _state.value = st.copy(flash = errorFlash("Этот короб уже закрыт"))
            } else {
                _state.value = st.copy(
                    currentBoxId = ownBox.id, locationId = null, locationCode = null, flash = successFlash(),
                )
            }
            return
        }

        val boxId = st.currentBoxId
        if (boxId == null) {
            _state.value = st.copy(flash = errorFlash("Сначала создайте или выберите короб"))
            return
        }

        val result = apiCall {
            api.operations().scanMarketplaceUnloadBoxOperationsMarketplaceUnloadRequestsRequestIdBoxesBoxIdScanPost(
                requestId, UUID.fromString(boxId),
                MarketplaceUnloadScanBody(
                    barcode = barcode,
                    storageLocationId = st.locationId?.let(UUID::fromString),
                ),
            )
        }
        when (result) {
            is ApiResult.Ok -> when (result.value.kind) {
                "location" -> _state.value = _state.value.copy(
                    locationId = result.value.storageLocationId,
                    locationCode = result.value.locationCode,
                    flash = successFlash(),
                )
                "product" -> {
                    _state.value = _state.value.copy(flash = successFlash(), activeProductId = result.value.productId)
                    refresh()
                }
                else -> { // ready_box
                    _state.value = _state.value.copy(flash = successFlash())
                    refresh()
                }
            }
            is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
        }
    }

    private suspend fun refresh() {
        runCatching { api.operations().getMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdGet(requestId) }
            .onSuccess { resp ->
                if (resp.isSuccessful) _state.value = _state.value.copy(request = resp.body())
            }
        refreshPackaging()
    }

    private fun successFlash() = ScanFlash.Success(++flashStamp)
    private fun errorFlash(message: String) = ScanFlash.Error(message, ++flashStamp)

    private sealed interface ApiResult<out T> {
        data class Ok<T>(val value: T) : ApiResult<T>
        data class Err(val message: String) : ApiResult<Nothing>
    }

    private suspend fun <T> apiCall(block: suspend () -> Response<T>): ApiResult<T> =
        runCatching { block() }.fold(
            onSuccess = { resp ->
                val body = resp.body()
                if (resp.isSuccessful && body != null) ApiResult.Ok(body) else ApiResult.Err(resp.readableError())
            },
            onFailure = { ApiResult.Err(networkErrorText()) },
        )

    class Factory(private val requestId: UUID, private val api: ApiProvider) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = OutboundAssemblyViewModel(requestId, api) as T
    }
}
