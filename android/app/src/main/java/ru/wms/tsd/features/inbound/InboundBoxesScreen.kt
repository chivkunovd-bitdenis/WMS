package ru.wms.tsd.features.inbound

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.LocalPrintshop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.UUID
import ru.wms.tsd.AppGraph
import ru.wms.tsd.ui.patterns.ConfirmSheet
import ru.wms.tsd.ui.patterns.FullScreenError
import ru.wms.tsd.ui.patterns.ScanScaffold
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * B2. Приёмка по коробам — экран создания и управления коробами перед приёмкой товара.
 * Содержит список созданных коробов с возможностью:
 * - Отметить этикетку как напечатанную
 * - Удалить пустой короб
 * - Создать новый короб
 * - Перейти к приёмке товара (B3)
 */
@Composable
fun InboundBoxesScreen(
    requestId: String,
    onBack: () -> Unit,
    onGoToReceiving: () -> Unit,
    onSelectBox: (String) -> Unit = {},
) {
    val vm: InboundBoxesViewModel = viewModel(
        factory = InboundBoxesViewModel.Factory(UUID.fromString(requestId), AppGraph.apiProvider),
    )
    val state by vm.state.collectAsState()

    val request = state.request
    val boxes = request?.boxes.orEmpty()

    ScanScaffold(
        title = "Короба ${request?.displayNumber ?: request?.documentNumber ?: ""}".trim(),
        subtitle = request?.sellerName,
        flash = state.flash,
        onExit = onBack,
        progressDone = null, // No progress bar for B2
        progressTotal = null,
        primaryActionLabel = when {
            state.loading || state.loadError != null -> null
            else -> "К приёмке товара"
        },
        onPrimaryAction = onGoToReceiving,
    ) {
        when {
            state.loading -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) { CircularProgressIndicator() }

            state.loadError != null -> FullScreenError(state.loadError!!, onRetry = vm::load)

            else -> Column(modifier = Modifier.fillMaxSize()) {
                // Плашка плана
                Surface(
                    color = when {
                        request?.plannedBoxCount != null && boxes.size != request.plannedBoxCount -> WmsColors.Warning.copy(alpha = 0.12f)
                        else -> WmsColors.Primary.copy(alpha = 0.08f)
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                ) {
                    Text(
                        text = "План: ${request?.plannedBoxCount ?: "—"} коробов · Создано: ${boxes.size}",
                        fontSize = 16.sp,
                        color = when {
                            request?.plannedBoxCount != null && boxes.size != request.plannedBoxCount -> WmsColors.Warning
                            else -> WmsColors.TextPrimary
                        },
                        modifier = Modifier.padding(12.dp),
                    )
                }

                // Список коробов
                if (boxes.isEmpty()) {
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth(),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            text = "Нет созданных коробов",
                            fontSize = 16.sp,
                            color = WmsColors.TextSecondary,
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 8.dp),
                    ) {
                        items(boxes, key = { it.id }) { box ->
                            BoxCard(
                                box = box,
                                onClick = { onSelectBox(box.id) },
                                onMarkLabelPrinted = { vm.markLabelPrinted(box.id) },
                                onDelete = { vm.requestDeleteBox(box.id) },
                            )
                        }
                    }
                }

                // Кнопка добавить короб — только пока сервер разрешает (submitted/receiving).
                // Позже (verifying и далее) короба уже не создать — показываем пояснение.
                if (canCreateInboundBox(request?.status)) {
                    FilledTonalButton(
                        onClick = vm::createBox,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 12.dp)
                            .then(Modifier.padding(bottom = 8.dp)),
                    ) {
                        Text(
                            text = "+ Добавить короб",
                            fontSize = 16.sp,
                            modifier = Modifier.padding(vertical = 8.dp),
                        )
                    }
                } else {
                    Text(
                        text = "Короба создаются только на этапе приёмки",
                        fontSize = 14.sp,
                        color = WmsColors.TextSecondary,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                    )
                }
            }
        }
    }

    // Delete confirmation
    val deletingBoxId = state.deleting
    if (deletingBoxId != null) {
        val box = boxes.firstOrNull { it.id == deletingBoxId }
        ConfirmSheet(
            title = "Удалить короб ${box?.boxNumber ?: ""}?",
            facts = emptyList(),
            confirmLabel = "Удалить",
            destructive = true,
            onConfirm = vm::confirmDeleteBox,
            onDismiss = vm::dismissDeleteConfirm,
        )
    }
}

@Composable
private fun BoxCard(
    box: ru.wms.tsd.core.api.generated.models.InboundIntakeBoxOut,
    onClick: () -> Unit,
    onMarkLabelPrinted: () -> Unit,
    onDelete: () -> Unit,
) {
    Surface(
        color = WmsColors.Surface,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Короб №${box.boxNumber} · наполнять →",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = WmsColors.Primary,
                )
                Text(
                    text = box.internalBarcode,
                    fontSize = 20.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Bold,
                    color = WmsColors.TextPrimary,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                // Print button
                IconButton(
                    onClick = onMarkLabelPrinted,
                    modifier = Modifier.padding(0.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.LocalPrintshop,
                        contentDescription = "Отметить этикетку как напечатанную",
                        tint = if (box.labelPrintedAt == null) WmsColors.Primary else WmsColors.Success,
                    )
                }

                // Delete button (только если короб пустой)
                if (box.lines.orEmpty().isEmpty()) {
                    IconButton(
                        onClick = onDelete,
                        modifier = Modifier.padding(0.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Default.DeleteOutline,
                            contentDescription = "Удалить короб",
                            tint = WmsColors.Error,
                        )
                    }
                }
            }
        }
    }
}
