package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.BoundSyntheticReceiptProcessingTransport
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.ReceiptProcessingTransport
import com.pantryproof.prototype.data.ReceiptSubmissionBinding
import com.pantryproof.prototype.data.T09HttpTransport
import java.util.WeakHashMap

/** Serialized UI owner. Image preparation is a local prerequisite, not an I2C outcome. */
internal class SelectedImageProcessingController private constructor(
    transport: ReceiptProcessingTransport,
    private val replaceSnapshot: (ReceiptSubmissionBinding.Snapshot?) -> Boolean,
    private val fixture: FixtureBinding?,
    private val postWorker: (() -> Unit) -> Unit,
    private val postUi: (() -> Unit) -> Unit,
    private val schedule: (Long, () -> Unit) -> Unit,
    nowMillis: () -> Long,
    timeoutMillis: Long,
    newImageId: () -> String,
    newRequestId: () -> String,
    private val maximumBytes: Int,
    private val onChanged: () -> Unit,
    private val consumerMode: PresentationConsumerMode = PresentationConsumerMode.FIXTURE,
) {
    constructor(
        transport: BoundSyntheticReceiptProcessingTransport,
        postWorker: (() -> Unit) -> Unit,
        postUi: (() -> Unit) -> Unit,
        schedule: (Long, () -> Unit) -> Unit,
        nowMillis: () -> Long,
        timeoutMillis: Long,
        newImageId: () -> String,
        newRequestId: () -> String,
        maximumBytes: Int,
        onChanged: () -> Unit,
    ) : this(
        transport = transport,
        replaceSnapshot = { snapshot ->
            transport.replaceSnapshot(snapshot)
            true
        },
        fixture = null,
        postWorker = postWorker,
        postUi = postUi,
        schedule = schedule,
        nowMillis = nowMillis,
        timeoutMillis = timeoutMillis,
        newImageId = newImageId,
        newRequestId = newRequestId,
        maximumBytes = maximumBytes,
        onChanged = onChanged,
    )

    constructor(
        fixture: FixtureBinding,
        postWorker: (() -> Unit) -> Unit,
        postUi: (() -> Unit) -> Unit,
        schedule: (Long, () -> Unit) -> Unit,
        onChanged: () -> Unit,
    ) : this(
        transport = fixture.transport,
        replaceSnapshot = fixture.replaceSnapshot,
        fixture = fixture,
        postWorker = postWorker,
        postUi = postUi,
        schedule = schedule,
        nowMillis = fixture.start::nowMillis,
        timeoutMillis = FixtureStart.TIMEOUT_MILLIS,
        newImageId = { fixture.start.context.expectedImageId },
        newRequestId = { fixture.start.context.expectedRequestId },
        maximumBytes = fixture.maximumBytes,
        onChanged = onChanged,
    )

    constructor(
        transport: T09HttpTransport,
        postWorker: (() -> Unit) -> Unit,
        postUi: (() -> Unit) -> Unit,
        schedule: (Long, () -> Unit) -> Unit,
        nowMillis: () -> Long,
        newImageId: () -> String,
        newRequestId: () -> String,
        onChanged: () -> Unit,
    ) : this(
        transport = transport,
        replaceSnapshot = { snapshot ->
            check(snapshot == null)
            transport.close()
            true
        },
        fixture = null,
        postWorker = postWorker,
        postUi = postUi,
        schedule = schedule,
        nowMillis = nowMillis,
        timeoutMillis = T09HttpTransport.TOTAL_MS,
        newImageId = newImageId,
        newRequestId = newRequestId,
        maximumBytes = T09HttpTransport.MAX_PNG_BYTES,
        onChanged = onChanged,
        consumerMode = PresentationConsumerMode.LIVE,
    )

    /** A test owner supplies the transport and the snapshot handler from the same holder. */
    internal class FixtureBinding(
        val transport: ReceiptProcessingTransport,
        val replaceSnapshot: (ReceiptSubmissionBinding.Snapshot?) -> Boolean,
        val start: FixtureStart,
        val maximumBytes: Int,
        val preparedInput: () -> ByteArray,
        private val retire: () -> Unit,
        private val release: () -> Unit,
    ) {
        private var detached = false
        var closed = false
            private set

        // Retiring the sender keeps the ticket available for a later Activity reset.
        fun close() {
            if (closed) return
            closed = true
            start.revoke()
            retire()
        }

        fun detach() {
            if (detached) return
            detached = true
            try {
                close()
            } finally {
                forgetFixture(this)
                release()
            }
        }
    }

    /** Captured on the UI owner. Only the immutable published record is read by workers. */
    internal class FixtureStart(
        val context: PresentationConsumerContext,
        private val generation: Any,
        val elapsedMillis: () -> Long,
    ) {
        private class Record(
            val request: ReceiptProcessingRequest,
            val selection: ReceiptProcessingRequest.Selection,
            val owner: ReceiptProcessingRequest.Owner,
            val submission: ReceiptProcessingRequest.Submission,
            val generation: Any,
            val start: Long,
        )

        private var armedSelection: ReceiptProcessingRequest.Selection? = null
        private var capturedStart: Long? = null
        private var used = false
        @Volatile private var record: Record? = null

        fun canArm(selection: ReceiptProcessingRequest.Selection): Boolean =
            !used && selection.imageId == context.expectedImageId

        fun arm(selection: ReceiptProcessingRequest.Selection): Boolean {
            if (!canArm(selection)) return false
            used = true
            armedSelection = selection
            return true
        }

        fun nowMillis(): Long {
            val now = elapsedMillis()
            if (armedSelection != null && capturedStart == null) capturedStart = now
            return now
        }

        fun seal(request: ReceiptProcessingRequest?, delay: Long) {
            val selection = armedSelection ?: return
            val start = capturedStart
            disarm()
            if (start == null || start !in 0L..(Long.MAX_VALUE - TIMEOUT_MILLIS)) return
            if (request == null || request.selection !== selection || request.context != context ||
                context.mode != PresentationConsumerMode.FIXTURE || delay != TIMEOUT_MILLIS
            ) return
            record = Record(request, selection, selection.owner, request.submission, generation, start)
        }

        fun startMillis(request: ReceiptProcessingRequest): Long? =
            record?.takeIf {
                it.request === request && it.submission === request.submission &&
                    it.selection === request.selection && it.owner === request.selection.owner &&
                    it.generation === generation && request.context == context
            }?.start

        fun isCurrent(request: ReceiptProcessingRequest): Boolean = startMillis(request) != null

        fun disarm() {
            armedSelection = null
            capturedStart = null
        }

        fun revoke() {
            record = null
            disarm()
        }

        companion object {
            const val TIMEOUT_MILLIS = 6_000L
        }
    }

    enum class InputState { EMPTY, PREPARING, READY, ERROR }

    private var disposed = false
    @Volatile private var generation = Any()
    private var fixturePreparationStarted = false
    var inputState = InputState.EMPTY
        private set
    private val processing = ReceiptProcessingUiController(
        transport, postWorker, postUi, ::scheduleProcessing, nowMillis, timeoutMillis,
        newImageId, newRequestId, onStateChanged = ::onProcessingChanged, consumerMode = consumerMode,
    )
    val state: ReceiptProcessingLifecycle.State get() = processing.state
    val isFixture: Boolean get() = fixture != null

    val canStart: Boolean
        get() {
            if (disposed || inputState != InputState.READY) return false
            val ready = state as? ReceiptProcessingLifecycle.State.Ready ?: return false
            val binding = fixture ?: return true
            return !binding.closed && binding.start.canArm(ready.selection)
        }

    fun ownsFixture(binding: FixtureBinding): Boolean = fixture === binding

    init {
        require(maximumBytes > 0)
    }

    private fun scheduleProcessing(delay: Long, action: () -> Unit) {
        // submit() has installed Pending and has not posted its worker yet.
        fixture?.start?.seal((state as? ReceiptProcessingLifecycle.State.Pending)?.request, delay)
        schedule(delay, action)
    }

    private fun onProcessingChanged(state: ReceiptProcessingLifecycle.State) {
        if (state is ReceiptProcessingLifecycle.State.Finished) fixture?.close()
        publish()
    }

    /** Replacing a URI, crop, or prepared input always invalidates the previous selection. */
    fun prepareInput(encode: () -> ByteArray) {
        check(!disposed)
        check(consumerMode == PresentationConsumerMode.FIXTURE)
        val token = Any().also { generation = it }
        if (fixture != null && (fixturePreparationStarted || fixture.closed)) {
            fixture.start.revoke()
            inputState = InputState.ERROR
            processing.clearSelection()
            fixture.close()
            publish()
            return
        }
        if (fixture != null) fixturePreparationStarted = true
        processing.clearSelection()
        replaceSnapshot(null)
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
                } else if (snapshot == null || !replaceSnapshot(snapshot)) {
                    snapshot?.release()
                    inputState = InputState.ERROR
                    processing.clearSelection()
                    fixture?.close()
                } else {
                    inputState = InputState.READY
                    publish()
                }
            }
        }
        publish()
    }

    /** LIVE owns one captured URI/crop. Its bounded preparation runs after Start. */
    fun selectLiveInput() {
        check(!disposed && consumerMode == PresentationConsumerMode.LIVE && inputState == InputState.EMPTY)
        inputState = InputState.READY
        processing.selectInput()
    }

    fun start() {
        if (!canStart) return
        val binding = fixture
        if (binding == null) {
            processing.start()
            return
        }
        val selected = (state as? ReceiptProcessingLifecycle.State.Ready)?.selection ?: return
        if (!binding.start.arm(selected)) return
        try {
            processing.start()
        } catch (error: RuntimeException) {
            binding.start.revoke()
            try {
                processing.cancel()
            } finally {
                binding.close()
            }
            throw error
        } finally {
            binding.start.disarm()
        }
    }

    fun cancel() {
        if (disposed) return
        val binding = fixture?.takeIf { state is ReceiptProcessingLifecycle.State.Pending }
        binding?.start?.revoke()
        try {
            processing.cancel()
        } finally {
            binding?.close()
        }
    }

    fun dispose() {
        if (disposed) return
        disposed = true
        generation = Any()
        fixture?.start?.revoke()
        try {
            processing.dispose()
        } finally {
            if (fixture == null) replaceSnapshot(null) else fixture.detach()
            inputState = InputState.EMPTY
        }
    }

    private fun publish() { if (!disposed) onChanged() }

    private class PendingFixture(val owner: Any, val preview: Any, val binding: FixtureBinding)

    // Instrumentation installs the one-shot offer on the UI thread before selected preparation.
    companion object {
        private val observedOwners = WeakHashMap<Any, Unit>()
        private var pendingFixture: PendingFixture? = null

        internal fun offerFixture(owner: Any, preview: Any, binding: FixtureBinding) {
            check(pendingFixture == null && owner !in observedOwners && !binding.closed)
            pendingFixture = PendingFixture(owner, preview, binding)
        }

        private fun forgetFixture(binding: FixtureBinding) {
            if (pendingFixture?.binding === binding) pendingFixture = null
        }

        internal fun claimFixture(owner: Any, preview: Any?): FixtureBinding? {
            observedOwners[owner] = Unit
            val pending = pendingFixture?.takeIf { it.owner === owner } ?: return null
            pendingFixture = null
            if (pending.preview == preview && !pending.binding.closed) return pending.binding
            pending.binding.detach()
            return null
        }
    }
}
