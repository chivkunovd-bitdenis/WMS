package ru.wms.tsd.features.fbs

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.fbs.FbsApi
import ru.wms.tsd.core.api.fbs.FbsBox
import ru.wms.tsd.core.api.fbs.FbsDeliveryCheck
import ru.wms.tsd.core.api.fbs.FbsDeliveryPreflight
import ru.wms.tsd.core.api.fbs.FbsNamedRef
import ru.wms.tsd.core.api.fbs.FbsOrder
import ru.wms.tsd.core.api.fbs.FbsPackState
import ru.wms.tsd.core.api.fbs.FbsPickLocation
import ru.wms.tsd.core.api.fbs.FbsPickState
import ru.wms.tsd.core.api.fbs.FbsPosition
import ru.wms.tsd.core.api.fbs.FbsProduct
import ru.wms.tsd.core.api.fbs.FbsProgress
import ru.wms.tsd.core.api.fbs.FbsSticker
import ru.wms.tsd.core.api.fbs.FbsSupplySummary
import ru.wms.tsd.core.api.fbs.FbsWorklistResponse
import ru.wms.tsd.core.api.fbs.FbsWorkspace
import ru.wms.tsd.core.api.fbs.FbsWorkspaceSupply
import ru.wms.tsd.core.api.fbs.FulfilledOrder
import ru.wms.tsd.core.api.fbs.PackProgressResponse
import ru.wms.tsd.core.api.fbs.PackagingLine
import ru.wms.tsd.core.api.fbs.PackagingTask

