package ru.wms.tsd.features.fbs

import android.util.Base64
import io.mockk.*
import java.io.IOException
import java.time.Instant
import java.util.TimeZone
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.MediaType.Companion.toMediaType
import org.junit.*
import org.junit.Assert.*
import retrofit2.Response
import ru.wms.tsd.core.api.ApiProvider
import ru.wms.tsd.core.api.fbs.*

@OptIn(ExperimentalCoroutinesApi::class)
class FbsViewModelTest {
    private lateinit var service: FbsApi
    private lateinit var provider: ApiProvider
    private fun order(id: String, created: String, picked: Boolean = false) = FbsOrder(
        id = id, wbOrderId = id.toLong(), status = "assembling", createdAt = created,
        product = FbsProduct(id = "product", name = "Товар", barcode = "4600000000001"),
        sticker = FbsSticker(status = "ready"), pick = FbsPickState(if (picked) "picked" else "pending"),
        pack = FbsPackState("pending"), deadlineAt = "2026-09-10T10:00:00Z",
    )
    private fun workspace(orders: List<FbsOrder>) = FbsWorkspace(
        supply = FbsWorkspaceSupply("supply", name = "Поставка", status = "assembling", seller = FbsNamedRef(), wbWarehouse = FbsNamedRef(), wmsWarehouse = FbsNamedRef(), nearestDeadlineAt = "2026-09-10T10:00:00Z"),
        stage = "picking", progress = FbsProgress(orders.count { it.pick.status == "picked" }, 0, 0, 0, orders.size), orders = orders, serverNow = "2026-09-08T10:00:00Z",
    )
    @Before fun setup() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        service = mockk()
        coEvery { service.pickOptions(any()) } returns Response.success(listOf(FbsPickOptionProduct("product", listOf(FbsPickOptionLocation("cell", "CELL", 10)))))
        provider = mockk {
            every { fbs() } returns service
            every { pendingFbsDelivery(any()) } returns null
            every { saveFbsDelivery(any(), any()) } just Runs
        }
    }
    @After fun teardown() { Dispatchers.resetMain() }

    @Test fun `oldest matching SKU uses instants and skips picked orders`() {
        val oldest = order("1", "2026-09-08T12:00:00+03:00")
        val newer = order("2", "2026-09-08T10:00:00Z").copy(deadlineAt = "2026-09-08T10:01:00Z")
        assertEquals(oldest, oldestMatchingOrder(listOf(newer, oldest), "4600000000001"))
        assertEquals(newer, oldestMatchingOrder(listOf(oldest.copy(pick = FbsPickState("picked")), newer), "4600000000001"))
        assertNull(oldestMatchingOrder(listOf(oldest), "unknown"))
    }
    @Test fun `oldest matching order respects offsets and fractions before WB id`() {
        val oldest = order("99", "2026-09-09T12:00:00.123456+03:00")
        val laterFraction = order("2", "2026-09-09T09:00:00.123457+00:00")
        val later = order("1", "2026-09-09T10:00:00+00:00")
        assertEquals(oldest, oldestMatchingOrder(listOf(later, laterFraction, oldest), "4600000000001"))
        assertEquals(laterFraction, oldestMatchingOrder(listOf(later, oldest.copy(pick = FbsPickState("picked")), laterFraction), "4600000000001"))
    }
    @Test fun `display time accepts API offsets fractions and UTC in local timezone`() {
        val originalZone = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("GMT+03:00"))
            listOf("2026-09-09T10:43:24+00:00", "2026-09-09T10:43:24Z", "2026-09-09T13:43:24+03:00", "2026-09-09T10:43:24.123456+00:00").forEach {
                assertEquals(it, "09.09.2026 13:43", displayTime(it))
            }
            assertEquals("invalid", displayTime("invalid"))
        } finally {
            TimeZone.setDefault(originalZone)
        }
    }
    @Test fun `sortedOrders lists earliest createdAt first with wb order tiebreaker (WMS-401)`() {
        val a = order("10", "2026-09-08T09:00:00+00:00")
        val b = order("20", "2026-09-08T08:00:00+03:00") // +03 = 05:00 UTC — самый ранний instant
        val c = order("5", "2026-09-08T09:00:00Z") // тот же instant, что и a → тайбрейк по wbOrderId (5 < 10)
        val bad = order("40", "not-a-date")
        val result = sortedOrders(listOf(a, bad, c, b))
        assertEquals(listOf(b, c, a, bad), result)
    }
    @Test fun `sortedOrders on empty and single-element inputs`() {
        assertTrue(sortedOrders(emptyList()).isEmpty())
        val only = order("1", "2026-09-08T09:00:00Z")
        assertEquals(listOf(only), sortedOrders(listOf(only)))
    }
    @Test fun `deadline offsets preserve the exclusive six hour boundary`() {
        val now = Instant.parse("2026-09-09T10:00:00Z")
        assertTrue(isDeadlineNear("2026-09-09T18:59:59.999999+03:00", now))
        assertTrue(isDeadlineNear("2026-09-09T15:59:59+00:00", now))
        assertFalse(isDeadlineNear("2026-09-09T19:00:00+03:00", now))
        assertFalse(isDeadlineNear("2026-09-09T20:00:00+03:00", now))
        assertFalse(isDeadlineNear("invalid", now))
    }
    @Test fun `scan retry keeps same order source and request identity after lost response`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"), order("2", "2026-09-08T10:00:00Z")))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.scan("supply", match { it.barcode == "BOX" }, any()) } returns Response.success(FbsScanResult("container", locationId = "cell", containerKind = "box", containerId = "box", containerCode = "BOX"))
        val bodies = mutableListOf<FbsScanBody>(); val keys = mutableListOf<String>()
        var attempt = 0
        coEvery { service.scan("supply", match { it.barcode == "4600000000001" }, any()) } coAnswers {
            bodies += secondArg<FbsScanBody>(); keys += thirdArg<String>()
            if (attempt++ == 0) throw IOException("response lost")
            Response.success(FbsScanResult("product"))
        }
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.scan("pick", "BOX"); vm.scan("pick", "4600000000001")
        assertNotNull(vm.state.value.error)
        vm.retry()
        assertNull(vm.state.value.error)
        assertEquals(2, keys.size); assertEquals(keys[0], keys[1]); assertEquals(bodies[0], bodies[1])
        assertEquals("1", bodies[1].orderId); assertEquals("box", bodies[1].containerId); assertEquals("cell", bodies[1].locationId)
    }
    @Test fun `serial product scans use refreshed server progress and distinct identities`() = runTest {
        val first = order("1", "2026-09-08T09:00:00Z"); val second = order("2", "2026-09-08T10:00:00Z")
        coEvery { service.workspace("supply") } returnsMany listOf(Response.success(workspace(listOf(first, second))), Response.success(workspace(listOf(first.copy(pick = FbsPickState("picked")), second))), Response.success(workspace(listOf(first.copy(pick = FbsPickState("picked")), second.copy(pick = FbsPickState("picked"))))))
        val bodies = mutableListOf<FbsScanBody>(); val keys = mutableListOf<String>()
        coEvery { service.scan(any(), capture(bodies), capture(keys)) } returns Response.success(FbsScanResult("product"))
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); repeat(2) { vm.scan("pick", "4600000000001") }
        assertEquals(listOf("1", "2"), bodies.map { it.orderId }); assertEquals(2, keys.toSet().size)
        assertEquals(2, vm.state.value.workspace?.progress?.picked)
    }
    @Test fun `physical choices use server availability and the deepest container`() {
        val pallet = FbsPickContainer("pallet", "pallet", "P-1")
        val box = FbsPickContainer("box", "box", "B-1")
        val choices = availablePickSources(listOf(FbsPickOptionLocation("cell", "CELL", 99, listOf(
            FbsPickOptionSource(0, "Россыпь"), FbsPickOptionSource(2, "Короб", listOf(pallet, box)),
        ))))
        assertEquals(1, choices.size)
        assertEquals("box", choices.single().source.containerId)
        assertEquals(2, choices.single().available)
        assertNull(availablePickSources(listOf(FbsPickOptionLocation("cell", "CELL", 1))).single().source.containerId)
    }
    @Test fun `cancel chooser preserves queued scan oldest order and explicit cell stays loose`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z")))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.pickOptions("supply") } returns Response.success(listOf(FbsPickOptionProduct("product", listOf(FbsPickOptionLocation("cell", "CELL", 10, listOf(
            FbsPickOptionSource(1, "Россыпь"), FbsPickOptionSource(9, "Короб", listOf(FbsPickContainer("box", "box", "BOX"))),
        ))))))
        val bodies = mutableListOf<FbsScanBody>()
        coEvery { service.scan("supply", capture(bodies), any()) } returns Response.success(FbsScanResult("product"))
        val vm = FbsViewModel(provider); vm.loadSupply("supply")
        vm.scan("pick", "4600000000001"); vm.scan("pick", "4600000000001")
        assertEquals(2, vm.state.value.pickChoices.size); assertTrue(bodies.isEmpty())
        vm.cancelPickSource()
        assertEquals(2, vm.state.value.pickChoices.size); assertTrue(bodies.isEmpty())
        vm.choosePickSource(vm.state.value.pickChoices.first())
        assertEquals("1", bodies.single().orderId); assertNull(bodies.single().containerId)
        // Explicit cell remains cell/NULL even if options later contain only a box.
        coEvery { service.pickOptions("supply") } returns Response.success(listOf(FbsPickOptionProduct("product", listOf(FbsPickOptionLocation("cell", "CELL", 9, listOf(
            FbsPickOptionSource(0, "Россыпь"), FbsPickOptionSource(9, "Короб", listOf(FbsPickContainer("box", "box", "BOX"))),
        ))))))
        coEvery { service.scan("supply", match { it.barcode == "CELL" }, any()) } returns Response.success(FbsScanResult("location", locationId = "cell", locationCode = "CELL"))
        vm.scan("pick", "CELL"); vm.scan("pick", "4600000000001")
        assertNull(bodies.last().containerId)
        coVerify(exactly = 2) { service.pickOptions("supply") }
    }
    @Test fun `switching supply cancels chooser and discards scans queued for previous supply`() = runTest {
        val old = workspace(listOf(order("1", "2026-09-08T09:00:00Z")))
        val fresh = workspace(listOf(order("3", "2026-09-08T09:00:00Z"))).let { it.copy(supply = it.supply.copy(id = "other")) }
        coEvery { service.workspace("supply") } returns Response.success(old)
        coEvery { service.workspace("other") } returns Response.success(fresh)
        coEvery { service.pickOptions("supply") } returns Response.success(listOf(FbsPickOptionProduct("product", listOf(
            FbsPickOptionLocation("cell1", "CELL1", 1), FbsPickOptionLocation("cell2", "CELL2", 1),
        ))))
        val bodies = mutableListOf<FbsScanBody>()
        coEvery { service.scan("other", capture(bodies), any()) } returns Response.success(FbsScanResult("product"))
        val vm = FbsViewModel(provider); vm.loadSupply("supply")
        vm.scan("pick", "4600000000001"); vm.scan("pick", "4600000000001")
        val staleChoice = vm.state.value.pickChoices.first()
        vm.loadSupply("other"); vm.choosePickSource(staleChoice)
        assertTrue(vm.state.value.pickChoices.isEmpty()); assertTrue(bodies.isEmpty())
        vm.scan("pick", "4600000000001")
        assertEquals("3", bodies.single().orderId)
        coVerify(exactly = 0) { service.scan("supply", any(), any()) }
    }
    @Test fun `full KIZ scan is preserved through WB commit`() = runTest {
        val code = "010460000000001221SERIAL\u001d91ABCD\u001d92SIGNATURE"
        coEvery { service.workspace("supply") } returns Response.success(workspace(listOf(order("1", "2026-09-08T09:00:00Z"))))
        coEvery { service.lookupKiz("supply", "QR") } returns Response.success(KizLookup("1", 1, true, false))
        coEvery { service.validateKiz(any()) } returns Response.success(KizValidation(true))
        val commits = mutableListOf<KizCommitBody>()
        coEvery { service.commitKiz(capture(commits)) } returns Response.success(listOf(KizCommitResult("1", "ok", "Сохранено", "pending")))
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.scan("pack", "QR"); vm.scan("pack", code + "\r\n")
        assertEquals(code, commits.single().pairs.single().value); assertNull(vm.state.value.error)
        assertEquals("КИЗ сохранён. WB ещё проверяет код.", vm.state.value.kizResult)
    }
    @Test fun `commit ok message never hides WB verification outcome`() = runTest {
        val code = "010460000000001221SERIAL\u001d91ABCD\u001d92SIGNATURE"
        coEvery { service.workspace("supply") } returns Response.success(workspace(listOf(order("1", "2026-09-08T09:00:00Z"))))
        coEvery { service.lookupKiz("supply", "QR") } returns Response.success(KizLookup("1", 1, true, false))
        coEvery { service.validateKiz(any()) } returns Response.success(KizValidation(true))
        val vm = FbsViewModel(provider); vm.loadSupply("supply")
        val cases = listOf(
            "accepted" to "КИЗ сохранён. WB принял код.",
            "allowed_without_check" to "КИЗ сохранён. WB разрешил код без проверки.",
            "pending" to "КИЗ сохранён. WB ещё проверяет код.",
            "sending" to "КИЗ сохранён. Передача в WB ещё не подтверждена.",
            "assigned" to "КИЗ сохранён. Передача в WB ещё не подтверждена.",
            "rejected" to "КИЗ сохранён. WB отклонил код.",
            "replacement_required" to "КИЗ сохранён. WB требует заменить код.",
            null to "КИЗ сохранён. Результат проверки WB неизвестен.",
            "unknown" to "КИЗ сохранён. Результат проверки WB неизвестен.",
            "future_status" to "КИЗ сохранён. Результат проверки WB неизвестен.",
        )
        for ((status, expected) in cases) {
            coEvery { service.commitKiz(any()) } returns Response.success(listOf(KizCommitResult("1", "ok", "ok", status)))
            vm.scan("pack", "QR"); vm.scan("pack", code)
            assertNull(vm.state.value.error)
            assertNull(vm.state.value.pendingKiz)
            assertEquals(expected, vm.state.value.kizResult)
        }
        coVerify(exactly = cases.size) { service.commitKiz(any()) }
    }
    @Test fun `print tape order error blocks all preview pages and is retried freshly`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"), order("2", "2026-09-08T10:00:00Z")))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        val partial = FbsPrintTape(orders = listOf(TapeOrder("1", 1, codes = listOf("CODE"))), orderErrors = listOf(FbsPrintOrderError("2", 2, "operator_kiz_print_forbidden", "operator_kiz_print_forbidden")))
        val complete = FbsPrintTape(orders = listOf(TapeOrder("1", 1, codes = listOf("CODE1")), TapeOrder("2", 2, codes = listOf("CODE2"))))
        coEvery { service.printTape("supply", any()) } returnsMany listOf(Response.success(partial), Response.success(complete))
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.printOrders("", listOf("1", "2"), 1, 1, false)
        assertEquals("WB 2: Печать введённого оператором кода ЧЗ запрещена.", vm.state.value.error)
        assertNull(vm.state.value.printDocument)
        coVerify(exactly = 0) { service.asset(any()); service.printAssets(any(), any()) }
        vm.retry()
        assertNull(vm.state.value.error)
        assertNotNull(vm.state.value.printDocument)
        coVerify(exactly = 2) { service.printTape("supply", any()) }
    }
    @Test fun `missing requested tape order cannot fall back to QR only success`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"), order("2", "2026-09-08T10:00:00Z")))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.printTape("supply", any()) } returns Response.success(FbsPrintTape(orders = listOf(TapeOrder("1", 1, codes = listOf("CODE")))))
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.printOrders("", listOf("1", "2"), 1, 1, true)
        assertEquals("Не получены данные для печати ЧЗ: WB 2", vm.state.value.error)
        assertNull(vm.state.value.printDocument)
        coVerify(exactly = 0) { service.asset(any()); service.printAssets(any(), any()) }
    }
    @Test fun `QR only printing retains the asset path without requesting KIZ tape`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z")))
        val asset = FbsPrintAsset("00000000-0000-0000-0000-000000000001", "order_sticker", "ready", previewUrl = "/api/operations/fbs-print-assets/00000000-0000-0000-0000-000000000001/content")
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.printAssets("supply", PrintBatchBody("order_sticker", listOf("1"))) } returns Response.success(FbsPrintBatch(listOf(asset)))
        val image = java.util.Base64.getDecoder().decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jL1sAAAAASUVORK5CYII=")
        coEvery { service.asset(any()) } returns Response.success(image.toResponseBody("image/png".toMediaType()))
        mockkStatic(Base64::class)
        try {
            every { Base64.encodeToString(any<ByteArray>(), Base64.NO_WRAP) } answers { java.util.Base64.getEncoder().encodeToString(firstArg()) }
            val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.printOrders("", listOf("1"), 0, 0, true)
            assertNull(vm.state.value.error)
            assertNotNull(vm.state.value.printDocument)
            coVerify(exactly = 0) { service.printTape(any(), any()) }
            coVerify(exactly = 1) { service.printAssets("supply", PrintBatchBody("order_sticker", listOf("1"))) }
        } finally { unmockkStatic(Base64::class) }
    }
    @Test fun `box technical QR resolves its exact order without marking gates`() = runTest {
        val box = FbsBox("box", 1, "BOX")
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"), order("2", "2026-09-08T10:00:00Z"))).copy(boxes = listOf(box))
        val updated = initial.copy(boxes = listOf(box.copy(assignedOrderIds = listOf("2"))))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.lookupKiz("supply", "*DU7lOQOH") } returns Response.success(KizLookup("2", 2, canBind = false, needsConfirmation = true))
        coEvery { service.assignOrders("supply", "box", AssignOrdersBody(listOf("2"))) } returns Response.success(updated)
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.scan("boxes", "BOX"); vm.scan("boxes", "*DU7lOQOH")
        assertNull(vm.state.value.error)
        assertEquals(listOf("2"), vm.state.value.workspace?.boxes?.single()?.assignedOrderIds)
        coVerify(exactly = 1) { service.lookupKiz("supply", "*DU7lOQOH") }
        coVerify(exactly = 1) { service.assignOrders("supply", "box", AssignOrdersBody(listOf("2"))) }
        coVerify(exactly = 0) { service.validateKiz(any()); service.commitKiz(any()) }
    }
    @Test fun `box local printed code does not invoke marking lookup`() = runTest {
        val box = FbsBox("box", 1, "BOX")
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z").copy(sticker = FbsSticker("57156822 35", "ready")))).copy(boxes = listOf(box))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.assignOrders("supply", "box", AssignOrdersBody(listOf("1"))) } returns Response.success(initial)
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.scan("boxes", "BOX"); vm.scan("boxes", "57156822 35")
        assertNull(vm.state.value.error)
        coVerify(exactly = 0) { service.lookupKiz(any(), any()) }
        coVerify(exactly = 1) { service.assignOrders("supply", "box", AssignOrdersBody(listOf("1"))) }
    }
    @Test fun `box QR cannot assign an absent or already assigned lookup order`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"))).copy(boxes = listOf(FbsBox("box", 1, "BOX", assignedOrderIds = listOf("1"))))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.lookupKiz("supply", "QR") } returnsMany listOf(Response.success(KizLookup("outside", 9, true, false)), Response.success(KizLookup("1", 1, true, false)))
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.selectBox("box")
        repeat(2) {
            vm.scan("boxes", "QR")
            assertNotNull(vm.state.value.error)
            vm.dismissError()
        }
        coVerify(exactly = 2) { service.lookupKiz("supply", "QR") }
        coVerify(exactly = 0) { service.assignOrders(any(), any(), any()) }
    }
    @Test fun `box lookup frozen response never assigns an order`() = runTest {
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"))).copy(boxes = listOf(FbsBox("box", 1, "BOX")))
        coEvery { service.workspace("supply") } returns Response.success(initial)
        coEvery { service.lookupKiz("supply", "QR") } returns Response.error(409, "{\"detail\":{\"code\":\"order_frozen\"}}".toResponseBody())
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.selectBox("box"); vm.scan("boxes", "QR")
        assertNotNull(vm.state.value.error)
        coVerify(exactly = 0) { service.assignOrders(any(), any(), any()) }
    }
    @Test fun `box quantity retry rereads successful deletes after lost response`() = runTest {
        val box = FbsBox("box", 1, "BOX", assignedOrderIds = listOf("1", "2"))
        val initial = workspace(listOf(order("1", "2026-09-08T09:00:00Z"), order("2", "2026-09-08T10:00:00Z"))).copy(boxes = listOf(box))
        val empty = initial.copy(boxes = listOf(box.copy(assignedOrderIds = emptyList())))
        coEvery { service.workspace("supply") } returnsMany listOf(Response.success(initial), Response.success(initial), Response.success(empty))
        coEvery { service.removeBoxOrder("supply", "box", "1") } returns Response.success(initial.copy(boxes = listOf(box.copy(assignedOrderIds = listOf("2")))))
        coEvery { service.removeBoxOrder("supply", "box", "2") } throws IOException("response lost after deletion")
        val vm = FbsViewModel(provider); vm.loadSupply("supply"); vm.setBoxQuantity(box, "product", 0)
        assertNotNull(vm.state.value.error)
        vm.retry()
        assertNull(vm.state.value.error)
        assertEquals(emptyList<String>(), vm.state.value.workspace?.boxes?.single()?.assignedOrderIds)
        coVerify(exactly = 1) { service.removeBoxOrder("supply", "box", "1") }
        coVerify(exactly = 1) { service.removeBoxOrder("supply", "box", "2") }
    }
    @Test fun `deadline and label escaping preserve operator data without script execution`() {
        assertTrue(isDeadlineNear("2026-09-08T15:00:00Z", Instant.parse("2026-09-08T10:00:00Z")))
        assertFalse(isDeadlineNear("2026-09-09T15:00:00Z", Instant.parse("2026-09-08T10:00:00Z")))
        val html = labelPage("<img onerror=x>", "</script>\u001d", true)
        assertTrue(html.contains("&lt;img onerror=x&gt;")); assertTrue(html.contains("\\u003c/script>")); assertTrue(html.contains("\\u001d"))
        assertTrue(isKizScan("]d2010460000000001221SERIAL")); assertFalse(isKizScan("4600000000001"))
    }
}
