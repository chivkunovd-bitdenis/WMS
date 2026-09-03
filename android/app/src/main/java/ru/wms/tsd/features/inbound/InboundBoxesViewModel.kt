package ru.wms.tsd.features.inbound

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestOut
import ru.wms.tsd.ui.patterns.ScanFlash

data class BoxesUiState(
    val loading: Boolean = true,
    val loadError: String? = null,
    val request: InboundIntakeRequestOut? = null,
    val flash: ScanFlash = ScanFlash.None,
    val deleting: String? = null, // boxId that's being deleted
)

/**
 * B2. Приёмка по коробам — управление список коробов и их этикетками.
 * Экран создания коробов и печати этикеток перед приёмкой товара (B3).
 */
class InboundBoxesViewModel(
    private val requestId: UUID,
    private val api: ApiProvider,
) : ViewModel() {

    private val _state = MutableStateFlow(BoxesUiState())
    val state: StateFlow<BoxesUiState> = _state

    private var flashStamp = 0L

    init {
        load()
    }

    fun load() {
        _state.value = _state.value.copy(loading = true, loadError = null)
        viewModelScope.launch {
            runCatching { api.operations().getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId) }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        val req = resp.body()
                        _state.value = _state.value.copy(
                            loading = false,
                            request = req,
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

    fun createBox() {
        viewModelScope.launch {
            val result = apiCall {
                api.operations().createInboundBoxOperationsInboundIntakeRequestsRequestIdBoxesPost(requestId)
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    fun markLabelPrinted(boxId: String) {
        viewModelScope.launch {
            val result = apiCall {
                api.operations().markInboundBoxLabelPrintedOperationsInboundIntakeRequestsRequestIdBoxesBoxIdMarkLabelPrintedPost(
                    requestId, UUID.fromString(boxId),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

    fun requestDeleteBox(boxId: String) {
        _state.value = _state.value.copy(deleting = boxId)
    }

    fun dismissDeleteConfirm() {
        _state.value = _state.value.copy(deleting = null)
    }

    fun confirmDeleteBox() {
        val boxId = _state.value.deleting ?: return
        _state.value = _state.value.copy(deleting = null)
        viewModelScope.launch {
            val result = apiCall {
                api.operations().deleteInboundBoxOperationsInboundIntakeRequestsRequestIdBoxesBoxIdDelete(
                    requestId, UUID.fromString(boxId),
                )
            }
            when (result) {
                is ApiResult.Ok -> {
                    _state.value = _state.value.copy(flash = successFlash())
                    refresh()
                }
                is ApiResult.Err -> _state.value = _state.value.copy(flash = errorFlash(result.message))
            }
        }
    }

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

    class Factory(private val requestId: UUID, private val api: ApiProvider) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            InboundBoxesViewModel(requestId, api) as T
    }
}
