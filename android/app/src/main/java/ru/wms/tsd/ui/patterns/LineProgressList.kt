package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

data class LineProgress(
    val id: String,
    val title: String,       // артикул — крупно
    val subtitle: String,    // название товара — одна строка
    val done: Int,
    val total: Int,
    val photoUrl: String? = null,
)

/**
 * P4. Список строк документа с прогрессом (02_UX_SPEC.md §P4).
 * Завершённые строки уезжают вниз и сереют; активная (последний скан) подсвечена
 * и автоматически проскроллена в видимую область.
 */
@Composable
fun LineProgressList(
    lines: List<LineProgress>,
    modifier: Modifier = Modifier,
    activeId: String? = null,
    /** Тап по строке (напр. ручной ввод количества в приёмке). null — строки не кликабельны. */
    onLineClick: ((String) -> Unit)? = null,
    state: LazyListState = rememberLazyListState(),
) {
    val sorted = lines.sortedBy { it.total in 1..it.done } // незавершённые сверху, порядок стабилен
    LaunchedEffect(activeId) {
        if (activeId == null) return@LaunchedEffect
        val idx = sorted.indexOfFirst { it.id == activeId }
        if (idx >= 0) state.animateScrollToItem(idx)
    }
    LazyColumn(
        state = state,
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
    ) {
        items(sorted, key = { it.id }) { line ->
            LineProgressCard(line, isActive = line.id == activeId, onClick = onLineClick?.let { { it(line.id) } })
        }
    }
}

@Composable
private fun LineProgressCard(line: LineProgress, isActive: Boolean, onClick: (() -> Unit)? = null) {
    val completed = line.total in 1..line.done
    val cardColor = when {
        isActive -> WmsColors.Primary.copy(alpha = 0.08f)
        completed -> WmsColors.Background
        else -> WmsColors.Surface
    }
    Surface(
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        color = cardColor,
        shadowElevation = if (completed) 0.dp else 1.dp,
        modifier = if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (line.photoUrl != null) {
                AsyncImage(
                    model = line.photoUrl,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(48.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(WmsColors.Background),
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    line.title,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (completed) WmsColors.TextSecondary else WmsColors.TextPrimary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    line.subtitle,
                    fontSize = 14.sp,
                    color = WmsColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (line.total > 0) {
                    LinearProgressIndicator(
                        progress = { (line.done.toFloat() / line.total).coerceIn(0f, 1f) },
                        color = if (completed) WmsColors.Success else WmsColors.Primary,
                        modifier = Modifier.fillMaxWidth().height(4.dp).padding(top = 6.dp),
                    )
                }
            }
            Text(
                "${line.done} / ${line.total}",
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = when {
                    completed -> WmsColors.Success
                    line.done > line.total && line.total > 0 -> WmsColors.Warning
                    else -> WmsColors.TextPrimary
                },
            )
        }
    }
}
