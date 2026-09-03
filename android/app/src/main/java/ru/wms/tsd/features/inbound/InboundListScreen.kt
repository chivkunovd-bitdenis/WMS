package ru.wms.tsd.features.inbound

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.wms.tsd.AppGraph
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.networkErrorText
import ru.wms.tsd.core.api.readableError
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestSummaryOut
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.ListSkeleton
import ru.wms.tsd.ui.patterns.ScanFlash
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.TaskCardData
import ru.wms.tsd.ui.patterns.TaskList

data class InboundListUiState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val requests: List<InboundIntakeRequestSummaryOut> = emptyList(),
)

class InboundListViewModel(private val api: ApiProvider) : ViewModel() {
    private val _state = MutableStateFlow(InboundListUiState())
    val state: StateFlow<InboundListUiState> = _state

    init { load(initial = true) }

    fun load(initial: Boolean = false) {
        _state.value = _state.value.copy(loading = initial, refreshing = !initial, error = null)
        viewModelScope.launch {
            runCatching { api.operations().listInboundRequestsOperationsInboundIntakeRequestsGet() }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        // Очередь приёмки: переданные на склад и находящиеся в пересчёте (как в вебе)
                        val queue = resp.body().orEmpty()
                            .filter { it.status == "submitted" || isReceivingStatus(it.status) }
                            .sortedBy { it.plannedDeliveryDate ?: it.createdAt }
                        _state.value = InboundListUiState(loading = false, requests = queue)
                    } else {
                        _state.value = _state.value.copy(loading = false, refreshing = false, error = resp.readableError())
                    }
                }
                .onFailure {
                    _state.value = _state.value.copy(loading = false, refreshing = false, error = networkErrorText())
                }
        }
    }

    class Factory(private val api: ApiProvider) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = InboundListViewModel(api) as T
    }
}

/** B1. Очередь приёмки (список поставок). */
@Composable
fun InboundListScreen(
    onBack: () -> Unit,
    onOpenRequest: (id: String, status: String) -> Unit,
) {
    val vm: InboundListViewModel = viewModel(factory = InboundListViewModel.Factory(AppGraph.apiProvider))
    val state by vm.state.collectAsState()

    // Данные меняются на детальных экранах — перечитываем список при каждом возврате
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }

    ScanScaffold(
        title = "Приёмка",
        flash = ScanFlash.None,
        onExit = onBack,
        cameraScanner = false, // список не принимает сканы
    ) {
        when {
            state.loading -> ListSkeleton()
            state.error != null -> FullScreenError(state.error!!, onRetry = { vm.load(initial = true) })
            else -> TaskList(
                tasks = state.requests.map { r ->
                    TaskCardData(
                        id = r.id,
                        title = listOfNotNull(
                            "Поставка ${r.displayNumber ?: r.documentNumber ?: ""}".trim(),
                            r.sellerName,
                        ).joinToString(" · "),
                        subtitle = listOfNotNull(
                            r.plannedDeliveryDate?.let { "Привоз: ${it.take(10)}" },
                            "${r.lineCount} позиций",
                            r.plannedBoxCount?.let { "коробов: ${r.actualBoxCount ?: "?"} из $it" },
                        ).joinToString(" · "),
                        statusText = inboundStatusRu(r.status),
                        statusColor = inboundStatusColor(r.status),
                        hasDiscrepancy = r.hasDiscrepancy == true || r.boxesDiscrepancy == true,
                    )
                },
                isRefreshing = state.refreshing,
                onRefresh = { vm.load() },
                onTaskClick = { card ->
                    val request = state.requests.firstOrNull { it.id == card.id }
                    if (request != null) {
                        onOpenRequest(request.id, request.status)
                    }
                },
                emptyMessage = "Нет поставок в очереди приёмки",
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}
