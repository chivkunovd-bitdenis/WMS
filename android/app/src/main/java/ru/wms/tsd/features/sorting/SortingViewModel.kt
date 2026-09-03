package ru.wms.tsd.features.sorting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.util.UUID
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.core.api.generated.models.InboundBoxPutawayBody
import ru.wms.tsd.core.api.generated.models.InboundDistributionLineIn
import ru.wms.tsd.core.api.generated.models.InboundDistributionLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeBoxOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestOut
import ru.wms.tsd.core.api.generated.models.LocationOut
import ru.wms.tsd.ui.patterns.ScanFlash

/** Что размещаем: закрытый короб целиком или товар из loose-пула. */
sealed interface SortTarget {
    data class Box(val boxId: String) : SortTarget
    data class Loose(val productId: String) : SortTarget
}

data class SortingUiState(
    val loading: Boolean = true,
    val loadError: String? = null,
    val request: InboundIntakeRequestOut? = null,
    val distLines: List<InboundDistributionLineOut> = emptyList(),
    val locations: List<LocationOut> = emptyList(),
    val target: SortTarget? = null,
    /** Отсканированная ячейка — при ненулевом значении открыт шит подтверждения. */
    val pendingLocation: LocationOut? = null,
    val flash: ScanFlash = ScanFlash.None,
    val confirmComplete: Boolean = false,
    val completing: Boolean = false,
)

/**
 * T-12. Размещение по ячейкам (C2 из 02_UX_SPEC.md). Сделан по образцу золотого
 * экрана (InboundReceivingViewModel): последовательные сканы через Channel,
 * после каждой мутации — перечитывание с сервера.
 *
 * Цикл: скан короба (или тап по товару из loose-пула) → скан ячейки →
 * подтверждение (для loose — с количеством) → размещение.
 * Короб размещается целиком (частичное размещение — в вебе).
 * Товар без короба добавляется строкой в distribution-lines (PUT заменяет весь
 * список, поэтому шлём текущие строки + новую).
 */
