package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import java.util.ArrayDeque
import org.junit.Assert.*
import org.junit.Test

class BoundSyntheticReceiptProcessingTransportTest {
    private val selection = ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), "image")
    private val tasks = ArrayDeque<() -> Unit>()
    private var submissions = 0
    private val transport = BoundSyntheticReceiptProcessingTransport(
        { submissions++; SyntheticReceiptProcessingTransport.Scenario.AVAILABLE }, { tasks.addLast(it) },
    )
    private fun request(selected: ReceiptProcessingRequest.Selection = selection, image: String = "image", id: String = "request") =
        ReceiptProcessingRequest(selected, ReceiptProcessingRequest.Submission(), PresentationConsumerContext(id, image, PresentationConsumerMode.FIXTURE))
    private fun snapshot() = ReceiptSubmissionBinding.Snapshot(selection, byteArrayOf(1, 2, 3), 16)
    private fun drain() { while (tasks.isNotEmpty()) tasks.removeFirst()() }

    @Test fun exactSelectionOwnerSubmissionAndContextReachValidatedSyntheticAdapter() {
        val snapshot = snapshot(); transport.replaceSnapshot(snapshot)
        val request = request()
        val bound = snapshot.bind(request)
        assertSame(selection, bound.selection); assertSame(selection.owner, bound.owner)
        assertSame(request, bound.request); assertSame(request.submission, bound.request.submission)
        var result: ReceiptPresentationUiResult? = null
        transport.submit(request) { result = M3eReceiptPresentationAdapter().decodeAndMap((it as ReceiptProcessingDelivery.Envelope).takeBytes(), request.context) }
        assertNull(result); drain()
        assertTrue(result is ReceiptPresentationUiResult.Available); assertEquals(1, submissions)
    }

    @Test fun callerAndReturnedBuffersCannotMutateSnapshot() {
        val source = byteArrayOf(1, 2, 3)
        val snapshot = ReceiptSubmissionBinding.Snapshot(selection, source, 16)
        source[0] = 99
        val binding = snapshot.bind(request()); val copy = binding.copyBytes(); copy[1] = 99
        assertArrayEquals(byteArrayOf(1, 2, 3), binding.copyBytes())
    }

    @Test fun foreignSelectionWithMatchingStringsIsRejectedWithoutSyntheticSubmission() {
        transport.replaceSnapshot(snapshot())
        val foreign = ReceiptProcessingRequest.Selection(selection.owner, "image")
        var result: ReceiptProcessingDelivery? = null
        transport.submit(request(foreign)) { result = it }
        assertSame(ReceiptProcessingDelivery.ExecutionFailure, result); assertEquals(0, submissions)
    }

    @Test fun foreignOwnerWithMatchingImageIdIsRejected() {
        transport.replaceSnapshot(snapshot())
        val foreign = ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), "image")
        transport.submit(request(foreign)) { assertSame(ReceiptProcessingDelivery.ExecutionFailure, it) }
        assertEquals(0, submissions)
    }

    @Test fun wrongExpectedImageIdIsRejectedWithoutSyntheticSuccess() {
        transport.replaceSnapshot(snapshot())
        transport.submit(request(image = "wrong")) { assertSame(ReceiptProcessingDelivery.ExecutionFailure, it) }
        assertEquals(0, submissions)
    }

    @Test fun freshRequestsAndSubmissionTokensReuseOneValidSnapshot() {
        val snapshot = snapshot(); transport.replaceSnapshot(snapshot)
        val first = request(id = "first"); val next = request(id = "second")
        assertNotSame(first.submission, next.submission)
        var count = 0
        listOf(first, next).forEach { req -> transport.submit(req) {
            assertTrue(M3eReceiptPresentationAdapter().decodeAndMap((it as ReceiptProcessingDelivery.Envelope).takeBytes(), req.context) is ReceiptPresentationUiResult.Available)
            count++
        } }
        drain(); assertEquals(2, count); assertEquals(2, submissions)
    }

    @Test fun replacementReleasesOriginalSnapshotAndExistingBinding() {
        val previous = snapshot(); val binding = previous.bind(request())
        transport.replaceSnapshot(previous); transport.replaceSnapshot(snapshot())
        assertThrows(IllegalStateException::class.java) { previous.bind(request()) }
        assertThrows(IllegalStateException::class.java) { binding.copyBytes() }
    }

    @Test fun clearReleasesSnapshotAndMissingSnapshotCannotSucceed() {
        val previous = snapshot(); transport.replaceSnapshot(previous); transport.replaceSnapshot(null)
        assertThrows(IllegalStateException::class.java) { previous.copyBytes() }
        var count = 0
        transport.submit(request()) { assertSame(ReceiptProcessingDelivery.ExecutionFailure, it); count++ }
        assertEquals(1, count); assertEquals(0, submissions)
    }

    @Test fun externallyReleasedSnapshotCannotSubmit() {
        val previous = snapshot(); transport.replaceSnapshot(previous); previous.release()
        transport.submit(request()) { assertSame(ReceiptProcessingDelivery.ExecutionFailure, it) }
        assertEquals(0, submissions)
    }

    @Test fun cancellationSuppressesDelayedSyntheticDelivery() {
        transport.replaceSnapshot(snapshot()); var count = 0
        transport.submit(request()) { count++ }.cancel(); drain()
        assertEquals(0, count)
    }
}
