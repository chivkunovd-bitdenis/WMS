package ru.wms.tsd.features.inbound

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
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.core.api.generated.models.InboundBoxBarcodeBody
import ru.wms.tsd.core.api.generated.models.InboundBoxLineQuantityBody
import ru.wms.tsd.core.api.generated.models.InboundBoxScanBody
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineActualPatch
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestOut
import ru.wms.tsd.core.api.generated.models.InboundReceivingScanBody
import ru.wms.tsd.ui.patterns.ScanFlash

data class ReceivingUiState(
    val loading: Boolean = true,
    val loadError: String? = null,
    val request: InboundIntakeRequestOut? = null,
    /** id открытого короба (локально выбранный; сервер тоже хранит isOpen). */
    val openBoxId: String? = null,
    /** Режим «без короба» — включается явной кнопкой. */
    val looseMode: Boolean = false,
    val flash: ScanFlash = ScanFlash.None,
    /** productId строки, по которой был последний скан (для подсветки/автоскролла). */
    val activeProductId: String? = null,
    /** Открыт ли шит подтверждения: "close_box" | "complete" | null. */
    val confirm: String? = null,
    val completing: Boolean = false,
)

/**
 * Золотой экран (T-07): приёмка товара по коробам (B3 из 02_UX_SPEC.md).
 *
 * Правила обработки скана (порядок важен):
 * 1) штрихкод совпал с internal_barcode короба заявки → открыть этот короб;
 * 2) включён режим «без короба» → скан в loose-приёмку;
 * 3) есть открытый короб → скан товара в короб;
 * 4) иначе — ошибка «Сначала отсканируйте короб».
 * Сканы обрабатываются строго последовательно (Channel), чтобы быстрая очередь
 * сканов не перемешала счётчики. Optimistic UI запрещён — после каждого скана
 * состояние перечитывается с сервера.
 */
