package com.pantryproof.prototype.contract.v1

import com.pantryproof.prototype.data.M3eReceiptPresentationAdapter
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.PresentedField
import com.pantryproof.prototype.data.ReceiptPresentationRequestCoordinator
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingDelivery
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.ReceiptProcessingTransport
import com.pantryproof.prototype.ui.PantryUiState
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.security.MessageDigest
import java.util.ArrayDeque
import java.util.zip.ZipFile
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/** Original transferred ZIP-member bytes; no Python execution, wire reconstruction or UI wiring. */
@RunWith(Parameterized::class)
class L05RealOcrV1KotlinConsumptionTest(private val caseName: String) {
    private val sufficient = caseName == "sufficient"
    private val member = "l05-real-ocr-$caseName-v1.json"
    private val expectedHash = if (sufficient) SUFFICIENT_HASH else INSUFFICIENT_HASH
    private val context = PresentationConsumerContext(REQUEST_ID, IMAGE_ID, PresentationConsumerMode.FIXTURE)
    private val pantry = PantryUiState(MockReceiptPresentationSource())
    private val originalInventory = pantry.inventory.toList()
    private val originalReceipt = pantry.receipt
    private val originalPresentation = pantry.presentationResult

    @After
    fun consumptionNeverConfirmsOrMutatesSessionInventory() {
        assertEquals(originalInventory, pantry.inventory)
        originalInventory.zip(pantry.inventory).forEach { (before, after) -> assertSame(before, after) }
        assertSame(originalReceipt, pantry.receipt)
        assertSame(originalPresentation, pantry.presentationResult)
        assertFalse(pantry.demoConfirmed)
    }

    @Test
    fun originalBytesPassStrictValidationAndPreserveSourceEvidence() {
        val bytes = originalBytes()
        val value = validated(bytes)
        assertEquals("receipt-presentation", value.schemaName)
        assertEquals("1", value.schemaVersion)
        assertEquals("0", value.sourceContractVersion)
        assertEquals(REQUEST_ID, value.requestId)
        assertEquals(IMAGE_ID, value.imageId)
        assertEquals(PresentationSourceType.SYNTHETIC_FIXTURE, value.source.type)
        assertEquals("I2B_SYNTHETIC_B2_V0", value.source.provenance.sourceSystem)
        assertEquals("src-$ALIAS-1", value.source.provenance.sourceReference)
        assertNull(value.source.provenance.contentSha256)
        val evidence = requireNotNull(value.sourceEvidence)
        assertEquals(SourceProcessingStatus.OCR_COMPLETED, evidence.sourceProcessingStatus)
        assertEquals((1..5).map { "tok-$ALIAS-$it" }, evidence.tokenIds)
        val gate = requireNotNull(value.sourceGate)
        assertEquals("gat-$ALIAS-1", gate.gateResultId)
        assertEquals(if (sufficient) SourceGateDecision.SUFFICIENT else SourceGateDecision.INSUFFICIENT, gate.decision)
        assertEquals(if (sufficient) emptyList<String>() else listOf(INSUFFICIENT_REASON), gate.reasons)
        assertEquals(expectedOutcome(), value.outcome.status)
        assertNull(value.outcome.failure)
        if (sufficient) {
            val automatic = requireNotNull(value.automaticExtraction)
            assertEquals(AutomaticExtractionStage.PRE_REVIEW_AUTOMATIC, automatic.stage)
            assertEquals(AutomaticExtractionStatus.EXTRACTED, automatic.extractionStatus)
            assertEquals("I2B_SYNTHETIC_L05", automatic.producer.producerId)
            assertEquals("B2-layout-graph-v0", automatic.producer.producerVersion)
            assertNotNull(value.receipt)
        } else {
            assertNull(value.receipt)
            assertNull(value.automaticExtraction)
        }
        assertEquals(expectedHash, sha256(bytes))
    }

