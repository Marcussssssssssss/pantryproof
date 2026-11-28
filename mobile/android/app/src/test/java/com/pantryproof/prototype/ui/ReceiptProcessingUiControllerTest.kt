package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.AutomaticExtractionStatus
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.Outcome
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.State
import com.pantryproof.prototype.data.SyntheticReceiptProcessingTransport.Scenario
import java.util.ArrayDeque
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

class ReceiptProcessingUiControllerTest {
    private val pantry = PantryUiState(MockReceiptPresentationSource())
    private val inventory = pantry.inventory.toList()
    private val receipt = pantry.receipt
    private val presentation = pantry.presentationResult
    private val confirmation = pantry.demoConfirmed

    @After
    fun processingDoesNotMutatePantry() {
        assertEquals(inventory, pantry.inventory)
        assertSame(receipt, pantry.receipt)
        assertSame(presentation, pantry.presentationResult)
        assertEquals(confirmation, pantry.demoConfirmed)
    }

    @Test
    fun entrySelectsInputWithoutSubmitting() {
        val h = Harness()
        assertSame(State.Idle, h.controller.state)
        h.controller.selectInput()
        assertTrue(h.controller.state is State.Ready)
        assertEquals(1, h.notifications.size)
        assertTrue(h.transport.calls.isEmpty())
        assertTrue(h.worker.isEmpty())
    }

    @Test
    fun startPublishesPendingOnceAndDispatchesOnlyOneSubmission() {
        val h = ready()
        h.controller.start()
        h.controller.start()
        assertTrue(h.controller.state is State.Pending)
        assertEquals(2, h.notifications.size)
        assertTrue(h.transport.calls.isEmpty())
        h.drain()
        assertEquals(1, h.transport.calls.size)
        assertEquals(PresentationConsumerMode.FIXTURE, h.transport.calls.single().request.context.mode)
    }

    @Test
    fun availableBytesPreserveFieldsRowsAndExactWeightedQuantity() {
        val h = ready()
        h.start().complete(Scenario.AVAILABLE)
        h.drain()
        val available = h.result() as ReceiptPresentationUiResult.Available
        assertTrue(available.canReview)
        assertEquals("Synthetic Processing Market", available.receipt.storeName.value)
        assertEquals(listOf("weighted", "second"), available.receipt.items.map { it.rowId })
        assertEquals(listOf("Synthetic apples", "Synthetic rice"), available.receipt.items.map { it.description.value })
        assertEquals("0.750", available.receipt.items.first().quantity.value)
        assertEquals(PresentedFieldStatus.MISSING, available.receipt.items[1].unitPrice.status)
        assertNull(available.receipt.items[1].unitPrice.value)
        assertEquals(PresentedFieldStatus.UNRESOLVED, available.receipt.purchaseDate.status)
        assertNull(available.receipt.purchaseDate.value)
        assertNull(available.receipt.toInventoryCompatibleReceiptOrNull())
    }

    @Test
    fun failedExtractionIsReviewableAndUsesExistingAnnotationPolicy() {
        val h = ready()
        h.start().complete(Scenario.EXTRACTION_FAILED)
        h.drain()
        val available = h.result() as ReceiptPresentationUiResult.Available
        assertEquals(AutomaticExtractionStatus.FAILED, available.receipt.automaticExtractionStatus)
        assertTrue(available.canReview)
        assertTrue(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(available))
        assertTrue(available.receipt.items.isEmpty())
        assertEquals(PresentedFieldStatus.MISSING, available.receipt.storeName.status)
    }

