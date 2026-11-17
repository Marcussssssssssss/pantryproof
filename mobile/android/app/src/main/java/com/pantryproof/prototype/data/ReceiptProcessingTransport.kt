package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext

/** In-process descriptor. The selection and submission tokens use reference identity. */
internal data class ReceiptProcessingRequest(
    val selection: Selection,
    val submission: Submission,
    val context: PresentationConsumerContext,
) {
    class Owner
    class Selection(val owner: Owner, val imageId: String)
    class Submission
}

internal sealed interface ReceiptProcessingDelivery {
    /** Snapshot the producer's bytes at handoff, before a worker can be delayed. */
    class Envelope(producerBuffer: ByteArray) : ReceiptProcessingDelivery {
        private var snapshot: ByteArray? = producerBuffer.copyOf()

        @Synchronized
        fun takeBytes(): ByteArray = checkNotNull(snapshot).also { snapshot = null }
    }

    data object NoEnvelope : ReceiptProcessingDelivery
    data object ExecutionFailure : ReceiptProcessingDelivery
}

/** Android-local test boundary. Callbacks may be delayed or delivered after cancellation. */
internal fun interface ReceiptProcessingTransport {
    fun submit(
        request: ReceiptProcessingRequest,
        deliver: (ReceiptProcessingDelivery) -> Unit,
    ): Cancellation

    fun interface Cancellation {
        fun cancel()
    }
}
