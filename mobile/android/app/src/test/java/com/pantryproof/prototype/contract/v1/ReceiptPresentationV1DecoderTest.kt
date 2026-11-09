package com.pantryproof.prototype.contract.v1

import java.nio.charset.StandardCharsets
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptPresentationV1DecoderTest {
    @Test
    fun strictDecoderAcceptsOneValidEnvelope() {
        val decoded = ReceiptPresentationV1Decoder.decode(validUnavailableJson())

        assertTrue(decoded is ReceiptPresentationResult.Accepted)
        val envelope = (decoded as ReceiptPresentationResult.Accepted).value
        assertEquals("request-decoder-001", envelope.requestId)
        assertEquals(PresentationOutcomeStatus.PROCESSING_UNAVAILABLE, envelope.outcome.status)
        assertEquals(PresentationFailureStage.AVAILABILITY, envelope.outcome.failure?.stage)
    }

    @Test
    fun strictDecoderRejectsBomMalformedUtf8AndUnpairedSurrogate() {
        val valid = validUnavailableJson()
        assertRejected(byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + valid)
        assertRejected(byteArrayOf('{'.code.toByte(), 0xC3.toByte(), 0x28, '}'.code.toByte()))
        assertRejected(
            validUnavailableText()
                .replace("M3E_ANDROID_TEST", "\\uD800")
                .toByteArray(StandardCharsets.UTF_8),
        )
    }

    @Test
    fun strictDecoderRejectsCommentsTrailingCommasAndTrailingContent() {
        val valid = validUnavailableText()
        assertRejected(valid.replaceFirst("{", "{/*comment*/").toByteArray())
        assertRejected(valid.replace("\n}", ",\n}").toByteArray())
        assertRejected((valid + " true").toByteArray())
        assertRejected(valid.replace("false", "NaN").toByteArray())
    }

    @Test
    fun strictDecoderRejectsDuplicateObjectKeys() {
        val duplicate =
            validUnavailableText()
                .replace(
                    "\"schemaVersion\": \"1\",",
                    "\"schemaVersion\": \"1\",\n  \"schemaVersion\": \"1\",",
                )

        assertRejected(
            duplicate.toByteArray(),
            ReceiptPresentationIssueCodes.DUPLICATE_JSON_KEY,
        )
    }

    @Test
    fun strictDecoderRejectsMissingUnknownAndIncorrectlyTypedMembers() {
        val valid = validUnavailableText()
        assertRejected(
            valid.replace(",\n  \"receipt\": null", "").toByteArray(),
            ReceiptPresentationIssueCodes.MISSING_MEMBER,
        )
        assertRejected(
            valid.replace("  \"receipt\": null", "  \"unexpected\": null,\n  \"receipt\": null")
                .toByteArray(),
            ReceiptPresentationIssueCodes.UNKNOWN_MEMBER,
        )
        assertRejected(
            valid.replace("\"request-decoder-001\"", "7").toByteArray(),
            ReceiptPresentationIssueCodes.INVALID_JSON,
        )
    }

    @Test
    fun strictDecoderRejectsUnknownEnumsAndUnsupportedVersions() {
        val valid = validUnavailableText()
        assertRejected(
            valid.replace("LOCAL_IMAGE", "REMOTE_IMAGE").toByteArray(),
            ReceiptPresentationIssueCodes.UNKNOWN_ENUM,
        )
        assertRejected(
            valid.replace("\"schemaVersion\": \"1\"", "\"schemaVersion\": \"2\"")
                .toByteArray(),
            ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION,
        )
        assertRejected(
            valid.replace("\"sourceContractVersion\": \"0\"", "\"sourceContractVersion\": \"1\"")
                .toByteArray(),
            ReceiptPresentationIssueCodes.UNSUPPORTED_CONTRACT_VERSION,
        )
    }

    @Test
    fun productionDecoderDoesNotAcceptTheFixtureWrapper() {
        val wrapper =
            """
            {
              "fixtureStatus": "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY",
              "scenario": "decoder-boundary",
              "expectedResult": "ACCEPT",
              "envelope": ${validUnavailableText()}
            }
            """.trimIndent().toByteArray(StandardCharsets.UTF_8)

        assertRejected(wrapper, ReceiptPresentationIssueCodes.MISSING_MEMBER)
    }

    @Test
    fun listBearingModelsDefensivelyCopyTheirInputs() {
        val source = mutableListOf("token-001")
        val evidence = PresentationSourceEvidence(SourceProcessingStatus.RECEIVED, source)
        source += "token-002"

        assertEquals(listOf("token-001"), evidence.tokenIds)
        @Suppress("UNCHECKED_CAST")
        val exposed = evidence.tokenIds as MutableList<String>
        try {
            exposed += "token-003"
            throw AssertionError("immutable model list accepted a mutation")
        } catch (_: UnsupportedOperationException) {
            // Expected: callers cannot mutate the model through its exposed list.
        }
    }

    private fun assertRejected(
        raw: ByteArray,
        expectedCode: String = ReceiptPresentationIssueCodes.INVALID_JSON,
    ) {
        val result = ReceiptPresentationV1Decoder.decode(raw)
        assertTrue("Expected rejection but received $result", result is ReceiptPresentationResult.Rejected)
        assertEquals(expectedCode, (result as ReceiptPresentationResult.Rejected).issue.code)
    }

    private fun validUnavailableJson(): ByteArray =
        validUnavailableText().toByteArray(StandardCharsets.UTF_8)

    private fun validUnavailableText(): String =
        """
        {
          "schemaName": "receipt-presentation",
          "schemaVersion": "1",
          "sourceContractVersion": "0",
          "requestId": "request-decoder-001",
          "imageId": "image-decoder-001",
          "source": {
            "type": "LOCAL_IMAGE",
            "provenance": {
              "sourceSystem": "M3E_ANDROID_TEST",
              "sourceReference": "source-decoder-001",
              "contentSha256": null
            }
          },
          "outcome": {
            "status": "PROCESSING_UNAVAILABLE",
            "failure": {
              "stage": "AVAILABILITY",
              "code": "PROCESSOR_NOT_AVAILABLE",
              "retryable": false
            }
          },
          "sourceEvidence": null,
          "sourceGate": null,
          "automaticExtraction": null,
          "receipt": null
        }
        """.trimIndent()
}
