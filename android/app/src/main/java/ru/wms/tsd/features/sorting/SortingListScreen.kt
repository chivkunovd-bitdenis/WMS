package ru.wms.tsd.features.sorting

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
import ru.wms.tsd.features.inbound.isSortingStatus
import ru.wms.tsd.features.inbound.inboundStatusColor
import ru.wms.tsd.features.inbound.inboundStatusRu
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.ListSkeleton
import ru.wms.tsd.ui.patterns.ScanFlash
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.TaskCardData
import ru.wms.tsd.ui.patterns.TaskList
import ru.wms.tsd.ui.theme.WmsColors

data class SortingListUiState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val requests: List<InboundIntakeRequestSummaryOut> = emptyList(),
)

class SortingListViewModel(private val api: ApiProvider) : ViewModel() {
    private val _state = MutableStateFlow(SortingListUiState())
    val state: StateFlow<SortingListUiState> = _state

    init { load(initial = true) }

    fun load(initial: Boolean = false) {
        _state.value = _state.value.copy(loading = initial, refreshing = !initial, error = null)
        viewModelScope.launch {
            runCatching { api.operations().listInboundRequestsOperationsInboundIntakeRequestsGet() }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        // Список к размещению: статус "sorting" или "verified" и sortingRemainingQty > 0
                        val queue = resp.body().orEmpty()
                            .filter { (it.status == "sorting" || it.status == "verified") && (it.sortingRemainingQty ?: 0) > 0 }
                            .sortedBy { it.createdAt }
                        _state.value = SortingListUiState(loading = false, requests = queue)
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
        override fun <T : ViewModel> create(modelClass: Class<T>): T = SortingListViewModel(api) as T
    }
}

/** C1. Список к размещению (сортировка). */
@Composable
fun SortingListScreen(
    onBack: () -> Unit,
    onOpenRequest: (id: String) -> Unit,
) {
    val vm: SortingListViewModel = viewModel(factory = SortingListViewModel.Factory(AppGraph.apiProvider))
    val state by vm.state.collectAsState()

    // Данные меняются на детальных экранах — перечитываем список при каждом возврате
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }

    ScanScaffold(
        title = "Сортировка",
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
                        subtitle = "Осталось разместить: ${r.sortingRemainingQty ?: 0} шт",
                        statusText = "В сортировке",
                        statusColor = WmsColors.Primary,
                        hasDiscrepancy = false,
                    )
                },
                isRefreshing = state.refreshing,
                onRefresh = { vm.load() },
                onTaskClick = { card ->
                    onOpenRequest(card.id)
                },
                emptyMessage = "Нет заявок к размещению",
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}
