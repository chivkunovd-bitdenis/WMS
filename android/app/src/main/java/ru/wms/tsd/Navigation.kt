package ru.wms.tsd

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import ru.wms.tsd.core.auth.AuthSession
import ru.wms.tsd.features.home.HomeScreen
import ru.wms.tsd.features.home.HomeSection
import ru.wms.tsd.features.fbs.FbsHandoffScreen
import ru.wms.tsd.features.fbs.FbsPackingScreen
import ru.wms.tsd.features.fbs.FbsPickingScreen
import ru.wms.tsd.features.fbs.FbsSupplyListScreen
import ru.wms.tsd.features.fbs.FbsWorkspaceScreen
import ru.wms.tsd.features.inbound.InboundBoxesScreen
import ru.wms.tsd.features.inbound.InboundListScreen
import ru.wms.tsd.features.inbound.InboundReceivingScreen
import ru.wms.tsd.features.outbound.OutboundAssemblyScreen
import ru.wms.tsd.features.outbound.OutboundListScreen
import ru.wms.tsd.features.sorting.SortingListScreen
import ru.wms.tsd.features.sorting.SortingScreen
import ru.wms.tsd.ui.theme.WmsColors

/**
 * Главный навигационный граф приложения.
 * Маршруты: home, inbound, sorting, outbound.
 * Разделы: inbound (B1→B2→B3), sorting (C1→C2), outbound (D1→сборка D2+D3).
 */
@Composable
fun AppNavHost(
    session: AuthSession,
    navController: NavHostController = rememberNavController(),
    onLogout: () -> Unit,
) {
    NavHost(
        navController = navController,
        startDestination = "home",
    ) {
        composable("home") {
            HomeScreen(
                session = session,
                onSectionClick = { section ->
                    navController.navigate(section.route)
                },
                onLogout = onLogout,
            )
        }

        composable("inbound") {
            InboundListScreen(
                onBack = { navController.popBackStack() },
                onOpenRequest = { id, status ->
                    if (status == "submitted") {
                        navController.navigate("inbound/$id/boxes")
                    } else {
                        navController.navigate("inbound/$id/receiving")
                    }
                },
            )
        }

        composable("inbound/{requestId}/boxes") { backStackEntry ->
            val requestId = backStackEntry.arguments?.getString("requestId") ?: return@composable
            InboundBoxesScreen(
                requestId = requestId,
                onBack = { navController.popBackStack() },
                onGoToReceiving = {
                    // Если пришли сюда С экрана приёмки (за коробом посреди работы) —
                    // возвращаемся к нему, а не плодим второй экран приёмки в стеке.
                    val cameFromReceiving = navController.previousBackStackEntry
                        ?.destination?.route?.startsWith("inbound/{requestId}/receiving") == true
                    if (cameFromReceiving) {
                        navController.popBackStack()
                    } else {
                        navController.navigate("inbound/$requestId/receiving") {
                            popUpTo("inbound/$requestId/boxes") { inclusive = true }
                        }
                    }
                },
                // Тап по коробу — «наполнять этот короб»: открыть приёмку с ним активным.
                onSelectBox = { boxId ->
                    val cameFromReceiving = navController.previousBackStackEntry
                        ?.destination?.route?.startsWith("inbound/{requestId}/receiving") == true
                    val route = "inbound/$requestId/receiving?boxId=$boxId"
                    navController.navigate(route) {
                        // заменяем текущий экран приёмки (или убираем короба, если пришли из списка)
                        if (cameFromReceiving) {
                            popUpTo("inbound/{requestId}/receiving") { inclusive = true }
                        } else {
                            popUpTo("inbound/$requestId/boxes") { inclusive = true }
                        }
                    }
                },
            )
        }

        composable(
            "inbound/{requestId}/receiving?boxId={boxId}",
            arguments = listOf(
                navArgument("boxId") { type = NavType.StringType; nullable = true; defaultValue = null },
            ),
        ) { backStackEntry ->
            val requestId = backStackEntry.arguments?.getString("requestId") ?: return@composable
            val boxId = backStackEntry.arguments?.getString("boxId")
            InboundReceivingScreen(
                requestId = requestId,
                onBack = { navController.popBackStack() },
                onOpenBoxes = { navController.navigate("inbound/$requestId/boxes") },
                initialBoxId = boxId,
            )
        }

        composable("sorting") {
            SortingListScreen(
                onBack = { navController.popBackStack() },
                onOpenRequest = { id ->
                    navController.navigate("sorting/$id")
                },
            )
        }

        composable("sorting/{requestId}") { backStackEntry ->
            val requestId = backStackEntry.arguments?.getString("requestId") ?: return@composable
            SortingScreen(
                requestId = requestId,
                onBack = { navController.popBackStack() },
            )
        }

        composable("outbound") {
            OutboundListScreen(
                onBack = { navController.popBackStack() },
                onOpenRequest = { id ->
                    navController.navigate("outbound/$id")
                },
            )
        }

        composable("outbound/{requestId}") { backStackEntry ->
            val requestId = backStackEntry.arguments?.getString("requestId") ?: return@composable
            OutboundAssemblyScreen(
                requestId = requestId,
                onBack = { navController.popBackStack() },
            )
        }

        composable("fbs") {
            FbsSupplyListScreen(
                onBack = { navController.popBackStack() },
                onOpenSupply = { navController.navigate("fbs/$it") },
            )
        }

        composable("fbs/{supplyId}") { backStackEntry ->
            val supplyId = backStackEntry.arguments?.getString("supplyId") ?: return@composable
            FbsWorkspaceScreen(
                supplyId = supplyId,
                onBack = { navController.popBackStack() },
                onPicking = { navController.navigate("fbs/$supplyId/picking") },
                onPacking = { navController.navigate("fbs/$supplyId/packing") },
                onHandoff = { navController.navigate("fbs/$supplyId/handoff") },
            )
        }

        composable("fbs/{supplyId}/picking") { backStackEntry ->
            val supplyId = backStackEntry.arguments?.getString("supplyId") ?: return@composable
            FbsPickingScreen(supplyId = supplyId, onBack = { navController.popBackStack() })
        }

        composable("fbs/{supplyId}/packing") { backStackEntry ->
            val supplyId = backStackEntry.arguments?.getString("supplyId") ?: return@composable
            FbsPackingScreen(supplyId = supplyId, onBack = { navController.popBackStack() })
        }

        composable("fbs/{supplyId}/handoff") { backStackEntry ->
            val supplyId = backStackEntry.arguments?.getString("supplyId") ?: return@composable
            FbsHandoffScreen(supplyId = supplyId, onBack = { navController.popBackStack() })
        }
    }
}

/**
 * Временная заглушка для экранов в разработке.
 */
@Composable
private fun PlaceholderScreen(
    title: String,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "Раздел в разработке",
            fontSize = 20.sp,
            color = WmsColors.TextPrimary,
            textAlign = TextAlign.Center,
        )
        Button(
            onClick = onBack,
            modifier = Modifier.padding(top = 24.dp),
        ) {
            Text("Назад")
        }
    }
}
