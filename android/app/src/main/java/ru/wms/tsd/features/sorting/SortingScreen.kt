package ru.wms.tsd.features.sorting

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.UUID
import ru.wms.tsd.AppGraph
import ru.wms.tsd.ui.patterns.ConfirmSheet
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.QtyInput
import ru.wms.tsd.ui.patterns.ScanPrompt
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.patterns.ScanTargetBar
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * C2. Размещение по ячейкам (T-12).
 * Цикл: скан короба / тап по товару → скан ячейки → подтверждение → размещение.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SortingScreen(
    requestId: String,
    onBack: () -> Unit,
) {
    val vm: SortingViewModel = viewModel(
        factory = SortingViewModel.Factory(UUID.fromString(requestId), AppGraph.apiProvider),
    )
    val state by vm.state.collectAsState()

    LaunchedEffect(Unit) {
        AppGraph.scannerManager.scans.collect { vm.onScan(it.barcode) }
    }

    val request = state.request
    val boxes = request?.boxes.orEmpty()
    val lines = request?.lines.orEmpty()
    val totalAccepted = lines.sumOf { it.actualQty ?: 0 }
    val remaining = request?.sortingRemainingQty ?: 0
    val target = state.target

    ScanScaffold(
        title = "Размещение ${request?.displayNumber ?: request?.documentNumber ?: ""}".trim(),
        subtitle = request?.sellerName,
        flash = state.flash,
        onExit = onBack,
        progressDone = (totalAccepted - remaining).coerceAtLeast(0),
        progressTotal = totalAccepted,
        primaryActionLabel = if (!state.loading && state.loadError == null && remaining == 0) "Завершить размещение" else null,
        primaryActionEnabled = !state.completing,
        onPrimaryAction = vm::requestComplete,
    ) {
        when {
            state.loading -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) { CircularProgressIndicator() }

            state.loadError != null -> FullScreenError(state.loadError!!, onRetry = vm::load)

            else -> Column(modifier = Modifier.fillMaxSize()) {
                when (target) {
                    is SortTarget.Box -> {
                        val box = boxes.firstOrNull { it.id == target.boxId }
                        ScanTargetBar(
                            text = "Короб №${box?.boxNumber ?: ""}",
                            hint = "Теперь отсканируйте ячейку",
                            actionLabel = "Отмена",
                            onAction = vm::clearTarget,
                        )
                    }
                    is SortTarget.Loose -> {
                        val line = lines.firstOrNull { it.productId == target.productId }
                        ScanTargetBar(
                            text = line?.skuCode ?: "Товар",
                            hint = "Теперь отсканируйте ячейку",
                            actionLabel = "Отмена",
                            onAction = vm::clearTarget,
                        )
                    }
                    null -> ScanPrompt(
                        icon = Icons.Default.Inventory2,
                        text = "Отсканируйте короб",
                        hint = "или выберите товар без короба из списка",
                    )
                }

                SortingWorkList(
                    state = state,
                    onBoxClick = vm::selectBox,
                    onLooseClick = vm::selectLooseProduct,
                )
            }
        }
    }

    val pending = state.pendingLocation
    if (pending != null && target is SortTarget.Box) {
        val box = boxes.firstOrNull { it.id == target.boxId }
        ConfirmSheet(
            title = "Разместить короб №${box?.boxNumber ?: ""}?",
            facts = listOf(
                "${box?.let(::boxRemaining) ?: 0} шт",
                "В ячейку ${pending.code}",
            ),
            confirmLabel = "Разместить",
            onConfirm = vm::confirmBoxPutaway,
            onDismiss = vm::dismissPending,
        )
    }
    if (pending != null && target is SortTarget.Loose) {
        val line = lines.firstOrNull { it.productId == target.productId }
        val maxQty = line?.let { looseRemaining(it, boxes) } ?: 0
        var qty by remember(pending, target) { mutableIntStateOf(maxQty) }
        ModalBottomSheet(onDismissRequest = vm::dismissPending) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    "${line?.skuCode ?: ""} → ячейка ${pending.code}",
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                    color = WmsColors.TextPrimary,
                )
                QtyInput(
                    value = qty,
                    onValueChange = { qty = it },
                    min = 1,
                    max = maxQty,
                    maxHint = "Осталось разместить $maxQty",
                )
                Button(
                    onClick = { vm.confirmLoosePutaway(qty) },
                    enabled = qty in 1..maxQty,
                    colors = ButtonDefaults.buttonColors(containerColor = WmsColors.Success),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 24.dp)
                        .height(WmsDimens.PrimaryButtonHeight),
                ) { Text("Разместить", fontSize = 20.sp) }
            }
        }
    }

    if (state.confirmComplete) {
        ConfirmSheet(
            title = "Завершить размещение?",
            facts = listOf("Размещено $totalAccepted из $totalAccepted шт", "Заявка будет оприходована"),
            confirmLabel = "Завершить",
            onConfirm = { vm.confirmComplete(onDone = onBack) },
            onDismiss = vm::dismissComplete,
        )
    }
}

/** Список работы: неразмещённые короба + товары loose-пула. */
@Composable
private fun SortingWorkList(
    state: SortingUiState,
    onBoxClick: (String) -> Unit,
    onLooseClick: (String) -> Unit,
) {
    val boxes = state.request?.boxes.orEmpty()
        .filter { boxRemaining(it) > 0 && it.intakeClosedAt != null }
        .sortedBy { it.boxNumber }
    val loose = state.request?.lines.orEmpty()
        .map { it to looseRemaining(it, state.request?.boxes.orEmpty()) }
        .filter { it.second > 0 }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(16.dp),
    ) {
        if (boxes.isNotEmpty()) {
            item { SectionHeader("Короба") }
            items(boxes, key = { it.id }) { box ->
                WorkCard(
                    title = "Короб №${box.boxNumber}",
                    subtitle = box.internalBarcode,
                    qtyText = "${boxRemaining(box)} шт",
                    onClick = { onBoxClick(box.id) },
                )
            }
        }
        if (loose.isNotEmpty()) {
            item { SectionHeader("Без короба") }
            items(loose, key = { it.first.productId }) { (line, rem) ->
                WorkCard(
                    title = line.skuCode,
                    subtitle = line.productName,
                    qtyText = "$rem шт",
                    onClick = { onLooseClick(line.productId) },
                )
            }
        }
        if (boxes.isEmpty() && loose.isEmpty()) {
            item {
                Text(
                    "Всё размещено",
                    fontSize = 18.sp,
                    color = WmsColors.Success,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(24.dp),
                )
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
        color = WmsColors.TextSecondary,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun WorkCard(title: String, subtitle: String, qtyText: String, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    title,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = WmsColors.TextPrimary,
                )
                Text(
                    subtitle,
                    fontSize = 14.sp,
                    color = WmsColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(qtyText, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = WmsColors.Primary)
        }
    }
}
