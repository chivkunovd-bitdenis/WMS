package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
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
 * P6. Подтверждение действия с последствиями (02_UX_SPEC.md §P6).
 * facts — 1–3 строки итогов («Коробов: 5 из 6», «Расхождение по 2 товарам»).
 * destructive=true красит основную кнопку в Error (для действий с расхождениями).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfirmSheet(
    title: String,
    facts: List<String>,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    destructive: Boolean = false,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(title, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WmsColors.TextPrimary)
            facts.forEach { fact ->
                Text(fact, fontSize = 18.sp, color = WmsColors.TextSecondary)
            }
            Button(
                onClick = onConfirm,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (destructive) WmsColors.Error else WmsColors.Success,
                ),
                modifier = Modifier.fillMaxWidth().height(WmsDimens.PrimaryButtonHeight),
            ) {
                Text(confirmLabel, fontSize = 20.sp)
            }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth().height(WmsDimens.TouchTargetMin).padding(bottom = 16.dp),
            ) {
                Text("Отмена", fontSize = 18.sp, color = WmsColors.TextSecondary)
            }
        }
    }
}
