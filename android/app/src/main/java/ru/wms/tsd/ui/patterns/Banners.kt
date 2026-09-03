package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.ui.theme.WmsColors

/**
 * P8. Ошибка загрузки данных на весь экран с кнопкой повтора (02_UX_SPEC.md §P8).
 * Для ошибок конкретного действия (скан, кнопка) используется ScanFlash.Error.
 */
@Composable
fun FullScreenError(message: String, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(message, fontSize = 18.sp, textAlign = TextAlign.Center, color = WmsColors.TextPrimary)
        Button(onClick = onRetry) { Text("Повторить", fontSize = 18.sp) }
    }
}

/** P8. Баннер потери сети поверх экрана (операция не удалась, ввод не потерян). */
@Composable
fun OfflineBanner(onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Surface(color = WmsColors.Warning, modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Нет связи с сервером",
                fontSize = 16.sp,
                color = WmsColors.TextPrimary,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onRetry) { Text("Повторить", color = WmsColors.TextPrimary) }
        }
    }
}

/** Пустое состояние списка. */
@Composable
fun EmptyState(message: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(message, fontSize = 18.sp, textAlign = TextAlign.Center, color = WmsColors.TextSecondary)
    }
}
