package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.ReceiptPresentationRequestCoordinator.Attempt
import com.pantryproof.prototype.data.ReceiptProcessingRequest.Selection

/**
 * Unwired receipt lifecycle. Public events and state reads belong to the serialized UI owner.
 * Dispatchers enqueue work: the worker is serial and separate from the UI thread. The timer
 * uses the same monotonic time base as [nowMillis] and only enqueues UI work.
 */
internal class ReceiptProcessingLifecycle(
    private val transport: ReceiptProcessingTransport,
    private val postWorker: (() -> Unit) -> Unit,
    private val postUi: (() -> Unit) -> Unit,
    private val schedule: (Long, () -> Unit) -> Unit,
    private val nowMillis: () -> Long,
    private val timeoutMillis: Long,
    private val newImageId: () -> String,
    private val newRequestId: () -> String,
    private val coordinator: ReceiptPresentationRequestCoordinator = ReceiptPresentationRequestCoordinator(),
    private val completeAttempt: (Attempt, ByteArray) -> ReceiptPresentationUiResult? = coordinator::complete,
) {
    sealed interface State {
        data object Idle : State
        data class Ready(val selection: Selection) : State
        data class Pending(val request: ReceiptProcessingRequest) : State
        data class Finished(val request: ReceiptProcessingRequest, val outcome: Outcome) : State
    }

    sealed interface Outcome {
        data class Presentation(val result: ReceiptPresentationUiResult) : Outcome {
            val reviewTitle: String?
                get() = if (result is ReceiptPresentationUiResult.Available) "Review receipt fields" else null
        }

        enum class LocalFailure : Outcome {
            MISSING_RESPONSE,
            TIMEOUT,
            EXECUTION_FAILURE,
        }
    }

    private class Submission(
        val request: ReceiptProcessingRequest,
        val startedAtMillis: Long,
    ) {
        // Worker-owned. Only the serial worker can read or change these fields.
        var workerAttempt: Attempt? = null
        var cancellation: ReceiptProcessingTransport.Cancellation? = null
        var terminalClaimed = false
    }

    private val owner = ReceiptProcessingRequest.Owner()
    private var selection: Selection? = null
    private var boundAttempt: Attempt? = null
    private var disposed = false

    @Volatile
    private var active: Submission? = null

    var state: State = State.Idle
        private set

    init {
        require(timeoutMillis > 0)
    }

    /** Call for an accepted selection or a change to submitted input, including reselection. */
    fun selectInput() {
        check(!disposed)
        invalidate()
        val selected = Selection(owner, newImageId())
        selection = selected
        state = State.Ready(selected)
    }

    fun clearSelection() {
        invalidate()
        selection = null
        state = State.Idle
    }

    fun dispose() {
        disposed = true
        clearSelection()
    }

    fun submit(mode: PresentationConsumerMode) {
        val selected = checkNotNull(selection)
        check(!disposed)
        invalidate()
        val context = PresentationConsumerContext(newRequestId(), selected.imageId, mode)
        val request = ReceiptProcessingRequest(selected, ReceiptProcessingRequest.Submission(), context)
        val submission = Submission(request, nowMillis())
        active = submission
        state = State.Pending(request)
        schedule(timeoutMillis) {
            postUi {
                if (isCurrent(submission) && expired(submission)) finishTimeout(submission)
            }
        }
        postWorker { beginOnWorker(submission) }
    }

    fun cancel() {
        if (active == null) return
        invalidate()
        state = State.Ready(checkNotNull(selection))
    }

    private fun invalidate() {
        val previous = active
        active = null
        boundAttempt = null
        if (previous != null) postWorker { cancelOnWorker(previous) }
    }

    private fun beginOnWorker(submission: Submission) {
        if (active !== submission) return
        val attempt = try {
            coordinator.begin(submission.request.context)
        } catch (_: RuntimeException) {
            deliverOnUi(submission, null, Outcome.LocalFailure.EXECUTION_FAILURE)
            return
        }
        submission.workerAttempt = attempt
        if (active !== submission) {
            cancelOnWorker(submission)
            return
        }
        postUi {
            if (isCurrent(submission)) {
                if (expired(submission)) {
                    finishTimeout(submission)
                } else {
                    boundAttempt = attempt
                    postWorker { submitOnWorker(submission, attempt) }
                }
            }
        }
    }

    private fun submitOnWorker(submission: Submission, attempt: Attempt) {
        if (active !== submission) return
        try {
            submission.cancellation = transport.submit(submission.request) { delivery ->
                postWorker { receiveOnWorker(submission, attempt, delivery) }
            }
        } catch (_: RuntimeException) {
            // Keep queue order even if the transport called back synchronously before throwing.
            postWorker { receiveOnWorker(submission, attempt, ReceiptProcessingDelivery.ExecutionFailure) }
        }
    }

    private fun receiveOnWorker(
        submission: Submission,
        attempt: Attempt,
        delivery: ReceiptProcessingDelivery,
    ) {
        if (active !== submission || submission.workerAttempt !== attempt || submission.terminalClaimed) return
        submission.terminalClaimed = true
        submission.cancellation = null
        val outcome = try {
            when (delivery) {
                is ReceiptProcessingDelivery.Envelope -> {
                    val result = completeAttempt(attempt, delivery.takeBytes()) ?: return
                    Outcome.Presentation(result)
                }
                ReceiptProcessingDelivery.NoEnvelope -> {
                    coordinator.cancel(attempt)
                    Outcome.LocalFailure.MISSING_RESPONSE
                }
                ReceiptProcessingDelivery.ExecutionFailure -> {
                    coordinator.cancel(attempt)
                    Outcome.LocalFailure.EXECUTION_FAILURE
                }
            }
        } catch (_: RuntimeException) {
            coordinator.cancel(attempt)
            Outcome.LocalFailure.EXECUTION_FAILURE
        }
        deliverOnUi(submission, attempt, outcome)
    }

    private fun cancelOnWorker(submission: Submission) {
        submission.workerAttempt?.let(coordinator::cancel)
        val cancellation = submission.cancellation
        submission.cancellation = null
        try {
            cancellation?.cancel()
        } catch (_: RuntimeException) {
            // The UI already invalidated this submission. Cancellation is best effort.
        }
    }

    private fun deliverOnUi(submission: Submission, attempt: Attempt?, outcome: Outcome) {
        postUi {
            if (isCurrent(submission) && boundAttempt === attempt) {
                if (expired(submission)) {
                    finishTimeout(submission)
                } else {
                    active = null
                    boundAttempt = null
                    state = State.Finished(submission.request, outcome)
                }
            }
        }
    }

    private fun isCurrent(submission: Submission): Boolean =
        !disposed && active === submission && selection === submission.request.selection &&
            submission.request.selection.owner === owner

    private fun expired(submission: Submission): Boolean =
        nowMillis() - submission.startedAtMillis >= timeoutMillis

    private fun finishTimeout(submission: Submission) {
        invalidate()
        state = State.Finished(submission.request, Outcome.LocalFailure.TIMEOUT)
    }
}
