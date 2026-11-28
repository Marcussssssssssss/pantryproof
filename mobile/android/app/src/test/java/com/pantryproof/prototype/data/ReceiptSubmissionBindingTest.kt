package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.ReceiptProcessingRequest.Owner
import com.pantryproof.prototype.data.ReceiptProcessingRequest.Selection
import com.pantryproof.prototype.data.ReceiptProcessingRequest.Submission
import com.pantryproof.prototype.data.ReceiptSubmissionBinding.Snapshot
import com.pantryproof.prototype.ui.PantryUiState
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptSubmissionBindingTest {
    private val selection = Selection(Owner(), "synthetic-image-001")
    private val input = byteArrayOf(1, 2, 3, 4)
    private val pantry = PantryUiState(MockReceiptPresentationSource())
    private val originalInventory = pantry.inventory.toList()
    private val originalReceipt = pantry.receipt
    private val originalPresentation = pantry.presentationResult
    private val originalConfirmation = pantry.demoConfirmed

    @After
    fun inventoryAndConfirmationRemainUnchanged() {
        assertEquals(originalInventory, pantry.inventory)
        assertSame(originalReceipt, pantry.receipt)
        assertSame(originalPresentation, pantry.presentationResult)
        assertEquals(originalConfirmation, pantry.demoConfirmed)
    }

    @Test
    fun callerMutationCannotChangeTheSnapshot() {
        val snapshot = Snapshot(selection, input, 4)
        input.fill(9)

        assertArrayEquals(byteArrayOf(1, 2, 3, 4), snapshot.copyBytes())
    }

    @Test
    fun snapshotReadsReturnIndependentCopies() {
        val snapshot = Snapshot(selection, input, 4)
        val first = snapshot.copyBytes()
        val second = snapshot.copyBytes()
        first.fill(9)

        assertNotSame(first, second)
        assertArrayEquals(input, second)
        assertArrayEquals(input, snapshot.copyBytes())
    }

    @Test
    fun boundReadsAlsoReturnIndependentCopies() {
        val snapshot = Snapshot(selection, input, 4)
        val binding = snapshot.bind(request())
        val first = binding.copyBytes()
        val second = binding.copyBytes()
        first.fill(9)

        assertNotSame(first, second)
        assertArrayEquals(input, second)
        assertArrayEquals(input, binding.copyBytes())
        assertArrayEquals(input, snapshot.copyBytes())
    }

    @Test
    fun bindingRetainsTheExactExistingDescriptorAndIdentityScopes() {
        val snapshot = Snapshot(selection, input, 4)
        val original = request()
        val binding = snapshot.bind(original)

        assertSame(original, binding.request)
        assertSame(selection, snapshot.selection)
        assertSame(selection, binding.selection)
        assertSame(selection.owner, snapshot.owner)
        assertSame(selection.owner, binding.owner)
        assertSame(original.submission, binding.request.submission)
        assertSame(original.context, binding.request.context)
        assertEquals(selection.imageId, snapshot.imageId)
        assertEquals(selection.imageId, binding.imageId)
        assertEquals("synthetic-request-001", binding.request.context.expectedRequestId)
        assertEquals(PresentationConsumerMode.FIXTURE, binding.request.context.mode)
    }

    @Test
    fun aDifferentSelectionWithTheSameOwnerAndImageIsRejected() {
        val snapshot = Snapshot(selection, input, 4)
        val otherSelection = Selection(selection.owner, selection.imageId)

        assertThrows(IllegalArgumentException::class.java) {
            snapshot.bind(request(selected = otherSelection))
        }
        assertArrayEquals(input, snapshot.copyBytes())
    }

    @Test
    fun aDifferentOwnerWithTheSameImageIsRejected() {
        val snapshot = Snapshot(selection, input, 4)
        val foreignSelection = Selection(Owner(), selection.imageId)

        assertNotSame(selection.owner, foreignSelection.owner)
        assertThrows(IllegalArgumentException::class.java) {
            snapshot.bind(request(selected = foreignSelection))
        }
    }

    @Test
    fun mismatchedExpectedImageIsRejectedEvenForTheCorrectSelection() {
        val snapshot = Snapshot(selection, input, 4)

        assertThrows(IllegalArgumentException::class.java) {
            snapshot.bind(request(imageId = "synthetic-image-other"))
        }
        assertArrayEquals(input, snapshot.bind(request()).copyBytes())
    }

    @Test
    fun retryCanReuseTheSnapshotWithANewRequestAndSubmission() {
        val snapshot = Snapshot(selection, input, 4)
        val firstRequest = request()
        val retryRequest = request(requestId = "synthetic-request-retry")
        val first = snapshot.bind(firstRequest)
        val retry = snapshot.bind(retryRequest)

        assertSame(firstRequest, first.request)
        assertSame(retryRequest, retry.request)
        assertSame(first.selection, retry.selection)
        assertSame(first.owner, retry.owner)
        assertNotSame(firstRequest.submission, retryRequest.submission)
        assertEquals("synthetic-request-001", first.request.context.expectedRequestId)
        assertEquals("synthetic-request-retry", retry.request.context.expectedRequestId)
        assertArrayEquals(first.copyBytes(), retry.copyBytes())
    }

    @Test
    fun identicalIdsDoNotReplaceSubmissionReferenceIdentity() {
        val snapshot = Snapshot(selection, input, 4)
        val firstRequest = request()
        val secondRequest = request()
        val first = snapshot.bind(firstRequest)
        val second = snapshot.bind(secondRequest)

        assertEquals(firstRequest.context, secondRequest.context)
        assertNotSame(firstRequest.submission, secondRequest.submission)
        assertSame(firstRequest.submission, first.request.submission)
        assertSame(secondRequest.submission, second.request.submission)
    }

    @Test
    fun releasedSnapshotRejectsNewBindingsAndReads() {
        val snapshot = Snapshot(selection, input, 4)
        snapshot.release()

        assertThrows(IllegalStateException::class.java) { snapshot.bind(request()) }
        assertThrows(IllegalStateException::class.java) { snapshot.copyBytes() }
    }

    @Test
    fun releaseInvalidatesReadsThroughAllPreviouslyBoundSubmissions() {
        val snapshot = Snapshot(selection, input, 4)
        val first = snapshot.bind(request())
        val retry = snapshot.bind(request(requestId = "synthetic-request-retry"))
        snapshot.release()

        assertThrows(IllegalStateException::class.java) { first.copyBytes() }
        assertThrows(IllegalStateException::class.java) { retry.copyBytes() }
    }

    @Test
    fun releaseDoesNotMutateAlreadyReturnedCallerOwnedCopies() {
        val snapshot = Snapshot(selection, input, 4)
        val issuedCopy = snapshot.bind(request()).copyBytes()
        snapshot.release()

        assertArrayEquals(input, issuedCopy)
        assertArrayEquals(byteArrayOf(1, 2, 3, 4), input)
    }

    @Test
    fun repeatedReleaseIsIdempotentAndDoesNotReleaseAnotherSnapshot() {
        val first = Snapshot(selection, input, 4)
        val second = Snapshot(selection, input, 4)
        first.release()
        first.release()

        assertThrows(IllegalStateException::class.java) { first.bind(request()) }
        assertArrayEquals(input, second.bind(request()).copyBytes())
    }

    @Test
    fun emptyInputIsRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            Snapshot(selection, byteArrayOf(), 4)
        }
    }

    @Test
    fun oversizedInputIsRejected() {
        assertThrows(IllegalArgumentException::class.java) { Snapshot(selection, input, 3) }
    }

    @Test
    fun maximumByteLimitMustBePositive() {
        assertThrows(IllegalArgumentException::class.java) { Snapshot(selection, input, 0) }
        assertThrows(IllegalArgumentException::class.java) { Snapshot(selection, input, -1) }
    }

    @Test
    fun inputAtTheExactByteLimitIsAccepted() {
        val snapshot = Snapshot(selection, input, input.size)

        assertArrayEquals(input, snapshot.bind(request()).copyBytes())
    }

    @Test
    fun releaseBeforeQueuedOperationsMakesBothBindingAndReadingFail() {
        val snapshot = Snapshot(selection, input, 4)
        val original = request()
        val started = CountDownLatch(2)
        val workers = Executors.newFixedThreadPool(2)
        try {
            val bind: java.util.concurrent.Future<ReceiptSubmissionBinding>
            val read: java.util.concurrent.Future<ByteArray>
            synchronized(snapshot) {
                bind = workers.submit<ReceiptSubmissionBinding> {
                    started.countDown()
                    snapshot.bind(original)
                }
                read = workers.submit<ByteArray> {
                    started.countDown()
                    snapshot.copyBytes()
                }
                assertTrue(started.await(5, TimeUnit.SECONDS))
                snapshot.release()
            }

            val bindFailure = assertThrows(ExecutionException::class.java) {
                bind.get(5, TimeUnit.SECONDS)
            }
            val readFailure = assertThrows(ExecutionException::class.java) {
                read.get(5, TimeUnit.SECONDS)
            }
            assertTrue(bindFailure.cause is IllegalStateException)
            assertTrue(readFailure.cause is IllegalStateException)
        } finally {
            workers.shutdownNow()
        }
    }

    private fun request(
        selected: Selection = selection,
        requestId: String = "synthetic-request-001",
        imageId: String = selected.imageId,
    ) = ReceiptProcessingRequest(
        selected,
        Submission(),
        PresentationConsumerContext(requestId, imageId, PresentationConsumerMode.FIXTURE),
    )
}
