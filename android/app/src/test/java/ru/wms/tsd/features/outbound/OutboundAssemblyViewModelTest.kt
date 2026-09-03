package ru.wms.tsd.features.outbound

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadLineOut
import ru.wms.tsd.core.api.generated.models.MarketplaceUnloadRequestDetailOut
import ru.wms.tsd.core.api.generated.models.PackagingTaskLineOut
import ru.wms.tsd.core.api.generated.models.PackagingTaskOut

/**
 * T-17. Юнит-тесты сборки отгрузки: двухшаговая загрузка упаковки (T-15b),
 * гейт расхождения при ship, запись упакованного количества.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OutboundAssemblyViewModelTest {

    private val requestId: UUID = UUID.fromString("3280dc0e-1871-41c9-a6c5-0f8c2a5f59ea")
    private val taskId = "a6e0c1b7-097f-4a41-8aa4-b96bcad02825"
    private val PACK_LINE_ID = "11111111-2222-3333-4444-555555555555"

    private lateinit var ops: OperationsApi
    private lateinit var api: ApiProvider

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        ops = mockk()
        api = mockk { every { operations() } returns ops }
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // ---------- фикстуры ----------

    private fun unloadLine(picked: Int, plan: Int) = MarketplaceUnloadLineOut(
        id = "line-1",
        productId = "prod-1",
        skuCode = "sku1",
        productName = "Товар",
        quantity = plan,
        pickedQty = picked,
    )

    private fun unloadDetail(picked: Int = 1, plan: Int = 1) = MarketplaceUnloadRequestDetailOut(
        id = requestId.toString(),
        warehouseId = "wh-1",
        warehouseName = "Склад",
        status = "collecting",
        createdAt = "2026-07-06T00:00:00Z",
        lines = listOf(unloadLine(picked, plan)),
        boxes = emptyList(),
    )

    private fun packagingLine(
        done: Int = 0,
        total: Int = 1,
        printed: Int = 0,
        honestSign: Boolean = true,
    ) = PackagingTaskLineOut(
        id = PACK_LINE_ID,
        productId = "prod-1",
        skuCode = "sku1",
        productName = "Товар",
        storageLocationId = "loc-1",
        storageLocationCode = "LOC-1",
        packagingInstructions = null,
        requiresHonestSign = honestSign,
        qtyTotal = total,
        qtySuggestedPacked = 0,
        qtyConfirmedPacked = 0,
        qtyNeedPack = total,
        qtyPackedInTask = done,
        qtyDone = done,
        qtyMarkingPrinted = printed,
        isComplete = done >= total,
    )

    private fun packagingTask(lines: List<PackagingTaskLineOut>, status: String = "draft") = PackagingTaskOut(
        id = taskId,
        warehouseId = "wh-1",
        status = status,
        marketplaceUnloadRequestId = requestId.toString(),
        inboundIntakeRequestId = null,
        isComplete = lines.isNotEmpty() && lines.all { it.isComplete },
        lines = lines,
    )

    private fun <T> err(code: Int, detail: String): Response<T> = Response.error(
        code,
        """{"detail":"$detail"}""".toResponseBody("application/json".toMediaType()),
    )

    private fun stubUnload(detail: MarketplaceUnloadRequestDetailOut) {
        coEvery {
            ops.getMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdGet(requestId)
        } returns Response.success(detail)
    }

    private fun stubPackaging404() {
        coEvery {
            ops.getPackagingTaskForUnloadOperationsPackagingTasksByUnloadUnloadIdGet(requestId)
        } returns err(404, "not_found")
    }

    private fun vm() = OutboundAssemblyViewModel(requestId, api)

    // ---------- тесты ----------

    @Test
    fun `load подтягивает заявку, отсутствие задачи упаковки (404) не ошибка`() = runTest {
        stubUnload(unloadDetail())
        stubPackaging404()

        val vm = vm()

        val st = vm.state.value
        assertFalse(st.loading)
        assertNull(st.loadError)
        assertEquals(requestId.toString(), st.request?.id)
        assertNull(st.packaging)
    }

    @Test
    fun `упаковка грузится двухшагово - строки берутся из GET по id, а не из by-unload`() = runTest {
        stubUnload(unloadDetail())
        // by-unload отдаёт задачу БЕЗ строк (сервер не синкает в этом эндпоинте)
        coEvery {
            ops.getPackagingTaskForUnloadOperationsPackagingTasksByUnloadUnloadIdGet(requestId)
        } returns Response.success(packagingTask(emptyList()))
        // GET по id синкает пик-аллокации и возвращает строку
        coEvery {
            ops.getPackagingTaskOperationsPackagingTasksTaskIdGet(UUID.fromString(taskId))
        } returns Response.success(packagingTask(listOf(packagingLine())))

        val vm = vm()

        assertEquals(1, vm.state.value.packaging?.lines?.size)
    }

    @Test
    fun `ship с расхождением план-факт - сервер отклоняет, открывается подтверждение расхождения`() = runTest {
        stubUnload(unloadDetail(picked = 1, plan = 2)) // недосбор
        stubPackaging404()
        coEvery {
            ops.shipMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdShipPost(requestId, any())
        } returns err(422, "distribution_incomplete")

        val vm = vm()
        var done = false
        vm.confirmShip(onDone = { done = true })

        assertFalse(done)
        assertEquals("ship_discrepancy", vm.state.value.confirm)
        assertFalse(vm.state.value.shipping)
    }

    @Test
    fun `ship после подтверждения расхождения уходит с acknowledgeDiscrepancy и завершает экран`() = runTest {
        stubUnload(unloadDetail(picked = 1, plan = 2))
        stubPackaging404()
        coEvery {
            ops.shipMarketplaceUnloadOperationsMarketplaceUnloadRequestsRequestIdShipPost(
                requestId,
                match { it?.acknowledgeDiscrepancy == true },
            )
        } returns Response.success(unloadDetail(picked = 1, plan = 2))

        val vm = vm()
        var done = false
        vm.confirmShip(onDone = { done = true }, acknowledgeDiscrepancy = true)

        assertTrue(done)
    }

    @Test
    fun `submitPack записывает количество и обновляет задачу упаковки`() = runTest {
        stubUnload(unloadDetail())
        coEvery {
            ops.getPackagingTaskForUnloadOperationsPackagingTasksByUnloadUnloadIdGet(requestId)
        } returns Response.success(packagingTask(listOf(packagingLine(done = 0))))
        coEvery {
            ops.getPackagingTaskOperationsPackagingTasksTaskIdGet(UUID.fromString(taskId))
        } returns Response.success(packagingTask(listOf(packagingLine(done = 0))))

        val packed = packagingTask(listOf(packagingLine(done = 1, printed = 1)))
        coEvery {
            ops.recordPackProgressOperationsPackagingTasksTaskIdLinesLineIdPackPost(
                UUID.fromString(taskId), UUID.fromString(PACK_LINE_ID), match { it.quantity == 1 },
            )
        } returns Response.success(packed)

        val vm = vm()
        vm.openPackLine(PACK_LINE_ID)
        vm.submitPack(1)

        coVerify(exactly = 1) {
            ops.recordPackProgressOperationsPackagingTasksTaskIdLinesLineIdPackPost(any(), any(), any())
        }
        assertEquals(1, vm.state.value.packaging?.lines?.firstOrNull()?.qtyDone)
        // строка выполнена — шторка закрывается
        assertNull(vm.state.value.packLineId)
    }

    @Test
    fun `markingIncomplete повторяет серверный гейт ЧЗ`() {
        // ЧЗ, упаковано 1, напечатано 0 — блокер
        assertTrue(markingIncomplete(packagingLine(done = 1, printed = 0)))
        // напечатано достаточно
        assertFalse(markingIncomplete(packagingLine(done = 1, printed = 1)))
        // ничего не упаковано — печать ещё не требуется
        assertFalse(markingIncomplete(packagingLine(done = 0, printed = 0)))
        // товар без ЧЗ
        assertFalse(markingIncomplete(packagingLine(done = 1, printed = 0, honestSign = false)))
    }
}
