package com.pantryproof.prototype.ui

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import com.pantryproof.prototype.contract.v1.AutomaticExtractionStatus
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import com.pantryproof.prototype.data.M3eReceiptPresentationAdapter
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.SyntheticReceiptPresentationPayload
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptReviewAnnotationPolicyTest {
    private val adapter = M3eReceiptPresentationAdapter()

    @Test
    fun canonicalAvailableWithFailedExtractionNeedsAnnotationButRemainsReviewable() {
        val available = loadCanonical("15-result-available-extraction-failed.json")
            as ReceiptPresentationUiResult.Available

        assertEquals(AutomaticExtractionStatus.FAILED, available.receipt.automaticExtractionStatus)
        assertTrue(available.canReview)
        assertTrue(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(available))
        assertTrue(available.receipt.items.isEmpty())
        assertEquals(PresentedFieldStatus.MISSING, available.receipt.storeName.status)
        assertEquals(PresentedFieldStatus.UNRESOLVED, available.receipt.purchaseDate.status)
        assertNull(available.receipt.toInventoryCompatibleReceiptOrNull())
    }

    @Test
    fun partialAndExtractedAvailableResultsDoNotShowFailedAnnotation() {
        val available = syntheticAvailable()
        assertEquals(AutomaticExtractionStatus.PARTIAL, available.receipt.automaticExtractionStatus)
        assertFalse(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(available))

        val extracted = ReceiptPresentationUiResult.Available(
            available.receipt.copy(automaticExtractionStatus = AutomaticExtractionStatus.EXTRACTED),
        )
        assertFalse(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(extracted))
        assertTrue(extracted.canReview)
    }

    @Test
    fun missingOptionalMetadataDoesNotClaimFailedOrSuccessfulExtraction() {
        val available = syntheticAvailable()
        val legacy = ReceiptPresentationUiResult.Available(
            available.receipt.copy(automaticExtractionStatus = null),
        )
        assertNull(legacy.receipt.automaticExtractionStatus)
        assertFalse(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(legacy))
    }

    @Test
    fun nonAvailableAndRejectedResultsNeverShowReviewAnnotation() {
        val unavailable = loadCanonical("06-processing-unavailable.json")
        val failed = loadCanonical("07-processing-failure.json")
        val insufficient = loadCanonical("16-source-evidence-insufficient.json")
        val rejected = adapter.decodeAndMap(
            "{".toByteArray(), SyntheticReceiptPresentationPayload.context,
        )
        assertTrue(unavailable is ReceiptPresentationUiResult.ProcessingUnavailable)
        assertTrue(failed is ReceiptPresentationUiResult.ProcessingFailed)
        assertTrue(insufficient is ReceiptPresentationUiResult.InsufficientEvidence)
        assertTrue(rejected is ReceiptPresentationUiResult.Rejected)
        listOf(unavailable, failed, insufficient, rejected).forEach { result ->
            assertFalse(result.canReview)
            assertFalse(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(result))
        }
    }

    @Test
    fun annotationPolicyDoesNotAlterReceiptFieldsOrInventoryCompatibility() {
        val available = syntheticAvailable()
        val before = available.receipt.toInventoryCompatibleReceiptOrNull()
        val fields = available.receipt.items.toList()
        val failed = ReceiptPresentationUiResult.Available(
            available.receipt.copy(automaticExtractionStatus = AutomaticExtractionStatus.FAILED),
        )

        assertTrue(ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(failed))
        assertEquals(fields, failed.receipt.items)
        assertEquals(before, failed.receipt.toInventoryCompatibleReceiptOrNull())
        assertEquals(before, available.receipt.toInventoryCompatibleReceiptOrNull())
        assertEquals(AutomaticExtractionStatus.PARTIAL, available.receipt.automaticExtractionStatus)
    }

    private fun syntheticAvailable(): ReceiptPresentationUiResult.Available =
        adapter.decodeAndMap(
            SyntheticReceiptPresentationPayload.bytes(),
            SyntheticReceiptPresentationPayload.context,
        ) as ReceiptPresentationUiResult.Available

    private fun loadCanonical(name: String): ReceiptPresentationUiResult {
        val raw = extractEnvelope(Files.readAllBytes(fixtureRoot().resolve("fixtures/$name")))
        val decoded = ReceiptPresentationV1Decoder.decode(raw)
        assertTrue(decoded is ReceiptPresentationResult.Accepted)
        val envelope = (decoded as ReceiptPresentationResult.Accepted).value
        return adapter.decodeAndMap(
            raw,
            PresentationConsumerContext(
                envelope.requestId, envelope.imageId, PresentationConsumerMode.FIXTURE,
            ),
        )
    }

    private fun extractEnvelope(wrapper: ByteArray): ByteArray {
        val factory = JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build()
        factory.createParser(wrapper).use { parser ->
            check(parser.nextToken() == JsonToken.START_OBJECT)
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                check(parser.currentToken == JsonToken.FIELD_NAME)
                val name = parser.currentName()
                val valueToken = parser.nextToken()
                if (name == "envelope") {
                    check(valueToken == JsonToken.START_OBJECT)
                    return ByteArrayOutputStream().use { output ->
                        factory.createGenerator(output).use { generator ->
                            generator.copyCurrentStructure(parser)
                        }
                        output.toByteArray()
                    }
                }
                parser.skipChildren()
            }
        }
        error("canonical fixture omitted envelope")
    }

    private fun fixtureRoot(): Path {
        var current: Path? = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize()
        while (current != null) {
            val candidate = current.resolve("tests/fixtures/receipt_presentation_v1/v1")
            if (Files.isRegularFile(candidate.resolve("manifest.json"))) return candidate
            current = current.parent
        }
        error("canonical fixture root not found")
    }
}
