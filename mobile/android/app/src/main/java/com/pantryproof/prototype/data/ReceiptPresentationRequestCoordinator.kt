package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext

/**
 * Coordinates one pending presentation request. State transitions and validation are
 * serialized on this instance. Callers should complete requests off the UI thread.
 */
internal class ReceiptPresentationRequestCoordinator {
    /** Identity belongs to this attempt, even when a retry uses the same context. */
    class Attempt internal constructor()

    private data class Pending(
        val attempt: Attempt,
        val context: PresentationConsumerContext,
    )

    private val adapter = M3eReceiptPresentationAdapter()
    private var pending: Pending? = null

    @Synchronized
    fun begin(context: PresentationConsumerContext): Attempt {
        val attempt = Attempt()
        pending = Pending(attempt, context)
        return attempt
    }

    @Synchronized
    fun cancel(attempt: Attempt) {
        if (pending?.attempt === attempt) pending = null
    }

    /** Returns a typed terminal result once, or null if this attempt is no longer active. */
    @Synchronized
    fun complete(attempt: Attempt, payload: ByteArray): ReceiptPresentationUiResult? {
        val current = pending ?: return null
        if (current.attempt !== attempt) return null
        pending = null
        return adapter.decodeAndMap(payload, current.context)
    }
}