    @Test
    fun validUnavailableFailedAndInsufficientStayDistinct() {
        val unavailable = complete(Scenario.UNAVAILABLE).result()
        val failed = complete(Scenario.PROCESSING_FAILED).result()
        val insufficient = complete(Scenario.INSUFFICIENT).result()
        assertEquals(ReceiptPresentationUiResult.ProcessingUnavailable("PROCESSOR_NOT_AVAILABLE", false), unavailable)
        assertTrue(failed is ReceiptPresentationUiResult.ProcessingFailed)
        assertEquals("OCR_ENGINE_FAILURE", (failed as ReceiptPresentationUiResult.ProcessingFailed).failureCode)
        assertEquals("OCR", failed.stage.name)
        assertEquals(listOf("Synthetic source structure was unavailable."),
            (insufficient as ReceiptPresentationUiResult.InsufficientEvidence).reasons)
        assertTrue(listOf(unavailable, failed, insufficient).none { it.canReview })
    }

    @Test
    fun invalidJsonRetainsItsConsumerRejection() {
        val result = complete(Scenario.INVALID_JSON).result() as ReceiptPresentationUiResult.Rejected
        assertEquals("REJECT_INVALID_JSON", result.issue.code)
        assertFalse(result.canReview)
    }

    @Test
    fun wrongRequestRetainsExactRejectionCodeAndPath() {
        val result = complete(Scenario.WRONG_REQUEST).result() as ReceiptPresentationUiResult.Rejected
        assertEquals("REJECT_REQUEST_ID_MISMATCH", result.issue.code)
        assertEquals("$.requestId", result.issue.path)
    }

    @Test
    fun wrongImageRetainsExactRejectionCodeAndPath() {
        val result = complete(Scenario.WRONG_IMAGE).result() as ReceiptPresentationUiResult.Rejected
        assertEquals("REJECT_IMAGE_ID_MISMATCH", result.issue.code)
        assertEquals("$.imageId", result.issue.path)
    }

    @Test
    fun liveConsumerStillRejectsSyntheticResponses() {
        val h = ready(PresentationConsumerMode.LIVE)
        h.start().complete(Scenario.AVAILABLE)
        h.drain()
        val result = h.result() as ReceiptPresentationUiResult.Rejected
        assertEquals("REJECT_SOURCE_MODE_MISMATCH", result.issue.code)
        assertEquals("$.source.type", result.issue.path)
    }

    @Test
    fun noEnvelopeAndExecutionFailureRemainLocalOutcomes() {
        assertEquals(Outcome.LocalFailure.MISSING_RESPONSE, complete(Scenario.NO_ENVELOPE).finished().outcome)
        assertEquals(Outcome.LocalFailure.EXECUTION_FAILURE, complete(Scenario.EXECUTION_FAILURE).finished().outcome)
    }

    @Test
    fun silenceRemainsPendingUntilDeadlineEquality() {
        val h = ready()
        h.start()
        h.now = 99
        h.fireTimers()
        h.drain()
        assertTrue(h.controller.state is State.Pending)
        h.now = 100
        h.fireTimers()
        h.drain()
        assertEquals(Outcome.LocalFailure.TIMEOUT, h.finished().outcome)
    }

    @Test
    fun deadlineWinsBeforeAdmissionEvenAfterWorkerValidation() {
        val h = ready()
        val call = h.start()
        h.now = 99
        call.complete(Scenario.AVAILABLE)
        h.worker.drain()
        assertTrue(h.controller.state is State.Pending)
        h.now = 100
        h.ui.drain()
        assertEquals(Outcome.LocalFailure.TIMEOUT, h.finished().outcome)
    }

    @Test
    fun admittedResultWinsOverALaterTimer() {
        val h = complete(Scenario.AVAILABLE)
        val admitted = h.finished()
        val notifications = h.notifications.size
        h.now = 100
        h.fireTimers()
        h.drain()
        assertSame(admitted, h.finished())
        assertEquals(notifications, h.notifications.size)
    }

    @Test
    fun cancelPublishesReadyImmediatelyAndSuppressesLateResult() {
        val h = ready()
        val call = h.start()
        h.controller.cancel()
        val ready = h.controller.state
        val notifications = h.notifications.size
        assertTrue(ready is State.Ready)
        call.complete(Scenario.AVAILABLE)
        h.drain()
        assertSame(ready, h.controller.state)
        assertEquals(notifications, h.notifications.size)
        assertEquals(1, call.cancellations)
    }

