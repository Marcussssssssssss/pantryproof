package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.State
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.Outcome
import java.util.ArrayDeque
import org.junit.Assert.*
import org.junit.Test

class SelectedImageProcessingControllerTest {
    private class Queue {
        val tasks = ArrayDeque<() -> Unit>()
        fun post(action: () -> Unit) { tasks.addLast(action) }
        fun drain() { while (tasks.isNotEmpty()) tasks.removeFirst()() }
    }
    private class Harness {
        val worker = Queue(); val ui = Queue(); val response = Queue(); val timers = Queue()
        var time = 0L; var ids = 0; var submissions = 0; var notifications = 0
        var scenario = SyntheticReceiptProcessingTransport.Scenario.AVAILABLE
        val transport = BoundSyntheticReceiptProcessingTransport({ submissions++; scenario }, response::post)
        val controller = SelectedImageProcessingController(
            transport, worker::post, ui::post, { _, task -> timers.post(task) }, { time }, 100L,
            { "image-${++ids}" }, { "request-${++ids}" }, 16, { notifications++ },
        )
        fun drain() { while (worker.tasks.isNotEmpty() || ui.tasks.isNotEmpty()) { worker.drain(); ui.drain() } }
        fun ready() { controller.prepareInput { byteArrayOf(1, 2, 3) }; drain() }
        fun start() { controller.start(); drain() }
        fun finish() { response.drain(); drain() }
        fun snapshot() = BoundSyntheticReceiptProcessingTransport::class.java.getDeclaredField("snapshot")
            .apply { isAccessible = true }.get(transport) as ReceiptSubmissionBinding.Snapshot
    }

    @Test fun preparationRunsOnWorkerAndNeverAutomaticallySubmits() {
        val h = Harness(); var read = false
        h.controller.prepareInput { read = true; byteArrayOf(1) }
        assertFalse(read); assertEquals(SelectedImageProcessingController.InputState.PREPARING, h.controller.inputState)
        h.controller.start(); assertEquals(0, h.submissions)
        h.worker.drain(); assertTrue(read)
        assertEquals(SelectedImageProcessingController.InputState.PREPARING, h.controller.inputState)
        h.ui.drain(); assertEquals(SelectedImageProcessingController.InputState.READY, h.controller.inputState)
        assertEquals(0, h.submissions)
    }

    @Test fun readySelectionIsTheExactSnapshotSelectionAndOwner() {
        val h = Harness(); h.ready()
        val selection = (h.controller.state as State.Ready).selection
        assertSame(selection, h.snapshot().selection); assertSame(selection.owner, h.snapshot().owner)
    }

    @Test fun inputMutationAndReturnedCopyDoNotChangeBoundBytes() {
        val h = Harness(); val source = byteArrayOf(1, 2, 3)
        h.controller.prepareInput { source }; h.drain(); source[0] = 99
        val copy = h.snapshot().copyBytes(); copy[1] = 99
        assertArrayEquals(byteArrayOf(1, 2, 3), h.snapshot().copyBytes())
    }

    @Test fun explicitStartOnceReachesValidatedAvailableWithOriginalWeightedFields() {
        val h = Harness(); h.ready(); h.controller.start(); h.controller.start(); h.drain()
        assertEquals(1, h.submissions); assertTrue(h.controller.state is State.Pending)
        h.finish()
        val result = ((h.controller.state as State.Finished).outcome as Outcome.Presentation).result as ReceiptPresentationUiResult.Available
        assertEquals("0.750", result.receipt.items.first().quantity.value)
        assertEquals(listOf("weighted", "second"), result.receipt.items.map { it.rowId })
    }

    @Test fun emptyInputIsLocalPreparationErrorWithNoI2cSubmission() {
        val h = Harness(); h.controller.prepareInput { byteArrayOf() }; h.drain(); h.controller.start(); h.drain()
        assertEquals(SelectedImageProcessingController.InputState.ERROR, h.controller.inputState)
        assertSame(State.Idle, h.controller.state); assertEquals(0, h.submissions)
    }

    @Test fun oversizedInputIsLocalPreparationError() {
        val h = Harness(); h.controller.prepareInput { ByteArray(17) }; h.drain()
        assertEquals(SelectedImageProcessingController.InputState.ERROR, h.controller.inputState)
        assertEquals(0, h.submissions)
    }

    @Test fun unreadableInputDoesNotFabricatePresentationOrExecutionOutcome() {
        val h = Harness(); h.controller.prepareInput { error("fictional read failure") }; h.drain()
        assertSame(State.Idle, h.controller.state)
        assertEquals(SelectedImageProcessingController.InputState.ERROR, h.controller.inputState)
        assertEquals(0, h.submissions)
    }