    @Test
    fun adapterRetainsExactEmittedValuesWithoutInventingReceiptOrMetadata() {
        val bytes = originalBytes()
        val envelope = validated(bytes)
        val result = M3eReceiptPresentationAdapter().decodeAndMap(bytes, context)
        assertExpectedUi(result)
        if (sufficient) {
            val source = requireNotNull(envelope.receipt)
            val mapped = (result as ReceiptPresentationUiResult.Available).receipt
            assertEquals("rct-$ALIAS-1", source.receiptId)
            assertEquals(source.receiptId, mapped.receiptId)
            assertEquals("MYR", source.currencyCode)
            assertEquals(source.currencyCode, mapped.currencyCode)
            assertEquals(AutomaticExtractionStatus.EXTRACTED, mapped.automaticExtractionStatus)
            assertEquals(listOf(ReceiptFieldRole.STORE_NAME, ReceiptFieldRole.PURCHASE_DATE, ReceiptFieldRole.RECEIPT_TOTAL), source.receiptFields.map { it.role })
            assertEquals(listOf("row-$ALIAS-1", "row-$ALIAS-2"), source.itemRows.map { it.rowId })
            assertEquals(source.itemRows.map { it.rowId }, mapped.items.map { it.rowId })
            source.itemRows.forEach { row ->
                assertEquals(listOf(ReceiptFieldRole.ITEM_DESCRIPTION, ReceiptFieldRole.QUANTITY, ReceiptFieldRole.UNIT_PRICE, ReceiptFieldRole.LINE_TOTAL), row.fields.map { it.role })
            }
            val fields = source.receiptFields + source.itemRows.flatMap { it.fields }
            // Expected strings were inspected in the hash-verified transferred bytes, not guessed from OCR.
            val expectedValues = listOf("PANTRYPROOF TEST MART", "2026-10-13", "23.90", "MILK", "2", "5.50", "11.00", "RICE", "1", "12.90", "12.90")
            val tokenNumbers = listOf(1, 2, 5, 3, 3, 3, 3, 4, 4, 4, 4)
            val uiFields = listOf(mapped.storeName, mapped.purchaseDate, mapped.receiptTotal) + mapped.items.flatMap {
                listOf(it.description, it.quantity, it.unitPrice, it.lineTotal)
            }
            assertEquals(expectedValues.size, fields.size)
            assertEquals(fields.size, uiFields.size)
            fields.forEachIndexed { index, field ->
                assertEquals("fld-$ALIAS-${index + 1}", field.fieldId)
                assertEquals(ReceiptFieldStatus.EXTRACTED, field.status)
                assertEquals(expectedValues[index], field.originalAutomaticValue)
                assertEquals(expectedValues[index], field.presentationValue)
                assertNull(field.absenceReason)
                assertNull(field.nativeConfidence)
                assertEquals(listOf("tok-$ALIAS-${tokenNumbers[index]}"), field.sourceTokenIds)
                assertUiField(field, uiFields[index])
            }
        } else {
            assertNull(envelope.receipt)
            assertNull(envelope.automaticExtraction)
            assertEquals(listOf(INSUFFICIENT_REASON), (result as ReceiptPresentationUiResult.InsufficientEvidence).reasons)
            assertFalse(result.canReview)
        }
        assertEquals(expectedHash, sha256(bytes))
    }

    @Test
    fun wrongExpectedRequestRejectsOriginalBytesInBothConsumers() = rejectBoth(
        context.copy(expectedRequestId = "request-l05-mismatch"), ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
    )

    @Test
    fun wrongExpectedImageRejectsOriginalBytesInBothConsumers() = rejectBoth(
        context.copy(expectedImageId = "image-l05-mismatch"), ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
    )

    @Test
    fun liveModeRejectsOriginalSyntheticSourceInBothConsumers() = rejectBoth(
        context.copy(mode = PresentationConsumerMode.LIVE), ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
    )

    @Test
    fun coordinatorBindsCallerContextAndConsumesACompletionExactlyOnce() {
        val coordinator = ReceiptPresentationRequestCoordinator()
        val wrong = coordinator.begin(context.copy(expectedRequestId = "request-l05-mismatch"))
        val rejected = coordinator.complete(wrong, originalBytes())
        assertTrue(rejected is ReceiptPresentationUiResult.Rejected)
        assertEquals(ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH, (rejected as ReceiptPresentationUiResult.Rejected).issue.code)
        assertNull(coordinator.complete(wrong, originalBytes()))
        val attempt = coordinator.begin(context)
        assertExpectedUi(coordinator.complete(attempt, originalBytes()))
        assertNull(coordinator.complete(attempt, originalBytes()))
    }

    @Test
    fun cancelledAndSupersededAttemptsCannotCompleteAnIdenticalIdRetry() {
        val coordinator = ReceiptPresentationRequestCoordinator()
        val cancelled = coordinator.begin(context)
        coordinator.cancel(cancelled)
        assertNull(coordinator.complete(cancelled, originalBytes()))
        val old = coordinator.begin(context)
        val retry = coordinator.begin(context)
        assertNotSame(old, retry)
        coordinator.cancel(old)
        assertNull(coordinator.complete(old, originalBytes()))
        assertExpectedUi(coordinator.complete(retry, originalBytes()))
        assertNull(coordinator.complete(retry, originalBytes()))
    }

