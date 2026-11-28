package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingTransport

/** UI-owned observer around I2C. Both dispatchers must enqueue, and the worker must be serial. */
internal class ReceiptProcessingUiController(
    transport: ReceiptProcessingTransport,
    postWorker: (() -> Unit) -> Unit,
    postUi: (() -> Unit) -> Unit,
    schedule: (Long, () -> Unit) -> Unit,
    nowMillis: () -> Long,
    timeoutMillis: Long,
    newImageId: () -> String,
    newRequestId: () -> String,
    private val onStateChanged: (ReceiptProcessingLifecycle.State) -> Unit,
    private val consumerMode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE,
) {
    private var disposed = false
    private var published: ReceiptProcessingLifecycle.State? = null
    private val lifecycle = ReceiptProcessingLifecycle(
        transport = transport,
        postWorker = postWorker,
        postUi = { action ->
            postUi {
                if (!disposed) {
                    action()
                    publish()
                }
            }
        },
        schedule = schedule,
        nowMillis = nowMillis,
        timeoutMillis = timeoutMillis,
        newImageId = newImageId,
        newRequestId = newRequestId,
    )

    val state: ReceiptProcessingLifecycle.State get() = lifecycle.state

    fun selectInput() {
        check(!disposed)
        lifecycle.selectInput()
        publish()
    }

    fun start() {
        check(!disposed)
        if (state !is ReceiptProcessingLifecycle.State.Ready) return
        lifecycle.submit(consumerMode)
        publish()
    }

    fun cancel() {
        if (disposed) return
        lifecycle.cancel()
        publish()
    }

    fun clearSelection() {
        check(!disposed)
        lifecycle.clearSelection()
        publish()
    }

    fun dispose() {
        if (disposed) return
        disposed = true
        lifecycle.dispose()
    }

    private fun publish() {
        if (published !== state) {
            published = state
            onStateChanged(state)
        }
    }
}
