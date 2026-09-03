package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * Плашка текущей цели скана («Короб №3», «Без короба», «Товар: ABC-123»)
 * с подсказкой следующего действия и кнопкой смены режима/сброса.
 */
@Composable
fun ScanTargetBar(
    text: String,
    hint: String,
    actionLabel: String?,
    onAction: () -> Unit,
) {
    Surface(
        color = WmsColors.Primary.copy(alpha = 0.08f),
        shape = RoundedCornerShape(WmsDimens.CornerRadius),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WmsColors.Primary)
                Text(hint, fontSize = 16.sp, color = WmsColors.TextSecondary)
            }
            if (actionLabel != null) {
                TextButton(onClick = onAction) { Text(actionLabel, fontSize = 16.sp) }
            }
        }
    }
}
