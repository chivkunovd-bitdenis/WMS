package ru.wms.tsd.features.sorting

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.generated.apis.OperationsApi
import ru.wms.tsd.core.api.generated.apis.WarehousesApi
import ru.wms.tsd.core.api.generated.models.InboundDistributionLineIn
import ru.wms.tsd.core.api.generated.models.InboundDistributionLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestOut
import ru.wms.tsd.core.api.generated.models.LocationOut

/**
 * T-17. Юнит-тесты сортировки. Главное — фикс гонки в confirmLoosePutaway:
 * PUT distribution-lines заменяет весь список, поэтому merge должен строиться
 * на СВЕЖЕМ серверном списке, иначе параллельное размещение молча затирается.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SortingViewModelTest {

    private val requestId: UUID = UUID.fromString("aaaaaaaa-0000-0000-0000-000000000001")
    private val warehouseId = "bbbbbbbb-0000-0000-0000-000000000002"
    private val prodA = "cccccccc-0000-0000-0000-00000000000a"
    private val prodB = "cccccccc-0000-0000-0000-00000000000b"
    private val prodC = "cccccccc-0000-0000-0000-00000000000c"
    private val locAId = "dddddddd-0000-0000-0000-00000000000a"
    private val locCId = "dddddddd-0000-0000-0000-00000000000c"
    private val locCBarcode = "LOC-C-BARCODE"

    private lateinit var ops: OperationsApi
    private lateinit var whs: WarehousesApi
    private lateinit var api: ApiProvider

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        ops = mockk()
        whs = mockk()
        api = mockk {
            every { operations() } returns ops
            every { warehouses() } returns whs
        }
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun intakeLine(productId: String, actual: Int, posted: Int) = InboundIntakeLineOut(
        id = "il-$productId",
        productId = productId,
        skuCode = "sku",
        productName = "Товар",
        expectedQty = actual,
        actualQty = actual,
        postedQty = posted,
        storageLocationId = null,
        storageLocationCode = null,
    )

    private fun request() = InboundIntakeRequestOut(
        id = requestId.toString(),
        warehouseId = warehouseId,
        status = "sorting",
        lines = listOf(intakeLine(prodC, actual = 10, posted = 0)),
        boxes = emptyList(),
    )

    private fun distLine(id: String, productId: String, locId: String, qty: Int) = InboundDistributionLineOut(
        id = id,
        productId = productId,
        storageLocationId = locId,
        storageLocationCode = "LOC",
        quantity = qty,
        createdAt = "2026-07-06T00:00:00Z",
    )

    private fun locC() = LocationOut(id = locCId, code = "LOC-C", warehouseId = warehouseId, barcode = locCBarcode)

    @Test
    fun `confirmLoosePutaway строит merge на свежем серверном списке, не затирая параллельное размещение`() = runTest {
        // Начальная загрузка: distLines = [A]
        val lineA = distLine("id-a", prodA, locAId, 5)
        coEvery { ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId) } returns
            Response.success(request())
        coEvery { ops.listDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesGet(requestId) } returns
            Response.success(listOf(lineA))
        coEvery {
            whs.listLocationsWarehousesWarehouseIdLocationsGet(UUID.fromString(warehouseId), excludeSortingZone = true)
        } returns Response.success(listOf(locC()))

        val vm = SortingViewModel(requestId, api)
        advanceUntilIdle()

        // Выбираем loose-товар C и сканируем ячейку C → pendingLocation
        vm.selectLooseProduct(prodC)
        vm.onScan(locCBarcode)
        runCurrent()
        assertEquals(locCId, vm.state.value.pendingLocation?.id)

        // К моменту подтверждения сервер уже содержит [A, B] (B добавил кто-то ещё)
        val lineB = distLine("id-b", prodB, locAId, 7)
        coEvery { ops.listDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesGet(requestId) } returns
            Response.success(listOf(lineA, lineB))

        val putSlot = slot<List<InboundDistributionLineIn>>()
        coEvery {
            ops.replaceDistributionLinesOperationsInboundIntakeRequestsRequestIdDistributionLinesPut(requestId, capture(putSlot))
        } returns Response.success(listOf(lineA, lineB))

        vm.confirmLoosePutaway(quantity = 3)
        advanceUntilIdle()

        val sent = putSlot.captured
        // Должны присутствовать A, B (свежие) И новая строка C=3 — B не потеряна
        assertTrue("A сохранён", sent.any { it.productId.toString() == prodA })
        assertTrue("B (параллельный) НЕ затёрт", sent.any { it.productId.toString() == prodB })
        val cLine = sent.firstOrNull { it.productId.toString() == prodC }
        assertEquals("C добавлен с qty=3", 3, cLine?.quantity)
        assertEquals("итого 3 строки", 3, sent.size)
    }
}
