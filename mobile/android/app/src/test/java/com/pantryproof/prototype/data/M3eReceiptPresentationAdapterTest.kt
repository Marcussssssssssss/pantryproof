package com.pantryproof.prototype.data

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationFailureStage
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class M3eReceiptPresentationAdapterTest {
    private val adapter = M3eReceiptPresentationAdapter()

    @Test
    fun runtimeSyntheticPayloadIsValidatedAndMapsSevenRolesInRowOrder() {
        val result = adapter.decodeAndMap(
            SyntheticReceiptPresentationPayload.bytes(),
            SyntheticReceiptPresentationPayload.context,
        )

        assertTrue(result is ReceiptPresentationUiResult.Available)
        val receipt = (result as ReceiptPresentationUiResult.Available).receipt
        assertEquals("Demo Grocery Store (Synthetic)", receipt.storeName.value)
        assertEquals("2026-10-31", receipt.purchaseDate.value)
        assertEquals("23.00", receipt.receiptTotal.value)
        assertEquals("RM 23.00", receipt.receiptTotal.originalAutomaticValue)
        assertEquals(listOf("demo-milk", "demo-bread", "demo-bananas"), receipt.items.map { it.rowId })
        assertEquals("2", receipt.items[0].quantity.value)
        assertEquals("6.50", receipt.items[0].unitPrice.value)
        assertEquals("13.00", receipt.items[0].lineTotal.value)
        assertEquals(PresentedFieldStatus.MISSING, receipt.items[2].unitPrice.status)
        assertNull(receipt.items[2].unitPrice.value)
        assertEquals("NO_EXPLICIT_UNIT_PRICE_OBSERVED", receipt.items[2].unitPrice.absenceReason)
        assertEquals(3, receipt.toInventoryCompatibleReceiptOrNull()?.items?.size)
    }

    @Test
    fun canonicalMissingOptionalUnitPriceRemainsMissingAndConfirmable() {
        val result = loadCanonical("02-missing-optional-unit-price.json")

        val receipt = (result as ReceiptPresentationUiResult.Available).receipt
        assertEquals(PresentedFieldStatus.MISSING, receipt.items.single().unitPrice.status)
        assertNull(receipt.items.single().unitPrice.value)
        assertTrue(receipt.toInventoryCompatibleReceiptOrNull() != null)
    }

    @Test
    fun canonicalMissingRequiredAndUnresolvedFieldsRemainAbsent() {
        val missing = loadCanonical("03-missing-required-store-name.json")
            as ReceiptPresentationUiResult.Available
        val unresolved = loadCanonical("04-unresolved-purchase-date.json")
            as ReceiptPresentationUiResult.Available

        assertEquals(PresentedFieldStatus.MISSING, missing.receipt.storeName.status)
        assertNull(missing.receipt.storeName.value)
        assertEquals("STORE_NAME_NOT_OBSERVED", missing.receipt.storeName.absenceReason)
        assertNull(missing.receipt.toInventoryCompatibleReceiptOrNull())
        assertEquals(PresentedFieldStatus.UNRESOLVED, unresolved.receipt.purchaseDate.status)
        assertNull(unresolved.receipt.purchaseDate.value)
        assertEquals("AMBIGUOUS_DATE_FORMAT", unresolved.receipt.purchaseDate.absenceReason)
        assertNull(unresolved.receipt.toInventoryCompatibleReceiptOrNull())
    }

    @Test
    fun canonicalDecimalQuantityIsNeverRoundedIntoIntegerInventory() {
        val available = loadCanonical("05-decimal-weighted-quantity.json")
            as ReceiptPresentationUiResult.Available

        assertEquals("0.750", available.receipt.items.single().quantity.value)
        assertNull(available.receipt.toInventoryCompatibleReceiptOrNull())
    }

    @Test
    fun legitimateNonResultOutcomesExposeNoReceipt() {
        val unavailable = loadCanonical("06-processing-unavailable.json")
        val failed = loadCanonical("07-processing-failure.json")
        val insufficient = loadCanonical("16-source-evidence-insufficient.json")

        assertTrue(unavailable is ReceiptPresentationUiResult.ProcessingUnavailable)
        assertTrue(failed is ReceiptPresentationUiResult.ProcessingFailed)
        assertEquals(
            "PROCESSOR_NOT_AVAILABLE",
            (unavailable as ReceiptPresentationUiResult.ProcessingUnavailable).failureCode,
        )
        assertFalse(unavailable.retryable)
        assertEquals(
            PresentationFailureStage.OCR,
            (failed as ReceiptPresentationUiResult.ProcessingFailed).stage,
        )
        assertEquals("OCR_ENGINE_FAILURE", failed.failureCode)
        assertTrue(failed.retryable)
        assertTrue(insufficient is ReceiptPresentationUiResult.InsufficientEvidence)
        assertTrue((insufficient as ReceiptPresentationUiResult.InsufficientEvidence).reasons.isNotEmpty())
        assertFalse(unavailable.canReview)
        assertFalse(failed.canReview)
        assertFalse(insufficient.canReview)
    }

    @Test
    fun invalidJsonAndUnsafeProvenanceAreRejectedWithoutReceiptData() {
        val invalid = adapter.decodeAndMap(
            "{".toByteArray(),
            SyntheticReceiptPresentationPayload.context,
        )
        val unsafePayload = SyntheticReceiptPresentationPayload.bytes()
            .toString(Charsets.UTF_8)
            .replace("m3f-demo-001", "participant-001")
            .toByteArray()
        val unsafe = adapter.decodeAndMap(unsafePayload, SyntheticReceiptPresentationPayload.context)

        assertEquals(
            ReceiptPresentationIssueCodes.INVALID_JSON,
            (invalid as ReceiptPresentationUiResult.Rejected).issue.code,
        )
        assertEquals(
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            (unsafe as ReceiptPresentationUiResult.Rejected).issue.code,
        )
        assertFalse(invalid.canReview)
        assertFalse(unsafe.canReview)
    }

    @Test
    fun exactRequestImageAndFixtureModeAreRequired() {
        val raw = SyntheticReceiptPresentationPayload.bytes()
        val requestMismatch = adapter.decodeAndMap(
            raw,
            PresentationConsumerContext(
                "request-other",
                SyntheticReceiptPresentationPayload.IMAGE_ID,
                PresentationConsumerMode.FIXTURE,
            ),
        )
        val imageMismatch = adapter.decodeAndMap(
            raw,
            PresentationConsumerContext(
                SyntheticReceiptPresentationPayload.REQUEST_ID,
                "image-other",
                PresentationConsumerMode.FIXTURE,
            ),
        )
        val modeMismatch = adapter.decodeAndMap(
            raw,
            PresentationConsumerContext(
                SyntheticReceiptPresentationPayload.REQUEST_ID,
                SyntheticReceiptPresentationPayload.IMAGE_ID,
                PresentationConsumerMode.LIVE,
            ),
        )

        assertEquals(
            ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            (requestMismatch as ReceiptPresentationUiResult.Rejected).issue.code,
        )
        assertEquals(
            ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
            (imageMismatch as ReceiptPresentationUiResult.Rejected).issue.code,
        )
        assertEquals(
            ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
            (modeMismatch as ReceiptPresentationUiResult.Rejected).issue.code,
        )
    }

    private fun loadCanonical(name: String): ReceiptPresentationUiResult {
        val rawEnvelope = extractEnvelope(Files.readAllBytes(fixtureRoot().resolve("fixtures/$name")))
        val decoded = ReceiptPresentationV1Decoder.decode(rawEnvelope)
        assertTrue(decoded is ReceiptPresentationResult.Accepted)
        val envelope = (decoded as ReceiptPresentationResult.Accepted).value
        return adapter.decodeAndMap(
            rawEnvelope,
            PresentationConsumerContext(
                envelope.requestId,
                envelope.imageId,
                PresentationConsumerMode.FIXTURE,
            ),
        )
    }

    private fun extractEnvelope(wrapper: ByteArray): ByteArray {
        strictFactory.createParser(wrapper).use { parser ->
            check(parser.nextToken() == JsonToken.START_OBJECT)
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                check(parser.currentToken == JsonToken.FIELD_NAME)
                val name = parser.currentName()
                val valueToken = parser.nextToken()
                if (name == "envelope") {
                    check(valueToken == JsonToken.START_OBJECT)
                    return ByteArrayOutputStream().use { output ->
                        strictFactory.createGenerator(output).use { generator ->
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

    private companion object {
        val strictFactory: JsonFactory =
            JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .build()
    }
}