    @Test
    fun reselectionAfterValidWorkerCompletionSuppressesOldUiDelivery() {
        val h = ready()
        val old = h.start()
        old.complete(Scenario.AVAILABLE)
        h.worker.drain()
        h.controller.selectInput()
        val ready = h.controller.state as State.Ready
        h.ui.drain()
        assertSame(ready, h.controller.state)
        assertNotSame(old.request.selection, ready.selection)
        val next = h.start()
        next.complete(Scenario.EXTRACTION_FAILED)
        old.complete(Scenario.AVAILABLE)
        h.drain()
        assertSame(next.request, h.finished().request)
    }

    @Test
    fun duplicateCallbacksDoNotRepeatTerminalNotifications() {
        val h = ready()
        val call = h.start()
        call.complete(Scenario.AVAILABLE)
        h.drain()
        val result = h.finished()
        val notifications = h.notifications.size
        call.complete(Scenario.PROCESSING_FAILED)
        call.complete(Scenario.AVAILABLE)
        h.drain()
        assertSame(result, h.finished())
        assertEquals(notifications, h.notifications.size)
    }

    @Test
    fun disposeSuppressesLateCallbacksAndTimerNotifications() {
        val h = ready()
        val call = h.start()
        val notifications = h.notifications.size
        h.controller.dispose()
        h.controller.dispose()
        call.complete(Scenario.AVAILABLE)
        h.now = 100
        h.fireTimers()
        h.drain()
        assertSame(State.Idle, h.controller.state)
        assertEquals(notifications, h.notifications.size)
    }

    @Test
    fun disposeBeforeQueuedStartupSkipsSubmission() {
        val h = ready()
        h.controller.start()
        h.controller.dispose()
        h.drain()
        assertTrue(h.transport.calls.isEmpty())
    }

    @Test
    fun disposeAfterWorkerCompletionSkipsQueuedUiNotification() {
        val h = ready()
        h.start().complete(Scenario.AVAILABLE)
        h.worker.drain()
        val notifications = h.notifications.size
        h.controller.dispose()
        h.ui.drain()
        assertEquals(notifications, h.notifications.size)
    }

    @Test
    fun newInputAndStartRequireExplicitActionsAndFreshIdentities() {
        val h = complete(Scenario.AVAILABLE)
        val first = h.finished().request
        h.controller.start()
        assertEquals(1, h.transport.calls.size)
        h.controller.selectInput()
        assertTrue(h.controller.state is State.Ready)
        assertEquals(1, h.transport.calls.size)
        val next = h.start().request
        assertNotSame(first.selection, next.selection)
        assertNotSame(first.submission, next.submission)
        assertNotEquals(first.context.expectedRequestId, next.context.expectedRequestId)
        assertNotEquals(first.context.expectedImageId, next.context.expectedImageId)
    }

    @Test
    fun clearingSelectionPublishesIdleAndDisablesSubmission() {
        val h = ready()
        h.controller.clearSelection()
        h.controller.start()
        h.drain()
        assertSame(State.Idle, h.controller.state)
        assertTrue(h.transport.calls.isEmpty())
    }

    @Test
    fun thrownTransportExceptionBecomesLocalExecutionFailure() {
        val h = Harness(throws = true)
        h.controller.selectInput()
        h.controller.start()
        h.drain()
        assertEquals(Outcome.LocalFailure.EXECUTION_FAILURE, h.finished().outcome)
    }

    @Test
    fun workerAndUiAreReleasedIndependently() {
        val h = ready()
        h.controller.start()
        h.worker.drain()
        assertTrue(h.transport.calls.isEmpty())
        assertTrue(h.ui.isNotEmpty())
        assertEquals(2, h.notifications.size)
        h.ui.drain()
        assertTrue(h.transport.calls.isEmpty())
        h.worker.drain()
        assertEquals(1, h.transport.calls.size)
    }

