package com.pantryproof.prototype.data

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonToken
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationFailureStage
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.Outcome
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.State
import com.pantryproof.prototype.ui.PantryUiState
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptProcessingLifecycleTest {
    private val cases = mutableListOf<Harness>()

    @After
    fun inventoryAndConfirmationRemainUnchanged() {
        for (h in cases) {
            assertEquals(h.originalInventory, h.pantry.inventory)
            assertSame(h.originalReceipt, h.pantry.receipt)
            assertFalse(h.pantry.demoConfirmed)
        }
    }

    @Test
    fun i2c01SelectionAndSubmissionBindBeforeFakeRuns() {
        val h = harness()
        assertSame(State.Idle, h.lifecycle.state)
        val a = h.select(F01)
        assertEquals(F01.imageId, a.imageId)
        assertTrue(h.worker.isEmpty)
        assertTrue(h.fake.calls.isEmpty())

        val request = h.submit(F01)
        h.worker.step()
        assertSame(request, h.pending())
        assertTrue(h.fake.calls.isEmpty())
        h.ui.step()
        assertTrue(h.fake.calls.isEmpty())
        h.worker.step()

        assertSame(request, h.fake.calls.single().request)
        assertSame(a, request.selection)
        assertEquals(F01.requestId, request.context.expectedRequestId)
        assertEquals(F01.imageId, request.context.expectedImageId)
        assertEquals(PresentationConsumerMode.FIXTURE, request.context.mode)
        assertEquals(100L, h.deadlines.single())
        assertTrue(h.completed.isEmpty())
        h.assertTerminals()
    }

    @Test
    fun i2c02MatchingFixtureCompletesOnce() {
        val h = harness()
        val call = h.start(F01)
        call.bytes(F01)
        h.worker.drain()
        assertSame(call.request, h.pending())
        h.ui.drain()
        call.bytes(F01)
        h.drain()

        val receipt = h.review(call.request)
        assertEquals("31.90", receipt.receiptTotal.value)
        assertEquals("RM 31.90", receipt.receiptTotal.originalAutomaticValue)
        assertEquals(1, h.completed.size)
        h.assertTerminals(call.request)
    }

    @Test
    fun i2c03MissingAndUnresolvedFieldsStayDistinct() {
        for ((fixture, status, reason) in listOf(
            Triple(F03, PresentedFieldStatus.MISSING, "STORE_NAME_NOT_OBSERVED"),
            Triple(F04, PresentedFieldStatus.UNRESOLVED, "AMBIGUOUS_DATE_FORMAT"),
        )) {
            val h = harness()
            val call = h.start(fixture)
            call.bytes(fixture)
            h.drain()
            val receipt = h.review(call.request)
            val field = when (status) {
                PresentedFieldStatus.MISSING -> receipt.storeName
                else -> receipt.purchaseDate
            }
            assertEquals(status, field.status)
            assertEquals(reason, field.absenceReason)
            assertNull(field.value)
            assertNull(field.originalAutomaticValue)
            call.bytes(fixture)
            h.drain()
            assertEquals(1, h.completed.size)
            h.assertTerminals(call.request)
        }
    }

    @Test
    fun i2c04WeightedQuantityIsExact() {
        val h = harness()
        val call = h.start(F05)
        call.bytes(F05)
        h.drain()
        assertEquals("0.750", h.review(call.request).items.single().quantity.value)
        assertEquals(1, h.completed.size)
        h.assertTerminals(call.request)
    }

    @Test
    fun i2c05FailedExtractionUsesNeutralReview() {
        val h = harness()
        val call = h.start(F15)
        call.bytes(F15)
        h.drain()
        assertEquals("Review receipt fields", h.presentation(call.request).reviewTitle)
        assertTrue(h.presentation(call.request).result.canReview)
        assertEquals(1, h.completed.size)
        h.assertTerminals(call.request)
    }

    @Test
    fun i2c06InsufficientEvidencePreservesReasons() {
        val h = harness()
        val call = h.start(F16)
        call.bytes(F16)
        h.drain()
        val result = h.presentation(call.request).result as ReceiptPresentationUiResult.InsufficientEvidence
        assertEquals(listOf("RECEIPT_STRUCTURE_NOT_RELIABLY_OBSERVED"), result.reasons)
        h.assertNonReview(call.request)
    }

    @Test
    fun i2c07UnavailablePreservesCodeAndRetryability() {
        val h = harness()
        val call = h.start(F06)
        call.bytes(F06)
        h.drain()
        assertEquals(
            ReceiptPresentationUiResult.ProcessingUnavailable("PROCESSOR_NOT_AVAILABLE", false),
            h.presentation(call.request).result,
        )
        h.assertNonReview(call.request)
    }

    @Test
    fun i2c08FailurePreservesStageCodeAndRetryability() {
        val h = harness()
        val call = h.start(F07)
        call.bytes(F07)
        h.drain()
        assertEquals(
            ReceiptPresentationUiResult.ProcessingFailed(PresentationFailureStage.OCR, "OCR_ENGINE_FAILURE", true),
            h.presentation(call.request).result,
        )
        h.assertNonReview(call.request)
    }

    @Test
    fun i2c09LiveRejectsFixtureSource() {
        val h = harness()
        val call = h.start(F01, PresentationConsumerMode.LIVE)
        call.bytes(F01)
        h.drain()
        h.assertRejected(call.request, ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH)
    }

    @Test
    fun i2c10ExpectedIdsComeFromSubmission() {
        for ((fixture, code) in listOf(
            F01.copy(requestId = "request-wrong") to ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            F01.copy(imageId = "image-wrong") to ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
        )) {
            val h = harness()
            val call = h.start(fixture)
            call.bytes(F01)
            h.drain()
            h.assertRejected(call.request, code)
        }
    }

    @Test
    fun i2c11MalformedAndEmptyBytesAreRejectedOnce() {
        for (bytes in listOf(byteArrayOf('{'.code.toByte()), byteArrayOf())) {
            val h = harness()
            val call = h.start(F01)
            call.bytes(bytes)
            h.drain()
            call.bytes(F01)
            h.drain()
            h.assertRejected(call.request, ReceiptPresentationIssueCodes.INVALID_JSON)
        }
    }

    @Test
    fun i2c12NoEnvelopeDoesNotValidateLateBytes() {
        val h = harness()
        val call = h.start(F01)
        call.deliver(ReceiptProcessingDelivery.NoEnvelope)
        h.drain()
        call.bytes(F01)
        h.drain()
        assertEquals(Outcome.LocalFailure.MISSING_RESPONSE, h.finished(call.request))
        assertTrue(h.completed.isEmpty())
        h.assertTerminals(call.request)
    }

    @Test
    fun i2c13DeadlineWinsForSilenceAndUndeliveredWorkerResult() {
        for (computed in listOf(false, true)) {
            val h = harness()
            val call = h.start(F01)
            if (computed) {
                call.bytes(F01)
                h.worker.drain()
            }
            h.now = 100
            h.timer.step()
            h.ui.drain()
            if (!computed) call.bytes(F01)
            h.drain()
            assertEquals(Outcome.LocalFailure.TIMEOUT, h.finished(call.request))
            assertEquals(if (computed) 1 else 0, h.completed.size)
            h.assertTerminals(call.request)
        }
    }

    @Test
    fun i2c14PreviouslyAdmittedResultSurvivesTimer() {
        val h = harness()
        val call = h.start(F01)
        call.bytes(F01)
        h.worker.drain()
        h.now = 99
        h.ui.drain()
        val admitted = h.lifecycle.state
        h.now = 100
        h.timer.step()
        h.drain()
        assertSame(admitted, h.lifecycle.state)
        h.review(call.request)
        assertEquals(1, h.completed.size)
        h.assertTerminals(call.request)
    }

    @Test
    fun i2c15CancelInvalidatesBeforeLateDelivery() {
        val h = harness()
        val call = h.start(F01)
        h.lifecycle.cancel()
        assertSame(call.request.selection, h.ready())
        h.worker.drain()
        assertEquals(1, call.cancellations)
        call.bytes(F01)
        h.drain()
        assertSame(call.request.selection, h.ready())
        assertTrue(h.completed.isEmpty())
        h.assertTerminals()
    }

    @Test
    fun i2c16ReplacementScopesLateEventsToOldAttempt() {
        val h = harness()
        val a = h.start(F01)
        h.select(F05)
        val staleCleanup = h.worker.take()
        val requestB = h.submit(F05)
        h.drain()
        val b = h.fake.calls.last()
        assertSame(requestB, b.request)
        assertNotSame(a.request.selection, b.request.selection)
        assertSame(a.request.selection.owner, b.request.selection.owner)
        assertFalse(a.request.context.expectedImageId == b.request.context.expectedImageId)
        a.bytes(F01)
        h.worker.post(staleCleanup)
        a.deliver(ReceiptProcessingDelivery.ExecutionFailure)
        h.drain()
        assertSame(b.request, h.pending())
        assertEquals(1, a.cancellations)
        assertEquals(0, b.cancellations)
        b.bytes(F05)
        h.drain()
        assertEquals("0.750", h.review(b.request).items.single().quantity.value)
        assertEquals(1, h.completed.size)
        h.assertTerminals(b.request)
    }

    @Test
    fun i2c17IdenticalIdRetryCannotConsumeOldAttempt() {
        val h = harness()
        val old = h.start(F01)
        h.lifecycle.cancel()
        val retry = h.retry(F01.requestId)
        assertEquals(old.request.context, retry.request.context)
        assertSame(old.request.selection, retry.request.selection)
        assertNotSame(old.request.submission, retry.request.submission)

        old.bytes(F01)
        h.drain()

        assertSame(retry.request, h.pending())
        assertTrue(h.completed.isEmpty())
        retry.bytes(F01)
        h.drain()
        retry.bytes(F01)
        h.drain()
        h.review(retry.request)
        assertEquals(1, h.completed.size)
        h.assertTerminals(retry.request)
    }

    @Test
    fun i2c18NewRequestIdSeparatesStaleCallbackFromMismatchedEnvelope() {
        for (deliverViaRetry in listOf(false, true)) {
            val h = harness()
            val old = h.start(F01)
            h.lifecycle.cancel()
            val retry = h.retry("request-i2c-retry-002")
            assertSame(old.request.selection, retry.request.selection)
            assertEquals(old.request.context.expectedImageId, retry.request.context.expectedImageId)
            assertFalse(old.request.context.expectedRequestId == retry.request.context.expectedRequestId)
            (if (deliverViaRetry) retry else old).bytes(F01)
            h.drain()

            if (deliverViaRetry) {
                h.assertRejected(retry.request, ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH)
            } else {
                assertSame(retry.request, h.pending())
                assertTrue(h.completed.isEmpty())
                h.assertTerminals()
            }
        }
    }

    @Test
    fun i2c19FirstWorkerClaimWinsInEitherOrder() {
        for (bytesFirst in listOf(false, true)) {
            val h = harness()
            val call = h.start(F01)
            val bytes = ReceiptProcessingDelivery.Envelope(F01.envelope())
            val missing = ReceiptProcessingDelivery.NoEnvelope
            listOf(if (bytesFirst) bytes else missing, if (bytesFirst) missing else bytes)
                .forEach(call.deliver)
            h.worker.drain()
            assertSame(call.request, h.pending())
            h.ui.drain()

            if (bytesFirst) h.review(call.request)
            else assertEquals(Outcome.LocalFailure.MISSING_RESPONSE, h.finished(call.request))
            assertEquals(if (bytesFirst) 1 else 0, h.completed.size)
            h.assertTerminals(call.request)
        }
    }

    @Test
    fun i2c20ValidI1ReturnCannotOverwriteNewSelection() {
        for (deliverBAheadOfA in listOf(false, true)) {
            val h = harness()
            val a = h.start(F01)
            a.bytes(F01)
            h.worker.drain()
            assertTrue(h.completed.single().result is ReceiptPresentationUiResult.Available)
            val heldA = h.ui.take()

            val b = h.start(F05)
            if (deliverBAheadOfA) {
                b.bytes(F05)
                h.drain()
                h.review(b.request)
            }
            val before = h.lifecycle.state
            h.applyUi(heldA)
            assertSame(before, h.lifecycle.state)
            if (!deliverBAheadOfA) {
                assertSame(b.request, h.pending())
                h.assertTerminals()
                b.bytes(F05)
                h.drain()
            }
            assertEquals("0.750", h.review(b.request).items.single().quantity.value)
            assertEquals(2, h.completed.size)
            assertNotSame(h.completed[0].attempt, h.completed[1].attempt)
            h.assertTerminals(b.request)
        }
    }

    @Test
    fun i2c21SubmissionAndPostConsumptionExceptionsAreLocal() {
        for (afterConsumption in listOf(false, true)) {
            val h = harness(throwAfterCompletion = afterConsumption)
            h.fake.throwOnSubmit = !afterConsumption
            val call = h.start(F01)
            if (afterConsumption) call.bytes(F01)
            h.drain()
            call.bytes(F01)
            h.drain()

            assertEquals(Outcome.LocalFailure.EXECUTION_FAILURE, h.finished(call.request))
            assertEquals(if (afterConsumption) 1 else 0, h.completed.size)
            if (afterConsumption) assertTrue(h.completed.single().result is ReceiptPresentationUiResult.Available)
            h.assertTerminals(call.request)
        }
    }

    @Test
    fun i2c22DisposedOwnerCannotDeliverToReplacementOwner() {
        val old = harness()
        val a = old.start(F01)
        old.lifecycle.dispose()
        val replacement = harness()
        val b = replacement.select(F05)
        assertNotSame(a.request.selection.owner, b.owner)
        a.bytes(F01)
        old.drain()
        replacement.drain()

        assertSame(State.Idle, old.lifecycle.state)
        assertSame(b, replacement.ready())
        assertTrue(old.completed.isEmpty())
        old.assertTerminals()
        replacement.assertTerminals()
    }

    @Test
    fun i2c23StaleStartupIsSkippedBeforeTokenBinding() {
        val h = harness()
        h.select(F01)
        val a = h.submit(F01)
        h.select(F05)
        val b = h.submit(F05)
        h.worker.step()
        assertTrue(h.ui.isEmpty)
        assertTrue(h.fake.calls.isEmpty())
        h.drain()

        assertNotSame(a.submission, b.submission)
        assertSame(b, h.pending())
        assertSame(b, h.fake.calls.single().request)
        assertTrue(h.completed.isEmpty())
        h.assertTerminals()
    }

    @Test
    fun i2cX01UiInvalidatesWhileCoordinatorMonitorIsHeld() {
        val h = harness()
        val a = h.start(F01)
        val locked = CountDownLatch(1)
        val release = CountDownLatch(1)
        val monitorThread = Executors.newSingleThreadExecutor()
        val uiThread = Executors.newSingleThreadExecutor()
        val workerThread = Executors.newSingleThreadExecutor()
        try {
            val holder = monitorThread.submit {
                synchronized(h.coordinator) {
                    locked.countDown()
                    check(release.await(10, TimeUnit.SECONDS))
                }
            }
            assertTrue(locked.await(10, TimeUnit.SECONDS))
            val submittedB = uiThread.submit<ReceiptProcessingRequest> {
                h.lifecycle.cancel()
                assertSame(a.request.selection, h.ready())
                h.select(F05)
                h.submit(F05)
            }.get(10, TimeUnit.SECONDS)
            assertSame(submittedB, h.pending())

            val cleanupStarted = CountDownLatch(1)
            val cleanup = workerThread.submit {
                cleanupStarted.countDown()
                h.worker.step()
            }
            assertTrue(cleanupStarted.await(10, TimeUnit.SECONDS))
            assertFalse(cleanup.isDone)
            release.countDown()
            holder.get(10, TimeUnit.SECONDS)
            cleanup.get(10, TimeUnit.SECONDS)
            h.drain()
            val b = h.fake.calls.last()
            assertSame(submittedB, b.request)
            assertEquals(1, a.cancellations)
            a.bytes(F01)
            b.bytes(F05)
            h.drain()
            assertEquals("0.750", h.review(b.request).items.single().quantity.value)
            assertEquals(1, h.completed.size)
            h.assertTerminals(b.request)
        } finally {
            release.countDown()
            monitorThread.shutdownNow()
            uiThread.shutdownNow()
            workerThread.shutdownNow()
        }
    }

    @Test
    fun i2cX02ProducerMutationCannotAlterHandedOffBytes() {
        val h = harness()
        val call = h.start(F01)
        val original = F01.envelope()
        val scratch = original.copyOf()
        call.bytes(scratch)
        scratch.fill(0)

        h.worker.drain()
        assertArrayEquals(original, h.completed.single().bytes)
        h.ui.drain()
        call.bytes(original.copyOf())
        h.drain()
        assertEquals("31.90", h.review(call.request).receiptTotal.value)
        assertEquals(1, h.completed.size)
        h.assertTerminals(call.request)
    }

    private fun harness(throwAfterCompletion: Boolean = false) =
        Harness(throwAfterCompletion).also(cases::add)

    private class Harness(throwAfterCompletion: Boolean) {
        val worker = Queue()
        val ui = Queue()
        val timer = Queue()
        val deadlines = mutableListOf<Long>()
        val fake = Fake()
        val coordinator = ReceiptPresentationRequestCoordinator()
        val completed = mutableListOf<Completion>()
        val terminals = mutableListOf<ReceiptProcessingRequest>()
        val pantry = PantryUiState(MockReceiptPresentationSource())
        val originalInventory = pantry.inventory.toList()
        val originalReceipt = pantry.receipt
        var now = 0L
        private val imageIds = ArrayDeque<String>()
        private val requestIds = ArrayDeque<String>()
        val lifecycle = ReceiptProcessingLifecycle(
            transport = fake,
            postWorker = worker::post,
            postUi = { action -> ui.post { applyUi(action) } },
            schedule = { delay, action ->
                deadlines += now + delay
                timer.post(action)
            },
            nowMillis = { now },
            timeoutMillis = 100,
            newImageId = imageIds::removeFirst,
            newRequestId = requestIds::removeFirst,
            coordinator = coordinator,
            completeAttempt = { attempt, bytes ->
                val result = coordinator.complete(attempt, bytes)
                completed += Completion(attempt, bytes.copyOf(), result)
                if (throwAfterCompletion) throw IllegalStateException("Injected completion failure")
                result
            },
        )

        fun select(fixture: Fixture): ReceiptProcessingRequest.Selection {
            imageIds.addLast(fixture.imageId)
            lifecycle.selectInput()
            return ready()
        }

        fun submit(fixture: Fixture, mode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE) =
            submit(fixture.requestId, mode)

        private fun submit(id: String, mode: PresentationConsumerMode): ReceiptProcessingRequest {
            requestIds.addLast(id)
            lifecycle.submit(mode)
            return pending()
        }

        fun retry(id: String): Fake.Call {
            val r = submit(id, PresentationConsumerMode.FIXTURE)
            drain()
            return fake.calls.last().also { assertSame(r, it.request) }
        }

        fun start(fixture: Fixture, mode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE): Fake.Call {
            select(fixture)
            val request = submit(fixture, mode)
            drain()
            return fake.calls.last().also { assertSame(request, it.request) }
        }

        fun ready() = (lifecycle.state as State.Ready).selection
        fun pending() = (lifecycle.state as State.Pending).request
        fun finished(request: ReceiptProcessingRequest): Outcome {
            val state = lifecycle.state as State.Finished
            assertSame(request, state.request)
            return state.outcome
        }

        fun presentation(request: ReceiptProcessingRequest) = finished(request) as Outcome.Presentation

        fun review(request: ReceiptProcessingRequest): PresentedReceipt {
            val presentation = presentation(request)
            assertEquals("Review receipt fields", presentation.reviewTitle)
            return (presentation.result as ReceiptPresentationUiResult.Available).receipt
        }

        fun assertRejected(request: ReceiptProcessingRequest, code: String) {
            val result = presentation(request).result as ReceiptPresentationUiResult.Rejected
            assertEquals(code, result.issue.code)
            assertNonReview(request)
        }

        fun assertNonReview(request: ReceiptProcessingRequest) {
            assertFalse(presentation(request).result.canReview)
            assertNull(presentation(request).reviewTitle)
            assertEquals(1, completed.size)
            assertTerminals(request)
        }

        fun assertTerminals(vararg expected: ReceiptProcessingRequest) {
            assertEquals(expected.toList(), terminals)
        }

        fun applyUi(action: () -> Unit) {
            val before = lifecycle.state
            action()
            val after = lifecycle.state
            if (after is State.Finished && before !== after) terminals += after.request
        }

        fun drain() {
            while (!worker.isEmpty || !ui.isEmpty) {
                if (!worker.isEmpty) worker.step()
                if (!ui.isEmpty) ui.step()
            }
        }
    }

    private data class Completion(
        val attempt: ReceiptPresentationRequestCoordinator.Attempt,
        val bytes: ByteArray,
        val result: ReceiptPresentationUiResult?,
    )

    private class Queue {
        private val work = ConcurrentLinkedQueue<() -> Unit>()
        val isEmpty: Boolean get() = work.isEmpty()
        fun post(action: () -> Unit) { work.add(action) }
        fun take(): () -> Unit = checkNotNull(work.poll())
        fun step() = take()()
        fun drain() { while (!isEmpty) step() }
    }

    private class Fake : ReceiptProcessingTransport {
        val calls = mutableListOf<Call>()
        var throwOnSubmit = false

        override fun submit(
            request: ReceiptProcessingRequest,
            deliver: (ReceiptProcessingDelivery) -> Unit,
        ): ReceiptProcessingTransport.Cancellation {
            val call = Call(request, deliver)
            calls += call
            if (throwOnSubmit) throw IllegalStateException("Injected submit failure")
            return ReceiptProcessingTransport.Cancellation { call.cancellations++ }
        }

        class Call(val request: ReceiptProcessingRequest, val deliver: (ReceiptProcessingDelivery) -> Unit) {
            var cancellations = 0
            fun bytes(fixture: Fixture) = bytes(fixture.envelope())
            fun bytes(scratch: ByteArray) = deliver(ReceiptProcessingDelivery.Envelope(scratch))
        }
    }

    private data class Fixture(val name: String, val requestId: String, val imageId: String) {
        fun envelope(): ByteArray {
            val file = generateSequence(Path.of("").toAbsolutePath()) { it.parent }
                .map { it.resolve("tests/fixtures/receipt_presentation_v1/v1/fixtures/$name") }
                .first(Files::isRegularFile)
            val raw = Files.readAllBytes(file)
            JsonFactory().createParser(raw).use { parser ->
                check(parser.nextToken() == JsonToken.START_OBJECT)
                while (parser.nextToken() == JsonToken.FIELD_NAME) {
                    val member = parser.currentName()
                    val token = parser.nextToken()
                    if (member == "envelope") {
                        check(token == JsonToken.START_OBJECT)
                        val first = parser.currentTokenLocation().byteOffset.toInt()
                        parser.skipChildren()
                        return raw.copyOfRange(first, parser.currentLocation().byteOffset.toInt())
                    }
                    parser.skipChildren()
                }
            }
            error("Canonical fixture omitted its envelope")
        }
    }

    private companion object {
        fun fixture(name: String, suffix: String) = Fixture(name, "request-$suffix", "image-$suffix")

        val F01 = fixture("01-complete-extracted-receipt.json", "synthetic-complete-001")
        val F03 = fixture("03-missing-required-store-name.json", "synthetic-store-missing-001")
        val F04 = fixture("04-unresolved-purchase-date.json", "synthetic-date-unresolved-001")
        val F05 = fixture("05-decimal-weighted-quantity.json", "synthetic-weighted-001")
        val F06 = fixture("06-processing-unavailable.json", "synthetic-unavailable-001")
        val F07 = fixture("07-processing-failure.json", "synthetic-failure-001")
        val F15 = fixture("15-result-available-extraction-failed.json", "extraction-failed-001")
        val F16 = fixture("16-source-evidence-insufficient.json", "insufficient-completed-001")
    }
}
