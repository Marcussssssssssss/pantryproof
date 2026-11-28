package com.pantryproof.prototype

import android.app.Instrumentation
import android.content.ContentResolver
import android.net.Uri
import android.os.Looper
import android.os.Process
import android.os.SystemClock
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.ReceiptProcessingDelivery
import com.pantryproof.prototype.data.ReceiptProcessingTransport
import com.pantryproof.prototype.data.ReceiptSubmissionBinding
import com.pantryproof.prototype.data.S04FakeHttpTransport
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import com.pantryproof.prototype.ui.SelectedImageProcessingController.FixtureBinding
import com.pantryproof.prototype.ui.SelectedImageProcessingController.FixtureStart
import java.io.File
import java.security.MessageDigest
import java.util.Locale

/** In-process hook for trusted S04 instrumentation. No configuration is persisted. */
internal object S04FakeHarnessBinding {
    private const val TARGET = "com.pantryproof.prototype.s04fake"
    private const val PNG_BYTES = 1_352

    class Ticket internal constructor()

    class RunConfig(
        val instrumentation: Instrumentation,
        val port: String,
        val token: String,
        requestId: String,
        imageId: String,
        val generatedImage: S04FakeHttpTransport.GeneratedImage,
        val responsePin: S04FakeHttpTransport.ResponsePin,
        preparedBytes: ByteArray,
    ) {
        val context = PresentationConsumerContext(requestId, imageId, PresentationConsumerMode.FIXTURE)
        private val pinnedBytes: ByteArray

        init {
            require(preparedBytes.size == PNG_BYTES)
            pinnedBytes = preparedBytes.copyOf()
            require(sha256(pinnedBytes) == generatedImage.sha256)
        }

        fun copyPinnedBytes(): ByteArray = pinnedBytes.copyOf()
    }

    // Stage, attach, reset and lifecycle callbacks are serialized on the target UI thread.
    private var run: Run? = null

    fun stage(runConfig: RunConfig): Ticket {
        checkMainThread()
        check(run == null)
        val target = runConfig.instrumentation.targetContext
        check(target.packageName == TARGET && target.applicationInfo.uid == Process.myUid())
        val ticket = Ticket()
        run = Run(ticket, runConfig)
        return ticket
    }

    fun attach(ticket: Ticket, activity: MainActivity, approvedPreview: Uri) {
        checkMainThread()
        val staged = checkNotNull(run?.takeIf { it.ticket === ticket })
        try {
            staged.attach(activity, approvedPreview)
        } catch (error: RuntimeException) {
            staged.reset()
            throw error
        }
    }

    fun reset(ticket: Ticket) {
        checkMainThread()
        run?.takeIf { it.ticket === ticket }?.reset()
    }

    private class Run(val ticket: Ticket, initial: RunConfig) {
        @Volatile private var config: RunConfig? = initial
        @Volatile private var sender: S04FakeHttpTransport? = null
        private val start = FixtureStart(initial.context, ticket, SystemClock::elapsedRealtime)
        private var activity: MainActivity? = null
        private var observer: LifecycleEventObserver? = null
        private var binding: FixtureBinding? = null

        fun attach(owner: MainActivity, preview: Uri) {
            check(activity == null && binding == null)
            val target = checkNotNull(config).instrumentation.targetContext
            check(owner.packageName == TARGET && owner.applicationContext === target.applicationContext)
            check(!owner.isFinishing && !owner.isDestroyed &&
                owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED))
            val previewFile = privateCachePreview(owner, preview)
            val pair = FixtureBinding(
                transport = ReceiptProcessingTransport { request, deliver ->
                    val currentSender = sender
                    if (currentSender == null) {
                        deliver(ReceiptProcessingDelivery.ExecutionFailure)
                        ReceiptProcessingTransport.Cancellation {}
                    } else {
                        currentSender.submit(request, deliver)
                    }
                },
                replaceSnapshot = ::replaceSnapshot,
                start = start,
                maximumBytes = PNG_BYTES,
                preparedInput = { verifiedPinnedInput(previewFile) },
                retire = ::retireSender,
                release = ::release,
            )
            val lifetime = LifecycleEventObserver { _, event ->
                if (event == Lifecycle.Event.ON_STOP || event == Lifecycle.Event.ON_DESTROY) {
                    S04FakeHarnessBinding.reset(ticket)
                }
            }
            binding = pair
            activity = owner
            observer = lifetime
            SelectedImageProcessingController.offerFixture(owner, preview, pair)
            owner.lifecycle.addObserver(lifetime)
        }

        fun reset() {
            val pair = binding
            if (pair == null) {
                release()
                return
            }
            try {
                activity?.resetSelectedImageFixture(pair)
            } finally {
                pair.detach()
            }
        }

        private fun verifiedPinnedInput(preview: File): ByteArray {
            val staged = checkNotNull(config)
            val pinned = staged.copyPinnedBytes()
            val canonical = preview.canonicalFile
            check(canonical.parentFile == preview.parentFile?.canonicalFile &&
                canonical.name == preview.name && canonical.isFile)
            // The preview is read for identity only. The upload uses the separately pinned copy.
            canonical.inputStream().use { input ->
                for (byte in pinned) check(input.read() == (byte.toInt() and 0xff))
                check(input.read() == -1)
            }
            return pinned
        }

        private fun replaceSnapshot(snapshot: ReceiptSubmissionBinding.Snapshot?): Boolean {
            if (snapshot == null) {
                closeSender()
                return true
            }
            val staged = config ?: return false
            if (sender != null) return false
            val bytes = snapshot.copyBytes()
            return try {
                sender = S04FakeHttpTransport(
                    port = staged.port,
                    token = staged.token,
                    selection = snapshot.selection,
                    context = staged.context,
                    preparedBytes = bytes,
                    generatedImage = staged.generatedImage,
                    responsePin = staged.responsePin,
                    elapsedMillis = start.elapsedMillis,
                    lifecycleStartMillis = start::startMillis,
                    isCurrentAttempt = start::isCurrent,
                )
                config = null
                true
            } catch (_: RuntimeException) {
                false
            } finally {
                bytes.fill(0)
                snapshot.release()
            }
        }

        private fun closeSender() {
            val previous = sender
            sender = null
            previous?.close()
        }

        private fun retireSender() {
            config = null
            closeSender()
        }

        private fun release() {
            config = null
            val owner = activity
            val lifetime = observer
            activity = null
            observer = null
            binding = null
            if (S04FakeHarnessBinding.run === this) S04FakeHarnessBinding.run = null
            if (lifetime != null) owner?.lifecycle?.removeObserver(lifetime)
        }
    }

    private fun privateCachePreview(activity: MainActivity, preview: Uri): File {
        require(preview.scheme == ContentResolver.SCHEME_FILE && preview.isHierarchical)
        val file = File(requireNotNull(preview.path))
        require(file.parentFile == activity.cacheDir.absoluteFile && preview == Uri.fromFile(file))
        return file
    }

    private fun checkMainThread() {
        check(Looper.myLooper() === Looper.getMainLooper())
    }

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") {
            "%02X".format(Locale.ROOT, it.toInt() and 0xff)
        }
}