    @Test
    fun syntheticTransportCapturesScenarioBeforeDelayedDelivery() {
        val h = ready()
        val request = h.start().request
        var selected = Scenario.UNAVAILABLE
        val responses = Queue()
        var delivered: ReceiptProcessingDelivery? = null
        val fake = SyntheticReceiptProcessingTransport({ selected }, responses::post)
        fake.submit(request) { delivered = it }
        selected = Scenario.AVAILABLE
        assertNull(delivered)
        responses.drain()
        val bytes = (delivered as ReceiptProcessingDelivery.Envelope).takeBytes()
        assertEquals(ReceiptPresentationUiResult.ProcessingUnavailable("PROCESSOR_NOT_AVAILABLE", false),
            M3eReceiptPresentationAdapter().decodeAndMap(bytes, request.context))
    }

    @Test
    fun syntheticTransportCancellationSuppressesItsDelayedDelivery() {
        val h = ready()
        val request = h.start().request
        val responses = Queue()
        var deliveries = 0
        val fake = SyntheticReceiptProcessingTransport({ Scenario.AVAILABLE }, responses::post)
        fake.submit(request) { deliveries++ }.cancel()
        responses.drain()
        assertEquals(0, deliveries)
    }

    private fun ready(mode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE) =
        Harness(mode = mode).also { it.controller.selectInput() }

    private fun complete(scenario: Scenario) = ready().also {
        it.start().complete(scenario)
        it.drain()
    }

    private class Queue {
        private val tasks = ArrayDeque<() -> Unit>()
        fun post(action: () -> Unit) { tasks.addLast(action) }
        fun isEmpty() = tasks.isEmpty()
        fun isNotEmpty() = tasks.isNotEmpty()
        fun drain() { while (tasks.isNotEmpty()) tasks.removeFirst()() }
    }

    private class Call(val request: ReceiptProcessingRequest, val callback: (ReceiptProcessingDelivery) -> Unit) {
        var cancellations = 0
        fun complete(scenario: Scenario) {
            SyntheticReceiptProcessingTransport({ scenario }, { it() }).submit(request, callback)
        }
    }

    private class ScriptedTransport(private val throws: Boolean) : ReceiptProcessingTransport {
        val calls = mutableListOf<Call>()
        override fun submit(request: ReceiptProcessingRequest, deliver: (ReceiptProcessingDelivery) -> Unit): ReceiptProcessingTransport.Cancellation {
            if (throws) throw IllegalStateException("Synthetic transport exception")
            val call = Call(request, deliver)
            calls.add(call)
            return ReceiptProcessingTransport.Cancellation { call.cancellations++ }
        }
    }

    private class Harness(mode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE, throws: Boolean = false) {
        val worker = Queue()
        val ui = Queue()
        var now = 0L
        private var image = 0
        private var request = 0
        private val timers = mutableListOf<Pair<Long, () -> Unit>>()
        val notifications = mutableListOf<State>()
        val transport = ScriptedTransport(throws)
        val controller = ReceiptProcessingUiController(
            transport, worker::post, ui::post,
            { delay, action -> timers.add(now + delay to action) }, { now }, 100L,
            { "image-ui-test-" + ++image }, { "request-ui-test-" + ++request }, notifications::add, mode,
        )
        fun drain() {
            while (worker.isNotEmpty() || ui.isNotEmpty()) {
                worker.drain()
                ui.drain()
            }
        }
        fun start(): Call {
            controller.start()
            drain()
            return transport.calls.last()
        }
        fun fireTimers() {
            val due = timers.filter { it.first <= now }
            timers.removeAll(due.toSet())
            due.forEach { it.second() }
        }
        fun finished() = controller.state as State.Finished
        fun result() = (finished().outcome as Outcome.Presentation).result
    }
}
