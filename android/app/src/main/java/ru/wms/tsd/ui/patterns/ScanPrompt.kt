package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.ui.theme.WmsColors

/**
 * P3. «Отсканируйте X» — центральный элемент рабочего экрана (02_UX_SPEC.md §P3).
 * Не содержит поля ввода: сканы приходят через ScannerManager независимо от UI.
 */
@Composable
fun ScanPrompt(
    icon: ImageVector,
    text: String,
    modifier: Modifier = Modifier,
    hint: String? = null,
    lastScan: String? = null,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(icon, contentDescription = null, tint = WmsColors.Primary, modifier = Modifier.size(72.dp))
        Text(
            text,
            fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            color = WmsColors.TextPrimary,
        )
        if (hint != null) {
            Text(hint, fontSize = 16.sp, textAlign = TextAlign.Center, color = WmsColors.TextSecondary)
        }
        if (lastScan != null) {
            Text("Последний скан: $lastScan", fontSize = 14.sp, color = WmsColors.TextSecondary)
        }
    }
}
