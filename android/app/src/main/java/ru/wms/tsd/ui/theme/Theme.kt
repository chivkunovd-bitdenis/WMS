package ru.wms.tsd.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Токены из mobile/docs/02_UX_SPEC.md §1. Менять только через UX-спеку.
object WmsColors {
    val Primary = Color(0xFF1565C0)
    val Success = Color(0xFF2E7D32)
    val Error = Color(0xFFC62828)
    val Warning = Color(0xFFF57F17)
    val Surface = Color(0xFFFFFFFF)
    val Background = Color(0xFFF5F5F5)
    val TextPrimary = Color(0xFF1A1A1A)
    val TextSecondary = Color(0xFF5F6368)
}

object WmsDimens {
    val CornerRadius = 12.dp
    val TouchTargetMin = 56.dp
    val PrimaryButtonHeight = 64.dp
    val SpacingUnit = 8.dp
}

private val LightColorScheme = lightColorScheme(
    primary = WmsColors.Primary,
    error = WmsColors.Error,
    surface = WmsColors.Surface,
    background = WmsColors.Background,
    onSurface = WmsColors.TextPrimary,
    onBackground = WmsColors.TextPrimary,
    onSurfaceVariant = WmsColors.TextSecondary,
)

@Composable
fun WmsTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        content = content,
    )
}
