package ru.wms.tsd.features.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Input
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.MoveToInbox
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import ru.wms.tsd.core.auth.AuthSession
import ru.wms.tsd.features.inbound.isReceivingStatus
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

data class HomeCounts(
    val inbound: Int? = null,
    val sorting: Int? = null,
    val outbound: Int? = null,
)

class HomeViewModel(private val api: ApiProvider) : ViewModel() {
    private val _counts = MutableStateFlow(HomeCounts())
    val counts: StateFlow<HomeCounts> = _counts

    fun load() {
        viewModelScope.launch {
            val newCounts = HomeCounts()

            // Запрос приёмки и сортировки
            runCatching { api.operations().listInboundRequestsOperationsInboundIntakeRequestsGet() }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        val requests = resp.body().orEmpty()
                        val inboundCount = requests.count { it.status == "submitted" || isReceivingStatus(it.status) }
                        val sortingCount = requests.count { (it.status == "sorting" || it.status == "verified") && (it.sortingRemainingQty ?: 0) > 0 }
                        _counts.value = newCounts.copy(inbound = inboundCount, sorting = sortingCount)
                    }
                }
                .onFailure { }

            // Запрос отгрузки
            runCatching { api.operations().listMarketplaceUnloadsOperationsMarketplaceUnloadRequestsGet() }
                .onSuccess { resp ->
                    if (resp.isSuccessful) {
                        val requests = resp.body().orEmpty()
                        val outboundCount = requests.count { it.status == "confirmed" || it.status == "collecting" }
                        _counts.value = _counts.value.copy(outbound = outboundCount)
                    }
                }
                .onFailure { }
        }
    }

    class Factory(private val api: ApiProvider) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = HomeViewModel(api) as T
    }
}

/**
 * Главный экран A2: три гигантские плитки-кнопки и инфо сотрудника внизу.
 */
@Composable
fun HomeScreen(
    session: AuthSession,
    onSectionClick: (HomeSection) -> Unit,
    onLogout: () -> Unit,
) {
    val vm: HomeViewModel = viewModel(factory = HomeViewModel.Factory(AppGraph.apiProvider))
    val counts by vm.counts.collectAsState()

    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(WmsDimens.SpacingUnit * 2),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        // Три плитки
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(WmsDimens.SpacingUnit),
        ) {
            HomeSection.values().forEach { section ->
                val count = when (section) {
                    HomeSection.INBOUND -> counts.inbound
                    HomeSection.SORTING -> counts.sorting
                    HomeSection.OUTBOUND -> counts.outbound
                }
                SectionTile(
                    section = section,
                    count = count,
                    onClick = { onSectionClick(section) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                )
            }
        }

        // Полоса инфо сотрудника
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(64.dp)
                .padding(vertical = WmsDimens.SpacingUnit),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = session.displayName,
                fontSize = 16.sp,
                color = WmsColors.TextPrimary,
            )
            TextButton(onClick = onLogout) {
                Text(
                    text = "Сменить",
                    fontSize = 16.sp,
                    color = WmsColors.Primary,
                )
            }
        }
    }
}

/**
 * Плитка-кнопка раздела.
 */
@Composable
private fun SectionTile(
    section: HomeSection,
    count: Int? = null,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
    ) {
        Box(
            modifier = Modifier.fillMaxSize(),
        ) {
            Button(
                onClick = onClick,
                modifier = Modifier.fillMaxSize(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = WmsColors.Surface,
                ),
            ) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    androidx.compose.material3.Icon(
                        imageVector = section.icon,
                        contentDescription = section.label,
                        modifier = Modifier.fillMaxWidth(0.2f),
                        tint = WmsColors.Primary,
                    )
                    Text(
                        text = section.label,
                        fontSize = 28.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = WmsColors.TextPrimary,
                        textAlign = TextAlign.Center,
                    )
                }
            }

            // Бейдж счётчика
            if (count != null && count > 0) {
                Surface(
                    shape = CircleShape,
                    color = WmsColors.Primary,
                    modifier = Modifier.align(Alignment.TopEnd).padding(12.dp),
                ) {
                    Text(
                        text = if (count > 99) "99+" else count.toString(),
                        color = WmsColors.Surface,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                    )
                }
            }
        }
    }
}

enum class HomeSection(
    val label: String,
    val icon: ImageVector,
    val route: String,
) {
    INBOUND("Приёмка", Icons.AutoMirrored.Default.Input, "inbound"),
    SORTING("Сортировка", Icons.Default.MoveToInbox, "sorting"),
    OUTBOUND("Отгрузка", Icons.Default.LocalShipping, "outbound"),
}