    @Test fun cancellationReturnsReadyAndLateResponseCannotFinish() {
        val h = Harness(); h.ready(); val snapshot = h.snapshot(); h.start(); h.controller.cancel()
        assertTrue(h.controller.state is State.Ready); h.finish()
        assertTrue(h.controller.state is State.Ready); assertSame(snapshot, h.snapshot())
    }

    @Test fun retryAfterCancelKeepsSnapshotButUsesFreshRequestAndSubmission() {
        val h = Harness(); h.ready(); h.start(); val first = (h.controller.state as State.Pending).request
        h.controller.cancel(); h.start(); val second = (h.controller.state as State.Pending).request
        assertSame(first.selection, second.selection); assertNotSame(first.submission, second.submission)
        assertNotEquals(first.context.expectedRequestId, second.context.expectedRequestId)
        h.finish(); assertTrue(h.controller.state is State.Finished)
    }

    @Test fun deadlineEqualityTimesOutAndLateResponseIsDiscarded() {
        val h = Harness(); h.ready(); h.start(); h.time = 100; h.timers.drain(); h.ui.drain()
        assertSame(Outcome.LocalFailure.TIMEOUT, (h.controller.state as State.Finished).outcome)
        h.finish(); assertSame(Outcome.LocalFailure.TIMEOUT, (h.controller.state as State.Finished).outcome)
    }

    @Test fun deadlineBeforeUiAdmissionBeatsWorkerComputedResponse() {
        val h = Harness(); h.ready(); h.start(); h.response.drain(); h.worker.drain(); h.time = 100; h.ui.drain()
        assertSame(Outcome.LocalFailure.TIMEOUT, (h.controller.state as State.Finished).outcome)
    }

    @Test fun cropReplacementReleasesOldSnapshotAndRejectsOldCompletion() {
        val h = Harness(); h.ready(); val old = h.snapshot(); h.start()
        val request = (h.controller.state as State.Pending).request
        h.controller.prepareInput { byteArrayOf(4, 5, 6) }
        assertThrows(IllegalStateException::class.java) { old.copyBytes() }
        h.finish(); h.drain()
        val next = (h.controller.state as State.Ready).selection
        assertNotSame(request.selection, next); assertArrayEquals(byteArrayOf(4, 5, 6), h.snapshot().copyBytes())
    }

    @Test fun olderPreparationUiCallbackCannotReplaceNewSnapshot() {
        val h = Harness(); h.controller.prepareInput { byteArrayOf(1) }; h.worker.drain()
        h.controller.prepareInput { byteArrayOf(2) }; h.worker.drain(); h.ui.drain()
        assertArrayEquals(byteArrayOf(2), h.snapshot().copyBytes())
        assertSame((h.controller.state as State.Ready).selection, h.snapshot().selection)
    }

    @Test fun disposeReleasesSnapshotAndSuppressesWorkerAndUiNotifications() {
        val h = Harness(); h.ready(); val old = h.snapshot(); h.start(); val count = h.notifications
        h.controller.dispose(); h.finish(); h.timers.drain(); h.drain()
        assertThrows(IllegalStateException::class.java) { old.copyBytes() }; assertEquals(count, h.notifications)
        assertSame(State.Idle, h.controller.state)
    }

    @Test fun disposeDuringPreparationNeverInstallsOrSubmits() {
        val h = Harness(); h.controller.prepareInput { byteArrayOf(1) }; h.worker.drain()
        h.controller.dispose(); h.ui.drain(); h.controller.start()
        assertSame(State.Idle, h.controller.state); assertEquals(0, h.submissions)
    }

    @Test fun reselectionAfterCompletedResultRequiresPreparationAndExplicitStart() {
        val h = Harness(); h.ready(); h.start(); val first = (h.controller.state as State.Pending).request
        h.finish(); h.controller.start(); assertEquals(1, h.submissions)
        h.ready(); assertEquals(1, h.submissions); h.start()
        val second = (h.controller.state as State.Pending).request
        assertNotSame(first.selection, second.selection); assertNotSame(first.submission, second.submission)
        assertNotEquals(first.context.expectedRequestId, second.context.expectedRequestId)
    }

    @Test fun localDeliveryFailuresRemainDistinctFromPreparationErrors() {
        val h = Harness(); h.scenario = SyntheticReceiptProcessingTransport.Scenario.NO_ENVELOPE
        h.ready(); h.start(); h.finish()
        assertSame(Outcome.LocalFailure.MISSING_RESPONSE, (h.controller.state as State.Finished).outcome)
        assertEquals(SelectedImageProcessingController.InputState.READY, h.controller.inputState)
    }
}
