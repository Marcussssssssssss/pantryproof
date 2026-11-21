package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.BoundSyntheticReceiptProcessingTransport
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptSubmissionBinding

/** Serialized UI owner. Image preparation is a local prerequisite, not an I2C outcome. */
internal class SelectedImageProcessingController(
    private val transport: BoundSyntheticReceiptProcessingTransport,
    private val postWorker: (() -> Unit) -> Unit,
    private val postUi: (() -> Unit) -> Unit,
    schedule: (Long, () -> Unit) -> Unit,
    nowMillis: () -> Long,
    timeoutMillis: Long,
    newImageId: () -> String,
    newRequestId: () -> String,
    private val maximumBytes: Int,
    private val onChanged: () -> Unit,
) {
    enum class InputState { EMPTY, PREPARING, READY, ERROR }

    private var disposed = false
    @Volatile private var generation = Any()
    var inputState = InputState.EMPTY
        private set
    private val processing = ReceiptProcessingUiController(
        transport, postWorker, postUi, schedule, nowMillis, timeoutMillis,
        newImageId, newRequestId, onStateChanged = { publish() },
    )
    val state: ReceiptProcessingLifecycle.State get() = processing.state

    init { require(maximumBytes > 0) }

    /** Replacing a URI, crop, or prepared input always invalidates the previous selection. */
    fun prepareInput(encode: () -> ByteArray) {
        check(!disposed)
        val token = Any().also { generation = it }
        processing.clearSelection()
        transport.replaceSnapshot(null)
        inputState = InputState.PREPARING
        processing.selectInput()
        val selection = (state as ReceiptProcessingLifecycle.State.Ready).selection
        postWorker {
            if (generation !== token) return@postWorker
            val snapshot = try {
                ReceiptSubmissionBinding.Snapshot(selection, encode(), maximumBytes)
            } catch (_: Exception) {
                null
            }
            // Never remove this queued callback on disposal: it releases a stale snapshot.
            postUi {
                if (disposed || generation !== token ||
                    (state as? ReceiptProcessingLifecycle.State.Ready)?.selection !== selection
                ) {
                    snapshot?.release()
                } else if (snapshot == null) {
                    inputState = InputState.ERROR
                    processing.clearSelection()
                } else {
                    transport.replaceSnapshot(snapshot)
                    inputState = InputState.READY
                    publish()
                }
            }
        }
        publish()
    }

    fun start() {
        if (!disposed && inputState == InputState.READY) processing.start()
    }

    fun cancel() {
        if (!disposed) processing.cancel()
    }

    fun dispose() {
        if (disposed) return
        disposed = true
        generation = Any()
        processing.dispose()
        transport.replaceSnapshot(null)
        inputState = InputState.EMPTY
    }

    private fun publish() { if (!disposed) onChanged() }
}