class SortingViewModel(
    private val requestId: UUID,
    private val api: ApiProvider,
) : ViewModel() {

    private val _state = MutableStateFlow(SortingUiState())
    val state: StateFlow<SortingUiState> = _state

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
            val ok = runCatching {
                coroutineScope {
                    val reqD = async { api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId) }
                    val distD = async { api.operations().listDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesGet(requestId) }
                    val req = reqD.await()
                    val dist = distD.await()
                    if (!req.isSuccessful) return@coroutineScope req.readableError()
                    val request = req.body() ?: return@coroutineScope "Пустой ответ сервера"
                    val locs = api.warehouses().listLocationsWarehousesWarehouseIdLocationsGet(
                        UUID.fromString(request.warehouseId), excludeSortingZone = true,
                    )
                    _state.value = _state.value.copy(
                        loading = false,
                        request = request,
                        distLines = dist.body().orEmpty(),
                        locations = locs.body().orEmpty(),
                    )
                    null
                }
            }.getOrElse { networkErrorText() }
            if (ok != null) _state.value = _state.value.copy(loading = false, loadError = ok)
        }
    }

    fun onScan(barcode: String) {
        scanQueue.trySend(barcode)
    }

    fun selectLooseProduct(productId: String) {
        _state.value = _state.value.copy(target = SortTarget.Loose(productId), pendingLocation = null)
    }

    fun selectBox(boxId: String) {
        _state.value = _state.value.copy(target = SortTarget.Box(boxId), pendingLocation = null)
    }

    fun clearTarget() {
        _state.value = _state.value.copy(target = null, pendingLocation = null)
    }

    fun dismissPending() {
        _state.value = _state.value.copy(pendingLocation = null)
    }

    fun requestComplete() {
        _state.value = _state.value.copy(confirmComplete = true)
    }

    fun dismissComplete() {
        _state.value = _state.value.copy(confirmComplete = false)
    }

    /** Подтверждение размещения короба целиком в отсканированную ячейку. */
    fun confirmBoxPutaway() {
        val st = _state.value
        val boxId = (st.target as? SortTarget.Box)?.boxId ?: return
        val location = st.pendingLocation ?: return
        _state.value = st.copy(pendingLocation = null)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().putawayInboundBoxOperationsInboundIntakeRequestsRequestIdBoxesBoxIdPutawayPost(
                    requestId, UUID.fromString(boxId),
                    InboundBoxPutawayBody(storageLocationId = UUID.fromString(location.id)),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(target = null, flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    /** Подтверждение размещения товара без короба (с количеством). */
    fun confirmLoosePutaway(quantity: Int) {
        val st = _state.value
        val productId = (st.target as? SortTarget.Loose)?.productId ?: return
        val location = st.pendingLocation ?: return
        if (quantity <= 0) return
        _state.value = st.copy(pendingLocation = null)
        viewModelScope.launch {
            // PUT заменяет ВЕСЬ список distribution-lines. Чтобы не перезатереть
            // размещение, сделанное только что (своё, чей refresh ещё не вернулся,
            // или другого сортировщика этой заявки), берём СВЕЖИЙ список с сервера
            // прямо перед merge — окно гонки сужается до одного GET+PUT.
            val freshResp = runCatching {
                api.operations().listDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesGet(requestId)
            }.getOrNull()
            val baseLines = freshResp?.takeIf { it.isSuccessful }?.body() ?: st.distLines
            val existing = baseLines.map {
                InboundDistributionLineIn(
                    productId = UUID.fromString(it.productId),
                    storageLocationId = UUID.fromString(it.storageLocationId),
                    quantity = it.quantity,
                    boxId = it.boxId?.let(UUID::fromString),
                )
            }
            val merged = existing.toMutableList()
            val sameIdx = merged.indexOfFirst {
                it.boxId == null && it.productId.toString() == productId && it.storageLocationId.toString() == location.id
            }
            if (sameIdx >= 0) {
                val old = merged[sameIdx]
                merged[sameIdx] = old.copy(quantity = old.quantity + quantity)
            } else {
                merged += InboundDistributionLineIn(
                    productId = UUID.fromString(productId),
                    storageLocationId = UUID.fromString(location.id),
                    quantity = quantity,
                )
            }
            val result = apiCall {
                api.operations().replaceDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesPut(
                    requestId, merged,
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(target = null, flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    fun confirmComplete(onDone: () -> Unit) {
        _state.value = _state.value.copy(confirmComplete = false, completing = true)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().completeDistributionOperationsInboundIntakeRequestsRequestIdDistributionCompletePost(requestId)
            }
            when (result) {
                is ApiResult.Ok -> onDone()
                is ApiResult.Err ->
                    _state.value = _state.value.copy(completing = false, flash = errorFlash(result.message))
            }
        }
    }

    private suspend fun processScan(barcode: String) {
        val st = _state.value
        val request = st.request ?: return

        // 1) Скан закрытого короба с остатком?
        val box = request.boxes.orEmpty().firstOrNull { it.internalBarcode == barcode }
        if (box != null) {
            if (boxRemaining(box) <= 0) {
                _state.value = st.copy(flash = errorFlash("Короб №${box.boxNumber} уже размещён"))
            } else if (box.intakeClosedAt == null) {
                _state.value = st.copy(flash = errorFlash("Короб №${box.boxNumber} не закрыт в приёмке"))
            } else {
                _state.value = st.copy(target = SortTarget.Box(box.id), pendingLocation = null, flash = successFlash())
            }
            return
        }

        // 2) Скан ячейки?
        val location = st.locations.firstOrNull { it.barcode == barcode }
        if (location != null) {
            if (st.target == null) {
                _state.value = st.copy(flash = errorFlash("Сначала отсканируйте короб или выберите товар"))
            } else {
                _state.value = st.copy(pendingLocation = location, flash = successFlash())
            }
            return
        }

        _state.value = st.copy(flash = errorFlash("Штрихкод не распознан: не короб этой поставки и не ячейка"))
    }

    private suspend fun refresh() {
        runCatching {
            val req = api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
            val dist = api.operations().listDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesGet(requestId)
            if (req.isSuccessful) {
                _state.value = _state.value.copy(
                    request = req.body(),
                    distLines = dist.body() ?: _state.value.distLines,
                )
            }
        }
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
        override fun <T : ViewModel> create(modelClass: Class<T>): T = SortingViewModel(requestId, api) as T
    }
}

/** Осталось разместить из короба. */
fun boxRemaining(box: InboundIntakeBoxOut): Int =
    box.remainingQty ?: box.lines.orEmpty().sumOf { it.remainingQty ?: 0 }

/**
 * Осталось разместить «без короба» по товару:
 * общий остаток строки (принято − размещено) минус неразмещённое в коробах.
 */
fun looseRemaining(line: InboundIntakeLineOut, boxes: List<InboundIntakeBoxOut>): Int {
    val lineRemaining = (line.actualQty ?: 0) - line.postedQty
    val inBoxes = boxes.sumOf { box ->
        box.lines.orEmpty().filter { it.productId == line.productId }.sumOf { it.remainingQty ?: 0 }
    }
    return (lineRemaining - inBoxes).coerceAtLeast(0)
}
