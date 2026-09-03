package ru.wms.tsd.ui.patterns

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.wms.tsd.ui.theme.WmsColors

/**
 * P5. Ввод количества (02_UX_SPEC.md §P5): гигантские «−» и «+», крупное число,
 * цифровая клавиатура по тапу на число. Валидация диапазона — с объяснением.
 */
@Composable
fun QtyInput(
    value: Int,
    onValueChange: (Int) -> Unit,
    modifier: Modifier = Modifier,
    min: Int = 0,
    max: Int? = null,
    maxHint: String? = null, // например: «Осталось разместить 7»
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            FilledTonalButton(
                onClick = { if (value > min) onValueChange(value - 1) },
                enabled = value > min,
                modifier = Modifier.size(72.dp),
            ) { Text("−", fontSize = 32.sp) }

            OutlinedTextField(
                value = if (value == 0) "" else value.toString(),
                onValueChange = { raw ->
                    val n = raw.filter(Char::isDigit).take(6).toIntOrNull() ?: 0
                    onValueChange(if (max != null) n.coerceAtMost(max) else n)
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                textStyle = androidx.compose.ui.text.TextStyle(
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center,
                ),
                singleLine = true,
                modifier = Modifier.width(120.dp),
            )

            FilledTonalButton(
                onClick = { if (max == null || value < max) onValueChange(value + 1) },
                enabled = max == null || value < max,
                modifier = Modifier.size(72.dp),
            ) { Text("+", fontSize = 32.sp) }
        }
        if (maxHint != null) {
            Text(maxHint, fontSize = 16.sp, color = WmsColors.TextSecondary)
        }
    }
}
