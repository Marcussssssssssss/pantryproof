package com.pantryproof.prototype.data

/** A request bound to a retained synthetic input snapshot. */
internal class ReceiptSubmissionBinding private constructor(
    val request: ReceiptProcessingRequest,
    private val snapshot: Snapshot,
) {
    val selection: ReceiptProcessingRequest.Selection get() = snapshot.selection
    val owner: ReceiptProcessingRequest.Owner get() = snapshot.owner
    val imageId: String get() = snapshot.imageId

    fun copyBytes(): ByteArray = snapshot.copyBytes()

    /**
     * The caller owns input until construction returns. All later reads are defensive copies.
     * Release is idempotent and invalidates new bindings and reads through existing bindings.
     * Copies already returned remain caller-owned. Snapshot operations share this monitor.
     */
    class Snapshot(
        val selection: ReceiptProcessingRequest.Selection,
        input: ByteArray,
        maximumBytes: Int,
    ) {
        val owner: ReceiptProcessingRequest.Owner = selection.owner
        val imageId: String = selection.imageId
        private var retainedBytes: ByteArray?

        init {
            require(maximumBytes > 0) { "Maximum input size must be positive." }
            require(input.isNotEmpty()) { "Synthetic input must not be empty." }
            require(input.size <= maximumBytes) { "Synthetic input exceeds the byte limit." }
            retainedBytes = input.copyOf()
        }

        @Synchronized
        fun bind(request: ReceiptProcessingRequest): ReceiptSubmissionBinding {
            checkNotNull(retainedBytes) { "Snapshot has been released." }
            require(request.selection === selection) { "Request selection does not match the snapshot." }
            require(request.context.expectedImageId == imageId) { "Request image does not match the snapshot." }
            return ReceiptSubmissionBinding(request, this)
        }

        @Synchronized
        fun copyBytes(): ByteArray =
            checkNotNull(retainedBytes) { "Snapshot has been released." }.copyOf()

        @Synchronized
        fun release() {
            retainedBytes = null
        }
    }
}
