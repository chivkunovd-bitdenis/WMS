package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

data class TaskCardData(
    val id: String,
    val title: String,      // «Поставка №123 · Селлер»
    val subtitle: String,   // дата, комментарий
    val statusText: String,
    val statusColor: Color, // WmsColors.Primary/Success/Warning
    val countsText: String? = null, // «120 шт план / 118 факт»
    val hasDiscrepancy: Boolean = false,
)

/**
 * P2. Список заданий с pull-to-refresh (02_UX_SPEC.md §P2).
 * Фильтры по статусу экран добавляет сверху сам (чипами) — сюда приходит уже
 * отфильтрованный список.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskList(
    tasks: List<TaskCardData>,
    isRefreshing: Boolean,
    onRefresh: () -> Unit,
    onTaskClick: (TaskCardData) -> Unit,
    modifier: Modifier = Modifier,
    emptyMessage: String = "Пока нет заданий",
) {
    PullToRefreshBox(isRefreshing = isRefreshing, onRefresh = onRefresh, modifier = modifier.fillMaxSize()) {
        if (tasks.isEmpty()) {
            // Внутри PullToRefreshBox нужен скроллируемый контейнер даже для пустого состояния
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                item { EmptyState(emptyMessage, modifier = Modifier.padding(top = 120.dp)) }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(16.dp),
            ) {
                items(tasks, key = { it.id }) { task ->
                    TaskCard(task, onClick = { onTaskClick(task) })
                }
            }
        }
    }
}

@Composable
private fun TaskCard(task: TaskCardData, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = WmsColors.Surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    task.title,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (task.hasDiscrepancy) {
                    Icon(
                        Icons.Default.Warning,
                        contentDescription = "Есть расхождения",
                        tint = WmsColors.Warning,
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
            }
            Text(task.subtitle, fontSize = 14.sp, color = WmsColors.TextSecondary, maxLines = 1)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = task.statusColor.copy(alpha = 0.12f),
                ) {
                    Text(
                        task.statusText,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        color = task.statusColor,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                }
                if (task.countsText != null) {
                    Text(task.countsText, fontSize = 14.sp, color = WmsColors.TextSecondary)
                }
            }
        }
    }
}
