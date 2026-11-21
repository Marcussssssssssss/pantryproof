package com.pantryproof.prototype.data

/** In-memory image-binding proof. The fictional response never examines image content. */
internal class BoundSyntheticReceiptProcessingTransport(
    scenario: () -> SyntheticReceiptProcessingTransport.Scenario,
    dispatchResponse: (() -> Unit) -> Unit,
) : ReceiptProcessingTransport {
    private val synthetic = SyntheticReceiptProcessingTransport(scenario, dispatchResponse)
    private var snapshot: ReceiptSubmissionBinding.Snapshot? = null

    @Synchronized
    fun replaceSnapshot(next: ReceiptSubmissionBinding.Snapshot?) {
        if (snapshot !== next) snapshot?.release()
        snapshot = next
    }

    override fun submit(
        request: ReceiptProcessingRequest,
        deliver: (ReceiptProcessingDelivery) -> Unit,
    ): ReceiptProcessingTransport.Cancellation {
        val bound = synchronized(this) {
            try {
                val binding = checkNotNull(snapshot).bind(request)
                // Prove the submitted input is readable through the exact O07 binding.
                // This temporary defensive copy is not sent anywhere or retained.
                check(binding.copyBytes().isNotEmpty())
                binding.request === request && binding.selection === request.selection
            } catch (_: RuntimeException) {
                false
            }
        }
        if (!bound) {
            deliver(ReceiptProcessingDelivery.ExecutionFailure)
            return ReceiptProcessingTransport.Cancellation {}
        }
        return synthetic.submit(request, deliver)
    }
}