    @Test
    fun lifecycleAdmitsExactBytesOnceWithOriginalRequestAssociation() {
        val h = Harness()
        val request = h.start()
        assertSame(request, h.calls.single().request)
        assertEquals(context, request.context)
        h.calls.single().deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.worker.drain()
        assertTrue(h.lifecycle.state is ReceiptProcessingLifecycle.State.Pending)
        assertEquals(1, h.consumptions)
        h.ui.drain()
        val finished = h.lifecycle.state as ReceiptProcessingLifecycle.State.Finished
        assertSame(request, finished.request)
        assertExpectedUi((finished.outcome as ReceiptProcessingLifecycle.Outcome.Presentation).result)
        assertEquals(if (sufficient) "Review receipt fields" else null, finished.outcome.reviewTitle)
        h.calls.single().deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.drain()
        assertSame(finished, h.lifecycle.state)
        assertEquals(1, h.consumptions)
        h.lifecycle.dispose()
        h.drain()
    }

    @Test
    fun lifecycleCancellationAndReplacementSuppressLateOriginalBytes() {
        val h = Harness()
        h.start()
        val oldCall = h.calls.single()
        h.lifecycle.cancel()
        assertTrue(h.lifecycle.state is ReceiptProcessingLifecycle.State.Ready)
        oldCall.deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.drain()
        assertEquals(0, h.consumptions)
        assertEquals(1, h.cancellations)
        val retry = h.start(select = false)
        assertNotSame(oldCall.request.submission, retry.submission)
        assertSame(oldCall.request.selection, retry.selection)
        // Deliberate same-ID retry isolates reference identity, not normal fresh-ID policy.
        assertEquals(oldCall.request.context, retry.context)
        oldCall.deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.calls.last().deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.drain()
        assertEquals(1, h.consumptions)
        assertSame(retry, (h.lifecycle.state as ReceiptProcessingLifecycle.State.Finished).request)
        h.lifecycle.dispose()
        h.drain()
    }

    @Test
    fun lifecycleSelectionReplacementRejectsAlreadyValidatedButUndeliveredResult() {
        val h = Harness()
        val old = h.start()
        h.calls.single().deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.worker.drain()
        assertEquals(1, h.consumptions)
        assertTrue(h.lifecycle.state is ReceiptProcessingLifecycle.State.Pending)
        h.lifecycle.selectInput()
        val ready = h.lifecycle.state as ReceiptProcessingLifecycle.State.Ready
        assertNotSame(old.selection, ready.selection)
        assertEquals(old.selection.imageId, ready.selection.imageId)
        h.ui.drain()
        h.worker.drain()
        assertSame(ready, h.lifecycle.state)
        val current = h.start(select = false)
        h.calls.last().deliver(ReceiptProcessingDelivery.Envelope(originalBytes()))
        h.drain()
        assertSame(current, (h.lifecycle.state as ReceiptProcessingLifecycle.State.Finished).request)
        assertEquals(2, h.consumptions)
        h.lifecycle.dispose()
        h.drain()
    }

    private fun rejectBoth(changedContext: PresentationConsumerContext, code: String) {
        val bytes = originalBytes()
        val validated = ReceiptPresentationV1Validator.decodeAndValidate(bytes, changedContext)
        assertTrue(validated is ReceiptPresentationResult.Rejected)
        assertEquals(code, (validated as ReceiptPresentationResult.Rejected).issue.code)
        val ui = M3eReceiptPresentationAdapter().decodeAndMap(bytes, changedContext)
        assertTrue(ui is ReceiptPresentationUiResult.Rejected)
        assertEquals(code, (ui as ReceiptPresentationUiResult.Rejected).issue.code)
        assertFalse(ui.canReview)
        assertEquals(expectedHash, sha256(bytes))
    }

    private fun validated(bytes: ByteArray): ReceiptPresentationV1 {
        val result = ReceiptPresentationV1Validator.decodeAndValidate(bytes, context)
        assertTrue("Strict consumer must accept hash-verified $caseName evidence", result is ReceiptPresentationResult.Accepted)
        return (result as ReceiptPresentationResult.Accepted).value
    }

    private fun assertExpectedUi(result: ReceiptPresentationUiResult?) {
        if (sufficient) {
            assertTrue(result is ReceiptPresentationUiResult.Available)
            assertTrue(requireNotNull(result).canReview)
        } else {
            assertTrue(result is ReceiptPresentationUiResult.InsufficientEvidence)
            assertFalse(requireNotNull(result).canReview)
        }
    }

