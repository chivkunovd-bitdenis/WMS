package ru.wms.tsd.features.inbound

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
import ru.wms.tsd.core.api.generated.models.InboundIntakeBoxLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeBoxOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeLineOut
import ru.wms.tsd.core.api.generated.models.InboundIntakeRequestOut
import ru.wms.tsd.ui.patterns.ScanFlash

/**
 * T-17 часть 2. Юнит-тесты приёмки товара (InboundReceivingViewModel):
 * загрузка заявки, обработка сканов штрихкодов (короба, товара, loose-режим),
 * закрытие и завершение.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class InboundReceivingViewModelTest {

    private val requestId: UUID = UUID.fromString("a5e1d2b3-4f6c-4e7d-8a9b-2c1d3e4f5a6b")
    private val BOX_ID = "11111111-2222-3333-4444-555555555555"
    private val BOX_BARCODE = "BOX-001-INTERNAL"
    private val PRODUCT_ID = "prod-1"
    private val PRODUCT_BARCODE = "8901234567890"

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

    private fun boxLine(
        productId: String = PRODUCT_ID,
        skuCode: String = "SKU-001",
        productName: String = "Товар",
        quantity: Int = 10,
    ) = InboundIntakeBoxLineOut(
        id = "line-1",
        productId = productId,
        skuCode = skuCode,
        productName = productName,
        quantity = quantity,
        postedQty = 0,
        remainingQty = quantity,
    )

    private fun box(
        id: String = BOX_ID,
        boxNumber: Int = 1,
        internalBarcode: String = BOX_BARCODE,
        isOpen: Boolean = false,
        lines: List<InboundIntakeBoxLineOut> = listOf(boxLine()),
    ) = InboundIntakeBoxOut(
        id = id,
        boxNumber = boxNumber,
        internalBarcode = internalBarcode,
        labelPrintedAt = "2026-07-06T00:00:00Z",
        intakeOpenedAt = null,
        intakeClosedAt = null,
        isOpen = isOpen,
        remainingQty = if (lines.isEmpty()) 0 else lines.sumOf { it.quantity },
        lines = lines,
    )

    private fun line(
        productId: String = PRODUCT_ID,
        skuCode: String = "SKU-001",
        productName: String = "Товар",
        expectedQty: Int = 10,
        actualQty: Int? = 0,
    ) = InboundIntakeLineOut(
        id = "line-1",
        productId = productId,
        skuCode = skuCode,
        productName = productName,
        expectedQty = expectedQty,
        actualQty = actualQty,
        postedQty = 0,
        storageLocationId = "loc-1",
        storageLocationCode = "LOC-1",
        effectiveActualQty = null,
    )

    private fun intakeRequest(
        boxes: List<InboundIntakeBoxOut> = listOf(box()),
        lines: List<InboundIntakeLineOut> = listOf(line()),
    ) = InboundIntakeRequestOut(
        id = requestId.toString(),
        warehouseId = "wh-1",
        status = "receiving",
        lines = lines,
        documentNumber = "DOC-001",
        displayNumber = "DISP-001",
        plannedBoxCount = 2,
        actualBoxCount = 0,
        boxes = boxes,
    )

    private fun <T> err(code: Int, detail: String): Response<T> = Response.error(
        code,
        """{"detail":"$detail"}""".toResponseBody("application/json".toMediaType()),
    )

    private fun stubLoadSuccess(request: InboundIntakeRequestOut) {
        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returns Response.success(request)
    }

    private fun stubLoadError(code: Int = 500, detail: String = "internal_error") {
        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returns err(code, detail)
    }

    private fun vm() = InboundReceivingViewModel(requestId, api)

    // ---------- тесты ----------

    @Test
    fun `load подтягивает заявку - состояние без ошибки, данные на месте`() = runTest {
        val request = intakeRequest()
        stubLoadSuccess(request)

        val vm = vm()

        val st = vm.state.value
        assertFalse(st.loading)
        assertNull(st.loadError)
        assertEquals(requestId.toString(), st.request?.id)
        assertEquals(1, st.request?.boxes?.size)
        assertEquals("SKU-001", st.request?.boxes?.get(0)?.lines?.get(0)?.skuCode)
    }

    @Test
    fun `load сетевая ошибка - loadError заполнен сообщением`() = runTest {
        stubLoadError(500, "internal_server_error")

        val vm = vm()

        val st = vm.state.value
        assertFalse(st.loading)
        assertTrue(!st.loadError.isNullOrBlank())
        assertNull(st.request)
    }

    @Test
    fun `скан штрихкода короба - открывает короб, flash успеха, данные обновлены`() = runTest {
        val initialRequest = intakeRequest(
            boxes = listOf(box(isOpen = false, id = BOX_ID))
        )
        val openedRequest = intakeRequest(
            boxes = listOf(box(isOpen = true, id = BOX_ID))
        )

        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returnsMany listOf(
            Response.success(initialRequest),
            Response.success(openedRequest),
        )
        coEvery {
            ops.openInboundBoxByBarcodeOperationsInboundIntakeRequestsRequestIdBoxesOpenPost(
                requestId, any()
            )
        } returns Response.success(box(isOpen = true, id = BOX_ID))

        val vm = vm()
        // После init произойдёт первая загрузка
        vm.onScan(BOX_BARCODE)

        val st = vm.state.value
        assertEquals(BOX_ID, st.openBoxId)
        assertTrue(st.flash is ScanFlash.Success)
    }

    @Test
    fun `скан неизвестного штрихкода в открытый короб (422) - flash ошибки`() = runTest {
        val request = intakeRequest()
        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returnsMany listOf(
            Response.success(request),
            Response.success(request),
        )
        // Откроем короб
        coEvery {
            ops.openInboundBoxByBarcodeOperationsInboundIntakeRequestsRequestIdBoxesOpenPost(
                requestId, any()
            )
        } returns Response.success(box(isOpen = true, id = BOX_ID))
        // Скан неизвестного товара → 422
        coEvery {
            ops.scanProductIntoInboundBoxOperationsInboundIntakeRequestsRequestIdBoxesBoxIdScanPost(
                requestId, UUID.fromString(BOX_ID), any()
            )
        } returns err(422, "barcode_unknown")

        val vm = vm()
        vm.onScan(BOX_BARCODE)  // откроем короб
        vm.onScan("UNKNOWN-BARCODE-999")  // попытка скана неизвестного товара

        val st = vm.state.value
        assertTrue(st.flash is ScanFlash.Error)
    }

    @Test
    fun `confirmCloseBox закрывает открытый короб, флеш успеха, openBoxId очищается`() = runTest {
        val request = intakeRequest(
            boxes = listOf(box(isOpen = true, id = BOX_ID))
        )
        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returnsMany listOf(
            Response.success(request),
            Response.success(intakeRequest(boxes = listOf(box(isOpen = false, id = BOX_ID)))),
        )
        coEvery {
            ops.closeInboundBoxIntakeOperationsInboundIntakeRequestsRequestIdBoxesBoxIdClosePost(
                requestId, UUID.fromString(BOX_ID)
            )
        } returns Response.success(box(isOpen = false, id = BOX_ID))

        val vm = vm()
        // Откроем короб через скан
        coEvery {
            ops.openInboundBoxByBarcodeOperationsInboundIntakeRequestsRequestIdBoxesOpenPost(
                requestId, any()
            )
        } returns Response.success(box(isOpen = true, id = BOX_ID))
        vm.onScan(BOX_BARCODE)

        // Теперь закроем
        vm.requestCloseBox()
        vm.confirmCloseBox()

        val st = vm.state.value
        assertNull(st.openBoxId)
        assertTrue(st.flash is ScanFlash.Success)
    }

    @Test
    fun `setLooseMode включает режим без короба, очищает openBoxId`() = runTest {
        val request = intakeRequest()
        stubLoadSuccess(request)
        coEvery {
            ops.openInboundBoxByBarcodeOperationsInboundIntakeRequestsRequestIdBoxesOpenPost(
                requestId, any()
            )
        } returns Response.success(box(isOpen = true, id = BOX_ID))

        val vm = vm()
        vm.onScan(BOX_BARCODE)  // откроем короб
        assertEquals(BOX_ID, vm.state.value.openBoxId)

        vm.setLooseMode(enabled = true)

        val st = vm.state.value
        assertTrue(st.looseMode)
        assertNull(st.openBoxId)
    }

    @Test
    fun `confirmComplete завершает приёмку, вызывает onDone при успехе`() = runTest {
        val request = intakeRequest()
        coEvery {
            ops.getInboundRequestOperationsInboundIntakeRequestsRequestIdGet(requestId)
        } returns Response.success(request)
        coEvery {
            ops.completeInboundReceivingOperationsInboundIntakeRequestsRequestIdCompleteReceivingPost(requestId)
        } returns Response.success(request.copy(status = "completed"))

        val vm = vm()
        var onDoneCalled = false
        vm.requestComplete()
        assertEquals("complete", vm.state.value.confirm)

        vm.confirmComplete(onDone = { onDoneCalled = true })

        assertTrue(onDoneCalled)
        coVerify(exactly = 1) {
            ops.completeInboundReceivingOperationsInboundIntakeRequestsRequestIdCompleteReceivingPost(requestId)
        }
    }
}