@OptIn(ExperimentalCoroutinesApi::class)
class FbsViewModelsTest {
    private lateinit var fbs: FbsApi
    private lateinit var api: ApiProvider

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        fbs = mockk()
        api = mockk { every { fbs() } returns fbs }
    }

    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun listLoadsWarehouseAndDeliveryQueues() = runTest {
        val active = supplySummary("active", "assembling")
        val delivery = supplySummary("delivery", "in_delivery")
        coEvery { fbs.worklist("wb", "active", 100) } returns Response.success(FbsWorklistResponse(listOf(active), NOW))
        coEvery { fbs.worklist("wb", "delivery", 100) } returns Response.success(FbsWorklistResponse(listOf(delivery), NOW))

        val vm = FbsSupplyListViewModel(api)
        advanceUntilIdle()

        assertEquals(listOf(active), vm.state.value.active)
        assertEquals(listOf(delivery), vm.state.value.delivery)
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun pickingRequiresLocationThenSendsProductWithIdempotency() = runTest {
        val before = workspace(picked = 0)
        val after = workspace(picked = 1)
        val location = FbsPickLocation("loc-1", "A-01", "Основной", emptyList())
        coEvery { fbs.workspace(SUPPLY_ID) } returns Response.success(before)
        coEvery { fbs.scanLocation(SUPPLY_ID, any()) } returns Response.success(location)
        coEvery { fbs.scanProduct(SUPPLY_ID, any()) } returns Response.success(after)

        val vm = FbsPickingViewModel(SUPPLY_ID, api)
        vm.onScan("A-01")
        vm.onScan("460000000001")
        advanceUntilIdle()

        assertEquals(1, vm.state.value.workspace?.progress?.picked)
        assertEquals("A-01", vm.state.value.location?.code)
        coVerify(exactly = 1) {
            fbs.scanProduct(SUPPLY_ID, match {
                it.locationId == "loc-1" && it.productBarcode == "460000000001" && it.idempotencyKey.isNotBlank()
            })
        }
    }

    @Test
    fun packingOrderStickerRecordsExactOrderAndRefreshesWorkspace() = runTest {
        val before = workspace(packed = 0)
        val after = workspace(packed = 1)
        val line = PackagingLine("line-1", "product-1", "SKU-1", "Товар", null, 1, 0, 1, false)
        val task = PackagingTask("task-1", "active", false, listOf(line))
        val packedTask = task.copy(isComplete = true, lines = listOf(line.copy(qtyDone = 1, qtyNeedPack = 0, isComplete = true)))
        coEvery { fbs.workspace(SUPPLY_ID) } returnsMany listOf(Response.success(before), Response.success(after))
        coEvery { fbs.packagingTask("task-1") } returns Response.success(task)
        coEvery { fbs.pack("task-1", "line-1", any()) } returns
            Response.success(PackProgressResponse(packedTask, FulfilledOrder("order-1", 123456789)))

        val vm = FbsPackingViewModel(SUPPLY_ID, api)
        vm.onScan("STICKER-1")
        advanceUntilIdle()

        assertTrue(vm.state.value.task?.isComplete == true)
        assertEquals(1, vm.state.value.workspace?.progress?.packed)
        coVerify { fbs.pack("task-1", "line-1", match { it.orderId == "order-1" && it.idempotencyKey.isNotBlank() }) }
    }

    @Test
    fun handoffSelectsBoxAssignsOrderAndUsesPreflightVersion() = runTest {
        val before = workspace(boxes = listOf(FbsBox("box-1", 1, "BOX-1")))
        val assigned = before.copy(boxes = listOf(FbsBox("box-1", 1, "BOX-1", listOf("order-1"))))
        val preflight = FbsDeliveryPreflight(
            true,
            "version-7",
            NOW,
            listOf(FbsDeliveryCheck("physical_boxes_required", "Короба есть", true, "info")),
        )
        val delivered = assigned.copy(supply = assigned.supply.copy(status = "in_delivery"))
        coEvery { fbs.workspace(SUPPLY_ID) } returns Response.success(before)
        coEvery { fbs.assignOrders(SUPPLY_ID, "box-1", any()) } returns Response.success(assigned)
        coEvery { fbs.deliveryPreflight(SUPPLY_ID) } returns Response.success(preflight)
        coEvery { fbs.deliver(SUPPLY_ID, any()) } returns Response.success(delivered)

        val vm = FbsHandoffViewModel(SUPPLY_ID, api)
        vm.onScan("BOX-1")
        vm.onScan("STICKER-1")
        vm.checkDelivery()
        vm.requestDeliver()
        vm.deliver()
        advanceUntilIdle()
        vm.onScan("STICKER-1")
        advanceUntilIdle()

        assertEquals("in_delivery", vm.state.value.workspace?.supply?.status)
        coVerify(exactly = 1) { fbs.assignOrders(SUPPLY_ID, "box-1", match { it.orderIds == listOf("order-1") }) }
        coVerify { fbs.deliver(SUPPLY_ID, match { it.confirmedPreflightVersion == "version-7" }) }
    }

    @Test
    fun assigningOrderInvalidatesPreviousDeliveryCheck() = runTest {
        val oldPreflight = FbsDeliveryPreflight(true, "old-version", NOW, emptyList())
        val before = workspace(boxes = listOf(FbsBox("box-1", 1, "BOX-1"))).copy(
            deliveryPreflight = oldPreflight,
        )
        val assigned = before.copy(boxes = listOf(FbsBox("box-1", 1, "BOX-1", listOf("order-1"))))
        coEvery { fbs.workspace(SUPPLY_ID) } returns Response.success(before)
        coEvery { fbs.assignOrders(SUPPLY_ID, "box-1", any()) } returns Response.success(assigned)

        val vm = FbsHandoffViewModel(SUPPLY_ID, api)
        assertNotNull(vm.state.value.preflight)
        vm.onScan("BOX-1")
        vm.onScan("STICKER-1")
        advanceUntilIdle()

        assertEquals(null, vm.state.value.preflight)
    }

    private fun supplySummary(id: String, status: String) = FbsSupplySummary(
        id, "WB-$id", "Поставка $id", status, FbsNamedRef("Селлер"),
        FbsNamedRef("Коледино"), FbsNamedRef("Основной"), 1, 1, 0,
    )

    private fun workspace(
        picked: Int = 0,
        packed: Int = 0,
        boxes: List<FbsBox> = emptyList(),
    ): FbsWorkspace = FbsWorkspace(
        supply = FbsWorkspaceSupply(
            SUPPLY_ID, "WB-1", "Поставка 1", "assembling", FbsNamedRef("Селлер"),
            FbsNamedRef("Коледино"), FbsNamedRef("Основной"), nearestDeadlineAt = NOW,
            packagingTaskId = "task-1",
        ),
        stage = "picking",
        progress = FbsProgress(picked, packed, 1, 1, 1),
        orders = listOf(
            FbsOrder(
                "order-1", "EXT-1", 123456789, "confirm", FbsProduct("product-1", "Товар", "ART-1", "460000000001", "SKU-1"),
                listOf(FbsPosition("product-1", "Товар", "ART-1", "SKU-1", 1, picked)),
                FbsSticker("STICKER-1", "ready"), FbsPickState(if (picked > 0) "picked" else "pending"),
                FbsPackState(if (packed > 0) "packed" else "pending"), NOW,
            ),
        ),
        boxes = boxes,
        serverNow = NOW,
    )

    companion object {
        private const val SUPPLY_ID = "supply-1"
        private const val NOW = "2026-09-04T00:00:00Z"
    }
}
