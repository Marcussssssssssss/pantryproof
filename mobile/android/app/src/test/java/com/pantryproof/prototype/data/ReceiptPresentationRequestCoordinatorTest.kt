package com.pantryproof.prototype.data

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonToken
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationFailureStage
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes
import com.pantryproof.prototype.ui.PantryUiState
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CyclicBarrier
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptPresentationRequestCoordinatorTest {
    private val coordinator = ReceiptPresentationRequestCoordinator()
    private val processor = DeferredProcessor(coordinator)
    private val demoContext = SyntheticReceiptPresentationPayload.context
    private val demoPayload = SyntheticReceiptPresentationPayload.bytes()

    @Test
    fun matchingFixtureCompletionDeliversReviewablePresentation() {
        val result = start()(demoPayload) as ReceiptPresentationUiResult.Available

        assertTrue(result.canReview)
        assertEquals("23.00", result.receipt.receiptTotal.value)
    }

    @Test
    fun callerSuppliedRequestAndImageIdsAreBothEnforced() {
        assertRejected(
            ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            start(demoContext.copy(expectedRequestId = "request-other"))(demoPayload),
        )
        assertRejected(
            ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
            start(demoContext.copy(expectedImageId = "image-other"))(demoPayload),
        )
    }

    @Test
    fun liveAttemptRejectsSyntheticFixtureDespiteMatchingIds() {
        val liveContext = demoContext.copy(mode = PresentationConsumerMode.LIVE)
        assertRejected(
            ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
            start(liveContext)(demoPayload),
        )
    }

    @Test
    fun malformedEnvelopeConsumesAttemptAndDeliversRejectionOnce() {
        val deliver = start()

        assertRejected(ReceiptPresentationIssueCodes.INVALID_JSON, deliver(byteArrayOf('{'.code.toByte())))
        assertNull(deliver(demoPayload))
    }

    @Test
    fun unsupportedVersionPreservesValidatorRejection() {
        assertRejected(
            ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION,
            completeFixture("08-unsupported-schema-version.json", "synthetic-unsupported-001"),
        )
    }

    @Test
    fun unavailableFailedAndInsufficientOutcomesRemainDistinct() {
        val unavailable = completeFixture("06-processing-unavailable.json", "synthetic-unavailable-001")
            as ReceiptPresentationUiResult.ProcessingUnavailable
        val failed = completeFixture("07-processing-failure.json", "synthetic-failure-001")
            as ReceiptPresentationUiResult.ProcessingFailed
        val insufficient = completeFixture("16-source-evidence-insufficient.json", "insufficient-completed-001")
            as ReceiptPresentationUiResult.InsufficientEvidence

        assertEquals("PROCESSOR_NOT_AVAILABLE", unavailable.failureCode)
        assertFalse(unavailable.retryable)
        assertEquals(PresentationFailureStage.OCR, failed.stage)
        assertEquals("OCR_ENGINE_FAILURE", failed.failureCode)
        assertTrue(failed.retryable)
        assertTrue(insufficient.reasons.isNotEmpty())
        assertFalse(unavailable.canReview)
        assertFalse(failed.canReview)
        assertFalse(insufficient.canReview)
    }

    @Test
    fun cancellationDiscardsCompletionEvenWithNoActiveAttempt() {
        val attempt = coordinator.begin(demoContext)
        val deliver = processor.submit(attempt)

        coordinator.cancel(attempt)

        assertNull(deliver(demoPayload))
        assertNull(deliver(demoPayload))
    }

    @Test
    fun replacementDiscardsOldCompletionsBeforeAndAfterNewCompletion() {
        val first = coordinator.begin(demoContext)
        val deliverFirst = processor.submit(first)
        val replacementContext = PresentationConsumerContext(
            "request-synthetic-complete-001",
            "image-synthetic-complete-001",
            PresentationConsumerMode.FIXTURE,
        )
        val deliverReplacement = start(replacementContext)

        assertNull(deliverFirst(demoPayload))
        coordinator.cancel(first)
        val replacement = deliverReplacement(fixtureEnvelope("01-complete-extracted-receipt.json"))
        assertTrue(replacement is ReceiptPresentationUiResult.Available)
        assertNull(deliverFirst(demoPayload))
    }

    @Test
    fun duplicateCompletionAfterAvailableResultIsDiscarded() {
        val deliver = start()

        assertTrue(deliver(demoPayload) is ReceiptPresentationUiResult.Available)
        assertNull(deliver(demoPayload))
    }

    @Test
    fun retryWithIdenticalIdsHasDistinctIdentityAndRejectsOldAttempt() {
        val first = coordinator.begin(demoContext)
        val deliverFirst = processor.submit(first)
        coordinator.cancel(first)
        val retry = coordinator.begin(demoContext)
        val deliverRetry = processor.submit(retry)

        assertNotSame(first, retry)
        assertTrue(deliverRetry(demoPayload) is ReceiptPresentationUiResult.Available)
        assertNull(deliverFirst(demoPayload))
        assertNull(deliverRetry(demoPayload))
    }

    @Test
    fun attemptFromAnotherCoordinatorCannotCompleteActiveRequest() {
        val foreign = ReceiptPresentationRequestCoordinator().begin(demoContext)
        val deliver = start()

        assertNull(processor.submit(foreign)(demoPayload))
        assertTrue(deliver(demoPayload) is ReceiptPresentationUiResult.Available)
    }

    @Test
    fun concurrentDuplicateCompletionsDeliverExactlyOneResult() {
        val deliver = start()
        val barrier = CyclicBarrier(2)
        val executor = Executors.newFixedThreadPool(2)
        try {
            val completions = List(2) {
                executor.submit<ReceiptPresentationUiResult?> {
                    barrier.await(10, TimeUnit.SECONDS)
                    deliver(demoPayload)
                }
            }.map { it.get(10, TimeUnit.SECONDS) }

            assertEquals(1, completions.count { it is ReceiptPresentationUiResult.Available })
            assertEquals(1, completions.count { it == null })
        } finally {
            executor.shutdownNow()
        }
    }

    @Test
    fun missingUnresolvedAndWeightedFieldsSurvivePresentation() {
        val missing = completeFixture("03-missing-required-store-name.json", "synthetic-store-missing-001")
            as ReceiptPresentationUiResult.Available
        val unresolved = completeFixture("04-unresolved-purchase-date.json", "synthetic-date-unresolved-001")
            as ReceiptPresentationUiResult.Available
        val weighted = completeFixture("05-decimal-weighted-quantity.json", "synthetic-weighted-001")
            as ReceiptPresentationUiResult.Available

        assertEquals(PresentedFieldStatus.MISSING, missing.receipt.storeName.status)
        assertEquals("STORE_NAME_NOT_OBSERVED", missing.receipt.storeName.absenceReason)
        assertNull(missing.receipt.storeName.value)
        assertEquals(PresentedFieldStatus.UNRESOLVED, unresolved.receipt.purchaseDate.status)
        assertEquals("AMBIGUOUS_DATE_FORMAT", unresolved.receipt.purchaseDate.absenceReason)
        assertNull(unresolved.receipt.purchaseDate.value)
        assertEquals("0.750", weighted.receipt.items.single().quantity.value)
        assertNull(weighted.receipt.toInventoryCompatibleReceiptOrNull())
    }

    @Test
    fun availableEnvelopeWithFailedExtractionDoesNotAuthorizeInventory() {
        // Fixture 15 carries FAILED extraction. The adapter exposes review data only.
        val pantry = PantryUiState(MockReceiptPresentationSource())
        val startingInventory = pantry.inventory.toList()
        val startingReceipt = pantry.receipt

        val result = completeFixture("15-result-available-extraction-failed.json", "extraction-failed-001")
        assertTrue(result is ReceiptPresentationUiResult.Available)
        assertTrue(result?.canReview == true)

        assertEquals(startingInventory, pantry.inventory)
        assertSame(startingReceipt, pantry.receipt)
        assertFalse(pantry.demoConfirmed)
    }

    private fun start(context: PresentationConsumerContext = demoContext) =
        processor.submit(coordinator.begin(context))

    private fun completeFixture(name: String, idSuffix: String): ReceiptPresentationUiResult? {
        val expected = PresentationConsumerContext(
            expectedRequestId = "request-$idSuffix",
            expectedImageId = "image-$idSuffix",
            mode = PresentationConsumerMode.FIXTURE,
        )
        return start(expected)(fixtureEnvelope(name))
    }

    private fun assertRejected(code: String, result: ReceiptPresentationUiResult?) {
        assertTrue(result is ReceiptPresentationUiResult.Rejected)
        assertEquals(code, (result as ReceiptPresentationUiResult.Rejected).issue.code)
        assertFalse(result.canReview)
    }

    private fun fixtureEnvelope(name: String): ByteArray {
        val fixture = generateSequence(Path.of("").toAbsolutePath()) { it.parent }
            .map { it.resolve("tests/fixtures/receipt_presentation_v1/v1/fixtures/$name") }
            .first(Files::isRegularFile)
        val bytes = Files.readAllBytes(fixture)
        JsonFactory().createParser(bytes).use { parser ->
            check(parser.nextToken() == JsonToken.START_OBJECT)
            while (parser.nextToken() == JsonToken.FIELD_NAME) {
                val key = parser.currentName()
                val value = parser.nextToken()
                if (key == "envelope") {
                    check(value == JsonToken.START_OBJECT)
                    val start = parser.currentTokenLocation().byteOffset.toInt()
                    parser.skipChildren()
                    return bytes.copyOfRange(start, parser.currentLocation().byteOffset.toInt())
                }
                parser.skipChildren()
            }
        }
        error("Canonical fixture omitted its envelope")
    }

    /** Each returned callback can be released repeatedly or in any order by the test. */
    private class DeferredProcessor(private val coordinator: ReceiptPresentationRequestCoordinator) {
        fun submit(attempt: ReceiptPresentationRequestCoordinator.Attempt):
            (ByteArray) -> ReceiptPresentationUiResult? =
            { bytes -> coordinator.complete(attempt, bytes) }
    }
}