    private fun assertUiField(source: PresentationField, mapped: PresentedField) {
        assertEquals(source.fieldId, mapped.id)
        assertEquals(source.status.name, mapped.status.name)
        assertEquals(source.originalAutomaticValue, mapped.originalAutomaticValue)
        assertEquals(source.presentationValue, mapped.value)
        assertEquals(source.absenceReason, mapped.absenceReason)
    }

    private fun expectedOutcome() = if (sufficient) PresentationOutcomeStatus.RESULT_AVAILABLE
        else PresentationOutcomeStatus.SOURCE_EVIDENCE_INSUFFICIENT

    private fun originalBytes(): ByteArray = ZipFile(archive().toFile()).use { zip ->
        val entries = zip.entries().asSequence().toList()
        assertEquals(8, entries.size)
        assertEquals(8, entries.map { it.name }.toSet().size)
        val manifest = zip.getInputStream(requireNotNull(zip.getEntry("l05-real-ocr-payload-manifest.json"))).use { it.readBytes() }
        assertEquals("1f4422acf18c8da586a509400d51033662b60466ffd015887363d669b5a7cffc", sha256(manifest))
        val bytes = zip.getInputStream(requireNotNull(zip.getEntry(member))).use { it.readBytes() }
        assertEquals(if (sufficient) 4172 else 890, bytes.size)
        assertEquals(expectedHash, sha256(bytes))
        bytes
    }

    private fun archive(): Path {
        var root: Path? = Paths.get("").toAbsolutePath()
        while (root != null && !Files.isRegularFile(root.resolve("tests/fixtures/receipt_presentation_v1/v1/manifest.json"))) root = root.parent
        val file = requireNotNull(root).resolve("artifacts/tai-l05-s02-consumption-20261119-01/received/pantryproof-l05-s02-source-bound-v1-transfer.zip")
        check(Files.isRegularFile(file)) { "Original L05 source-bound transfer evidence is required" }
        assertEquals(19246L, Files.size(file))
        assertEquals("faa6c0aa47da6497fef92ed667667aa8ce39c8d8149444f555e21ae315c6f85c", sha256(Files.readAllBytes(file)))
        return file
    }

    private data class Call(val request: ReceiptProcessingRequest, val deliver: (ReceiptProcessingDelivery) -> Unit)

    /** Independent deterministic queues; these tests assert ordering, not production threading. */
    private class Queue {
        private val tasks = ArrayDeque<() -> Unit>()
        fun post(task: () -> Unit) { tasks.addLast(task) }
        fun drain() { var count = 0; while (tasks.isNotEmpty()) { check(count++ < 100); tasks.removeFirst().invoke() } }
    }

    private class Harness {
        val worker = Queue()
        val ui = Queue()
        val calls = mutableListOf<Call>()
        var consumptions = 0
        var cancellations = 0
        private val coordinator = ReceiptPresentationRequestCoordinator()
        val lifecycle = ReceiptProcessingLifecycle(
            transport = ReceiptProcessingTransport { request, deliver ->
                calls.add(Call(request, deliver))
                ReceiptProcessingTransport.Cancellation { cancellations++ }
            },
            postWorker = worker::post,
            postUi = ui::post,
            schedule = { delay, _ -> assertEquals(100L, delay) },
            nowMillis = { 0L },
            timeoutMillis = 100L,
            newImageId = { IMAGE_ID },
            newRequestId = { REQUEST_ID },
            coordinator = coordinator,
            completeAttempt = { attempt, bytes -> consumptions++; coordinator.complete(attempt, bytes) },
        )

        fun start(select: Boolean = true): ReceiptProcessingRequest {
            if (select) lifecycle.selectInput()
            lifecycle.submit(PresentationConsumerMode.FIXTURE)
            val request = (lifecycle.state as ReceiptProcessingLifecycle.State.Pending).request
            drain()
            return request
        }

        fun drain() { repeat(4) { worker.drain(); ui.drain() } }
    }

    companion object {
        private const val REQUEST_ID = "request-l05-synthetic-1"
        private const val IMAGE_ID = "image-l05-synthetic-1"
        private const val ALIAS = "v1-0123456789abcdef0123456789abcdef"
        private const val SUFFICIENT_HASH = "d73f6ef4bbbe2b850dcc3c8bb5f71fe4dde8a666a968adb10e596e6f0d4ff12b"
        private const val INSUFFICIENT_HASH = "a5075d6f9d5cea5137b69778bcb8bae4f86312de61c09514a3109505453a094d"
        private const val INSUFFICIENT_REASON = "Synthetic source structure was unavailable."

        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun cases(): Collection<Array<Any>> = listOf(arrayOf<Any>("sufficient"), arrayOf<Any>("insufficient"))

        private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
            .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }
}
