package ru.wms.tsd.ui.patterns

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

@Composable
fun ListSkeleton(rows: Int = 5) {
    val infiniteTransition = rememberInfiniteTransition(label = "ListSkeleton")
    val alpha = infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(700),
            repeatMode = RepeatMode.Reverse
        ),
        label = "SkeletonAlpha"
    )

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .graphicsLayer { this.alpha = alpha.value }
            .padding(horizontal = 16.dp, vertical = 16.dp)
    ) {
        repeat(rows) {
            Surface(
                shape = RoundedCornerShape(WmsDimens.CornerRadius),
                color = WmsColors.Surface,
                shadowElevation = 1.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp)
                ) {
                    // First placeholder line (title)
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.6f)
                            .height(20.dp)
                            .background(WmsColors.Background, RoundedCornerShape(4.dp))
                    )

                    // Space between lines
                    Box(modifier = Modifier.height(8.dp))

                    // Second placeholder line (subtitle)
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.9f)
                            .height(14.dp)
                            .background(WmsColors.Background, RoundedCornerShape(4.dp))
                    )
                }
            }
        }
    }
}