class InboundReceivingViewModel(
    private val requestId: UUID,
    private val api: ApiProvider,
    /** Короб, выбранный на экране коробов «начать наполнять» — делаем активным. */
    private val initialBoxId: String? = null,
) : ViewModel() {

    private val _state = MutableStateFlow(ReceivingUiState())
    val state: StateFlow<ReceivingUiState> = _state

    private val scanQueue = Channel<String>(capacity = 16)
    private var flashStamp = 0L
    private var initialBoxApplied = false

    init {
        load()
        viewModelScope.launch {
            for (barcode in scanQueue) processScan(barcode)
        }
    }

    fun load() {
        _state.value = _state.value.copy(loading = true, loadError = null)
        viewModelScope.launch {
            runCatching { api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId) }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        val req = resp.body()
                        // При первом заходе выбираем активный короб: явно выбранный на
                        // экране коробов (initialBoxId) важнее авто-подхвата открытого на
                        // сервере. Применяем ОДИН раз, чтобы не перебивать переключения.
                        val pick = if (!initialBoxApplied) {
                            initialBoxApplied = true
                            initialBoxId ?: req?.boxes.orEmpty().firstOrNull { it.isOpen == true }?.id
                        } else null
                        _state.value = _state.value.copy(
                            loading = false,
                            request = req,
                            openBoxId = _state.value.openBoxId ?: pick,
                        )
                    } else {
                        _state.value = _state.value.copy(loading = false, loadError = resp.readableError())
                    }
                }
                .onFailure {
                    _state.value = _state.value.copy(loading = false, loadError = networkErrorText())
                }
        }
    }

    fun onScan(barcode: String) {
        scanQueue.trySend(barcode)
    }

    /** Тихое обновление (без спиннера) — напр. при возврате с экрана коробов. */
    fun reloadSilently() {
        viewModelScope.launch { refresh() }
    }

    /**
     * Ручной ввод количества «без короба» (loose) — навал/немаркированный товар.
     * Задаёт АБСОЛЮТНЫЙ loose-факт для строки через PATCH .../actual.
     */
    fun setLineActualQty(lineId: String, productId: String, quantity: Int) {
        viewModelScope.launch {
            val result = apiCall {
                api.operations().patchInboundLineActualOperationsInboundIntakeRequestsRequestIdLinesLineIdActualPatch(
                    requestId, UUID.fromString(lineId), InboundIntakeLineActualPatch(actualQty = quantity),
                )
            }
            applyManualResult(result, productId)
        }
    }

    /**
     * Ручной ввод количества товара В ОТКРЫТЫЙ КОРОБ (навал в короб — когда
     * сканировать по штуке нельзя). Задаёт абсолютное кол-во товара в коробе.
     */
    fun setBoxLineQuantity(boxId: String, productId: String, quantity: Int) {
        viewModelScope.launch {
            val result = apiCall {
                api.operations().setInboundBoxLineQuantityOperationsInboundIntakeRequestsRequestIdBoxesBoxIdLinesProductIdPut(
                    requestId, UUID.fromString(boxId), UUID.fromString(productId),
                    InboundBoxLineQuantityBody(quantity = quantity),
                )
            }
            applyManualResult(result, productId)
        }
    }

    private suspend fun applyManualResult(result: ApiResult<*>, productId: String) {
        when (result) {
            is ApiResult.Ok -> {
                _state.value = _state.value.copy(flash = successFlash(), activeProductId = productId)
                refresh()
            }
            is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
        }
    }

    fun setLooseMode(enabled: Boolean) {
        _state.value = _state.value.copy(looseMode = enabled, openBoxId = if (enabled) null else _state.value.openBoxId)
    }

    fun requestCloseBox() {
        if (_state.value.openBoxId != null) _state.value = _state.value.copy(confirm = "close_box")
    }

    fun requestComplete() {
        _state.value = _state.value.copy(confirm = "complete")
    }

    fun dismissConfirm() {
        _state.value = _state.value.copy(confirm = null)
    }

    fun confirmCloseBox() {
        val boxId = _state.value.openBoxId ?: return
        _state.value = _state.value.copy(confirm = null)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().closeInboundBoxIntakeOperationsInboundIntakeRequestsRequestIdBoxesBoxIdClosePost(
                    requestId, UUID.fromString(boxId),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(openBoxId = null, flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    /** Завершить пересчёт (complete-receiving). onDone — навигация назад. */
    fun confirmComplete(onDone: () -> Unit) {
        _state.value = _state.value.copy(confirm = null, completing = true)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().completeInboundReceivingOperationsInboundIntakeRequestsRequestIdCompleteReceivingPost(requestId)
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

        // 1) Скан короба?
        val box = request.boxes.orEmpty().firstOrNull { it.internalBarcode == barcode }
        if (box != null) {
            val result = apiCall {
                api.operations().openInboundBoxByBarcodeOperationsInboundIntakeRequestsRequestIdBoxesOpenPost(
                    requestId, InboundBoxBarcodeBody(barcode),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(
                        openBoxId = result.value.id,
                        looseMode = false,
                        flash = successFlash(),
                    )
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
            return
        }

        // 2) Режим «без короба»
        if (st.looseMode) {
            val result = apiCall {
                api.operations().scanBarcodeToLooseIntakeOperationsInboundIntakeRequestsRequestIdReceivingScanPost(
                    requestId, InboundReceivingScanBody(barcode),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(flash = successFlash(), activeProductId = result.value.productId)
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
            return
        }

        // 3) Скан товара в открытый короб
        val openBoxId = st.openBoxId
        if (openBoxId != null) {
            val result = apiCall {
                api.operations().scanProductIntoInboundBoxOperationsInboundIntakeRequestsRequestIdBoxesBoxIdScanPost(
                    requestId, UUID.fromString(openBoxId), InboundBoxScanBody(barcode),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(flash = successFlash(), activeProductId = result.value.productId)
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
            return
        }

        // 4) Некуда сканировать
        _state.value = _state.value.copy(flash = errorFlash("Сначала отсканируйте штрихкод короба"))
    }

    /** Тихое обновление данных с сервера (без спиннера на весь экран). */
    private suspend fun refresh() {
        runCatching { api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId) }
            .onSuccess { resp ->
                if (resp.isSuccessful) _state.value = _state.value.copy(request = resp.body())
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

    class Factory(
        private val requestId: UUID,
        private val api: ApiProvider,
        private val initialBoxId: String? = null,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            InboundReceivingViewModel(requestId, api, initialBoxId) as T
    }
}
