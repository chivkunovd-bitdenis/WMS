package ru.wms.tsd.features.outbound

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
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadRequestSummaryOut
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.ListSkeleton
import ru.wms.tsd.ui.patterns.ScanFlash
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.TaskCardData
import ru.wms.tsd.ui.patterns.TaskList

data class OutboundListUiState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val requests: List<MarketplaceUnloadRequestSummaryOut> = emptyList(),
)

class OutboundListViewModel(private val api: ApiProvider) : ViewModel() {
    private val _state = MutableStateFlow(OutboundListUiState())
    val state: StateFlow<OutboundListUiState> = _state

    init { load(initial = true) }

    fun load(initial: Boolean = false) {
        _state.value = _state.value.copy(loading = initial, refreshing = !initial, error = null)
        viewModelScope.launch {
            runCatching { api.operations().listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        // Список отгрузок: статус "confirmed" или "collecting" (очередь работы склада)
                        val queue = resp.body().orEmpty()
                            .filter { it.status == "confirmed" || it.status == "collecting" }
                            .sortedBy { it.createdAt }
                        _state.value = OutboundListUiState(loading = false, requests = queue)
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
        override fun <T : ViewModel> create(modelClass: Class<T>): T = OutboundListViewModel(api) as T
    }
}

/** D1. Список отгрузок. */
@Composable
fun OutboundListScreen(
    onBack: () -> Unit,
    onOpenRequest: (id: String) -> Unit,
) {
    val vm: OutboundListViewModel = viewModel(factory = OutboundListViewModel.Factory(AppGraph.apiProvider))
    val state by vm.state.collectAsState()

    // Данные меняются на детальных экранах — перечитываем список при каждом возврате
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }

    ScanScaffold(
        title = "Отгрузка",
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
                            "Отгрузка ${r.displayNumber ?: r.documentNumber ?: ""}".trim(),
                            r.sellerName,
                        ).joinToString(" · "),
                        subtitle = listOfNotNull(
                            r.plannedShipmentDate?.let { "Дата: ${it.take(10)}" },
                            r.lineCount?.let { "$it позиций" },
                        ).joinToString(" · "),
                        statusText = unloadStatusRu(r.status),
                        statusColor = unloadStatusColor(r.status),
                        hasDiscrepancy = false,
                    )
                },
                isRefreshing = state.refreshing,
                onRefresh = { vm.load() },
                onTaskClick = { card ->
                    onOpenRequest(card.id)
                },
                emptyMessage = "Нет отгрузок в работе",
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}
