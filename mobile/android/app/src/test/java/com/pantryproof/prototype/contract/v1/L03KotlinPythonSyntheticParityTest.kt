package com.pantryproof.prototype.contract.v1

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import com.pantryproof.prototype.data.M3eReceiptPresentationAdapter
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Base64
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Independent 9-positive/27-negative Kotlin consumer check using Leng's original
 * Base64 payloads, embedded verbatim; no Python execution or operational transport.
 *
 * Add this file only under separately approved Tai synthetic-test scope.
 * Test names report exact vector and check, 36 distinct JVM test instances.
 */
data class L03Vector(
    val id: String, val base64: String, val length: Int, val sha256: String,
    val requestId: String, val imageId: String,
    val status: String, val stage: String, val code: String, val retryable: Boolean,
    val evidencePresent: Boolean, val evidenceStatus: String?,
    val gatePresent: Boolean, val gateDecision: String?,
) {
    override fun toString(): String = id // Never print the embedded envelope on failure.
}

enum class L03Case {
    POSITIVE, WRONG_EXPECTED_REQUEST, WRONG_EXPECTED_IMAGE, UNSUPPORTED_SCHEMA_VERSION
}

@RunWith(Parameterized::class)
class L03KotlinPythonSyntheticParityTest(
    private val vector: L03Vector,
    private val check: L03Case,
) {
    @Test
    fun verifyOriginalPythonBytesWithUnchangedKotlinConsumer() {
        val original = Base64.getDecoder().decode(vector.base64)
        assertEquals("${vector.id}: original canonical Base64", vector.base64,
            Base64.getEncoder().encodeToString(original))
        assertEquals("${vector.id}: original byte length", vector.length, original.size)
        assertEquals("${vector.id}: original SHA-256", vector.sha256, sha256(original))
        val context = PresentationConsumerContext(
            vector.requestId, vector.imageId, PresentationConsumerMode.FIXTURE,
        )
        when (check) {
            L03Case.POSITIVE -> positive(original, context)
            L03Case.WRONG_EXPECTED_REQUEST -> negative(
                original, context.copy(expectedRequestId = "request-l03-mismatch"),
                ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            )
            L03Case.WRONG_EXPECTED_IMAGE -> negative(
                original, context.copy(expectedImageId = "image-l03-mismatch"),
                ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
            )
            L03Case.UNSUPPORTED_SCHEMA_VERSION -> {
                val modifiedCopy = replaceOnlySchemaVersionOnParsedJson(original)
                assertFalse("${vector.id}: mutated copy must differ", original.contentEquals(modifiedCopy))
                // Confirm original bytes stay unchanged after constructing the test copy.
                assertEquals(vector.sha256, sha256(original))
                negative(modifiedCopy, context, ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION)
            }
        }
    }

    private fun positive(original: ByteArray, context: PresentationConsumerContext) {
        val result = ReceiptPresentationV1Validator.decodeAndValidate(original, context)
        assertTrue("${vector.id}: Kotlin validator rejected: $result", result is ReceiptPresentationResult.Accepted)
        val value = (result as ReceiptPresentationResult.Accepted).value
        assertEquals(vector.requestId, value.requestId)
        assertEquals(vector.imageId, value.imageId)
        assertEquals("receipt-presentation", value.schemaName)
        assertEquals("1", value.schemaVersion)
        assertEquals("0", value.sourceContractVersion)
        assertEquals(vector.status, value.outcome.status.name)
        val failure = requireNotNull(value.outcome.failure)
        assertEquals(vector.stage, failure.stage.name)
        assertEquals(vector.code, failure.code)
        assertEquals(vector.retryable, failure.retryable)
        assertNull(value.receipt)
        assertNull(value.automaticExtraction)
        assertEquals(PresentationSourceType.SYNTHETIC_FIXTURE, value.source.type)
        assertEquals("I2B_SYNTHETIC_FAILURE_V0", value.source.provenance.sourceSystem)
        assertEquals("src-v1-0123456789abcdef0123456789abcdef-1", value.source.provenance.sourceReference)
        assertNull(value.source.provenance.contentSha256)
        val evidence = value.sourceEvidence
        assertEquals(vector.evidencePresent, evidence != null)
        assertEquals(vector.evidenceStatus, evidence?.sourceProcessingStatus?.name)
        evidence?.tokenIds?.forEachIndexed { index, alias ->
            assertEquals("tok-v1-0123456789abcdef0123456789abcdef-${index + 1}", alias)
        }
        // All original exported source-bearing cases contain ten ordered positional aliases.
        assertEquals(if (vector.evidencePresent) 10 else 0, evidence?.tokenIds?.size ?: 0)
        val gate = value.sourceGate
        assertEquals(vector.gatePresent, gate != null)
        assertEquals(vector.gateDecision, gate?.decision?.name)
        if (gate != null) {
            assertEquals("gat-v1-0123456789abcdef0123456789abcdef-1", gate.gateResultId)
            assertEquals(listOf("Synthetic source structure was unavailable."), gate.reasons)
        }
        val ui = M3eReceiptPresentationAdapter().decodeAndMap(original, context)
        assertFalse(ui.canReview)
        when (vector.status) {
            "PROCESSING_UNAVAILABLE" -> {
                assertTrue("${vector.id}: consumer must map unavailable", ui is ReceiptPresentationUiResult.ProcessingUnavailable)
                val mapped = ui as ReceiptPresentationUiResult.ProcessingUnavailable
                assertEquals(vector.code, mapped.failureCode)
                assertEquals(vector.retryable, mapped.retryable)
            }
            "PROCESSING_FAILED" -> {
                assertTrue("${vector.id}: consumer must map technical failure", ui is ReceiptPresentationUiResult.ProcessingFailed)
                val mapped = ui as ReceiptPresentationUiResult.ProcessingFailed
                assertEquals(vector.stage, mapped.stage.name)
                assertEquals(vector.code, mapped.failureCode)
                assertEquals(vector.retryable, mapped.retryable)
            }
            else -> error("Unexpected exported outcome")
        }
    }

    private fun negative(originalOrMutated: ByteArray, context: PresentationConsumerContext, expectedCode: String) {
        val result = ReceiptPresentationV1Validator.decodeAndValidate(originalOrMutated, context)
        assertTrue("${vector.id}/${check}: expected Kotlin Rejected; observed $result", result is ReceiptPresentationResult.Rejected)
        assertEquals(expectedCode, (result as ReceiptPresentationResult.Rejected).issue.code)
        val ui = M3eReceiptPresentationAdapter().decodeAndMap(originalOrMutated, context)
        assertTrue("${vector.id}/${check}: expected adapter Rejected; observed $ui", ui is ReceiptPresentationUiResult.Rejected)
        assertEquals(expectedCode, (ui as ReceiptPresentationUiResult.Rejected).issue.code)
        assertFalse(ui.canReview)
    }

    /** Use Jackson's existing streaming parser. Never replace the original bytes. */
    private fun replaceOnlySchemaVersionOnParsedJson(original: ByteArray): ByteArray {
        val factory = JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build()
        val output = ByteArrayOutputStream()
        var replaced = 0
        factory.createParser(original).use { parser ->
            factory.createGenerator(output).use { generator ->
                assertEquals(JsonToken.START_OBJECT, parser.nextToken())
                generator.writeStartObject()
                while (parser.nextToken() != JsonToken.END_OBJECT) {
                    assertEquals(JsonToken.FIELD_NAME, parser.currentToken)
                    val memberName = parser.currentName()
                    val next = parser.nextToken()
                    if (memberName == "schemaVersion") {
                        assertEquals(JsonToken.VALUE_STRING, next)
                        assertEquals("1", parser.text)
                        generator.writeStringField("schemaVersion", "999")
                        replaced++
                    } else {
                        generator.writeFieldName(memberName)
                        generator.copyCurrentStructure(parser)
                    }
                }
                generator.writeEndObject()
                assertNull(parser.nextToken())
            }
        }
        assertEquals("Exactly one schemaVersion must be replaced", 1, replaced)
        return output.toByteArray()
    }

    private fun sha256(raw: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(raw).joinToString("") { "%02X".format(it.toInt() and 0xff) }

    companion object {
        @JvmStatic
        @Parameterized.Parameters(name = "{0} / {1}")
        fun cases(): Collection<Array<Any>> = vectors.flatMap { vector ->
            L03Case.values().map { check -> arrayOf<Any>(vector, check) }
        }

        private val vectors = listOf(
        L03Vector(
            id = "L03-P01",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiUFJPQ0VTU09SX05PVF9BVkFJTEFCTEUiLCJyZXRyeWFibGUiOmZhbHNlLCJzdGFnZSI6IkFWQUlMQUJJTElUWSJ9LCJzdGF0" +
            "dXMiOiJQUk9DRVNTSU5HX1VOQVZBSUxBQkxFIn0sInJlY2VpcHQiOm51bGwsInJlcXVlc3RJZCI6InJlcXVlc3QtbDAzLXN5bnRoZXRpYyIs" +
            "InNjaGVtYU5hbWUiOiJyZWNlaXB0LXByZXNlbnRhdGlvbiIsInNjaGVtYVZlcnNpb24iOiIxIiwic291cmNlIjp7InByb3ZlbmFuY2UiOnsi" +
            "Y29udGVudFNoYTI1NiI6bnVsbCwic291cmNlUmVmZXJlbmNlIjoic3JjLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEi" +
            "LCJzb3VyY2VTeXN0ZW0iOiJJMkJfU1lOVEhFVElDX0ZBSUxVUkVfVjAifSwidHlwZSI6IlNZTlRIRVRJQ19GSVhUVVJFIn0sInNvdXJjZUNv" +
            "bnRyYWN0VmVyc2lvbiI6IjAiLCJzb3VyY2VFdmlkZW5jZSI6bnVsbCwic291cmNlR2F0ZSI6bnVsbH0=",
            length = 545,
            sha256 = "729FBC1A081D1F8FD01C71EE1F18CFDDACF89FE77944DE5A82CD00343EB28756",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_UNAVAILABLE", stage = "AVAILABILITY",
            code = "PROCESSOR_NOT_AVAILABLE", retryable = false,
            evidencePresent = false, evidenceStatus = null,
            gatePresent = false, gateDecision = null,
        ),
        L03Vector(
            id = "L03-P02",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiT0NSX0VOR0lORV9GQUlMVVJFIiwicmV0cnlhYmxlIjp0cnVlLCJzdGFnZSI6Ik9DUiJ9LCJzdGF0dXMiOiJQUk9DRVNTSU5H" +
            "X0ZBSUxFRCJ9LCJyZWNlaXB0IjpudWxsLCJyZXF1ZXN0SWQiOiJyZXF1ZXN0LWwwMy1zeW50aGV0aWMiLCJzY2hlbWFOYW1lIjoicmVjZWlw" +
            "dC1wcmVzZW50YXRpb24iLCJzY2hlbWFWZXJzaW9uIjoiMSIsInNvdXJjZSI6eyJwcm92ZW5hbmNlIjp7ImNvbnRlbnRTaGEyNTYiOm51bGws" +
            "InNvdXJjZVJlZmVyZW5jZSI6InNyYy12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xIiwic291cmNlU3lzdGVtIjoiSTJC" +
            "X1NZTlRIRVRJQ19GQUlMVVJFX1YwIn0sInR5cGUiOiJTWU5USEVUSUNfRklYVFVSRSJ9LCJzb3VyY2VDb250cmFjdFZlcnNpb24iOiIwIiwi" +
            "c291cmNlRXZpZGVuY2UiOm51bGwsInNvdXJjZUdhdGUiOm51bGx9",
            length = 525,
            sha256 = "C18E533E92815EF04E3E0E8FAD50859CEB2DA48448D10BB3A43D825D9495B504",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "OCR",
            code = "OCR_ENGINE_FAILURE", retryable = true,
            evidencePresent = false, evidenceStatus = null,
            gatePresent = false, gateDecision = null,
        ),
        L03Vector(
            id = "L03-P03",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiT0NSX0VOR0lORV9GQUlMVVJFIiwicmV0cnlhYmxlIjp0cnVlLCJzdGFnZSI6Ik9DUiJ9LCJzdGF0dXMiOiJQUk9DRVNTSU5H" +
            "X0ZBSUxFRCJ9LCJyZWNlaXB0IjpudWxsLCJyZXF1ZXN0SWQiOiJyZXF1ZXN0LWwwMy1zeW50aGV0aWMiLCJzY2hlbWFOYW1lIjoicmVjZWlw" +
            "dC1wcmVzZW50YXRpb24iLCJzY2hlbWFWZXJzaW9uIjoiMSIsInNvdXJjZSI6eyJwcm92ZW5hbmNlIjp7ImNvbnRlbnRTaGEyNTYiOm51bGws" +
            "InNvdXJjZVJlZmVyZW5jZSI6InNyYy12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xIiwic291cmNlU3lzdGVtIjoiSTJC" +
            "X1NZTlRIRVRJQ19GQUlMVVJFX1YwIn0sInR5cGUiOiJTWU5USEVUSUNfRklYVFVSRSJ9LCJzb3VyY2VDb250cmFjdFZlcnNpb24iOiIwIiwi" +
            "c291cmNlRXZpZGVuY2UiOnsic291cmNlUHJvY2Vzc2luZ1N0YXR1cyI6Ik9DUl9GQUlMRUQiLCJ0b2tlbklkcyI6WyJ0b2stdjEtMDEyMzQ1" +
            "Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0yIiwidG9rLXYx" +
            "LTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTMiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNCIs" +
            "InRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi01IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJj" +
            "ZGVmLTYiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNyIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1" +
            "Njc4OWFiY2RlZi04IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTkiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2Rl" +
            "ZjAxMjM0NTY3ODlhYmNkZWYtMTAiXX0sInNvdXJjZUdhdGUiOm51bGx9",
            length = 1014,
            sha256 = "9E6321A792B33779310A027B9048907F0EE87F330507C5D970B5184C3EECD234",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "OCR",
            code = "OCR_ENGINE_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_FAILED",
            gatePresent = false, gateDecision = null,
        ),
        L03Vector(
            id = "L03-P04",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiU09VUkNFX0dBVEVfRVhFQ1VUSU9OX0ZBSUxVUkUiLCJyZXRyeWFibGUiOnRydWUsInN0YWdlIjoiU09VUkNFX0dBVEUifSwi" +
            "c3RhdHVzIjoiUFJPQ0VTU0lOR19GQUlMRUQifSwicmVjZWlwdCI6bnVsbCwicmVxdWVzdElkIjoicmVxdWVzdC1sMDMtc3ludGhldGljIiwi" +
            "c2NoZW1hTmFtZSI6InJlY2VpcHQtcHJlc2VudGF0aW9uIiwic2NoZW1hVmVyc2lvbiI6IjEiLCJzb3VyY2UiOnsicHJvdmVuYW5jZSI6eyJj" +
            "b250ZW50U2hhMjU2IjpudWxsLCJzb3VyY2VSZWZlcmVuY2UiOiJzcmMtdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIs" +
            "InNvdXJjZVN5c3RlbSI6IkkyQl9TWU5USEVUSUNfRkFJTFVSRV9WMCJ9LCJ0eXBlIjoiU1lOVEhFVElDX0ZJWFRVUkUifSwic291cmNlQ29u" +
            "dHJhY3RWZXJzaW9uIjoiMCIsInNvdXJjZUV2aWRlbmNlIjp7InNvdXJjZVByb2Nlc3NpbmdTdGF0dXMiOiJPQ1JfQ09NUExFVEVEIiwidG9r" +
            "ZW5JZHMiOlsidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0" +
            "NTY3ODlhYmNkZWYtMiIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0zIiwidG9rLXYxLTAxMjM0NTY3ODlhYmNk" +
            "ZWYwMTIzNDU2Nzg5YWJjZGVmLTQiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNSIsInRvay12MS0wMTIzNDU2" +
            "Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi02IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTciLCJ0b2stdjEt" +
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtOCIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi05Iiwi" +
            "dG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEwIl19LCJzb3VyY2VHYXRlIjpudWxsfQ==",
            length = 1036,
            sha256 = "2E83A06E907BA34AF6BCA3653F9282ED97EE9687034B8893156CF901E9896AB3",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "SOURCE_GATE",
            code = "SOURCE_GATE_EXECUTION_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_COMPLETED",
            gatePresent = false, gateDecision = null,
        ),
        L03Vector(
            id = "L03-P05",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiU09VUkNFX0dBVEVfRVhFQ1VUSU9OX0ZBSUxVUkUiLCJyZXRyeWFibGUiOnRydWUsInN0YWdlIjoiU09VUkNFX0dBVEUifSwi" +
            "c3RhdHVzIjoiUFJPQ0VTU0lOR19GQUlMRUQifSwicmVjZWlwdCI6bnVsbCwicmVxdWVzdElkIjoicmVxdWVzdC1sMDMtc3ludGhldGljIiwi" +
            "c2NoZW1hTmFtZSI6InJlY2VpcHQtcHJlc2VudGF0aW9uIiwic2NoZW1hVmVyc2lvbiI6IjEiLCJzb3VyY2UiOnsicHJvdmVuYW5jZSI6eyJj" +
            "b250ZW50U2hhMjU2IjpudWxsLCJzb3VyY2VSZWZlcmVuY2UiOiJzcmMtdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIs" +
            "InNvdXJjZVN5c3RlbSI6IkkyQl9TWU5USEVUSUNfRkFJTFVSRV9WMCJ9LCJ0eXBlIjoiU1lOVEhFVElDX0ZJWFRVUkUifSwic291cmNlQ29u" +
            "dHJhY3RWZXJzaW9uIjoiMCIsInNvdXJjZUV2aWRlbmNlIjp7InNvdXJjZVByb2Nlc3NpbmdTdGF0dXMiOiJPQ1JfUEFSVElBTCIsInRva2Vu" +
            "SWRzIjpbInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xIiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2" +
            "Nzg5YWJjZGVmLTIiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMyIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVm" +
            "MDEyMzQ1Njc4OWFiY2RlZi00IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTUiLCJ0b2stdjEtMDEyMzQ1Njc4" +
            "OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNiIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi03IiwidG9rLXYxLTAx" +
            "MjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTgiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtOSIsInRv" +
            "ay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xMCJdfSwic291cmNlR2F0ZSI6bnVsbH0=",
            length = 1034,
            sha256 = "2925CB67934D7313CD7F0E470D6AE8651E8F68498C9E228F42E5F5CAB7694B43",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "SOURCE_GATE",
            code = "SOURCE_GATE_EXECUTION_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_PARTIAL",
            gatePresent = false, gateDecision = null,
        ),
        L03Vector(
            id = "L03-P06",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiRVhUUkFDVElPTl9FTkdJTkVfRkFJTFVSRSIsInJldHJ5YWJsZSI6dHJ1ZSwic3RhZ2UiOiJFWFRSQUNUSU9OIn0sInN0YXR1" +
            "cyI6IlBST0NFU1NJTkdfRkFJTEVEIn0sInJlY2VpcHQiOm51bGwsInJlcXVlc3RJZCI6InJlcXVlc3QtbDAzLXN5bnRoZXRpYyIsInNjaGVt" +
            "YU5hbWUiOiJyZWNlaXB0LXByZXNlbnRhdGlvbiIsInNjaGVtYVZlcnNpb24iOiIxIiwic291cmNlIjp7InByb3ZlbmFuY2UiOnsiY29udGVu" +
            "dFNoYTI1NiI6bnVsbCwic291cmNlUmVmZXJlbmNlIjoic3JjLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJzb3Vy" +
            "Y2VTeXN0ZW0iOiJJMkJfU1lOVEhFVElDX0ZBSUxVUkVfVjAifSwidHlwZSI6IlNZTlRIRVRJQ19GSVhUVVJFIn0sInNvdXJjZUNvbnRyYWN0" +
            "VmVyc2lvbiI6IjAiLCJzb3VyY2VFdmlkZW5jZSI6eyJzb3VyY2VQcm9jZXNzaW5nU3RhdHVzIjoiT0NSX0NPTVBMRVRFRCIsInRva2VuSWRz" +
            "IjpbInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xIiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5" +
            "YWJjZGVmLTIiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMyIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEy" +
            "MzQ1Njc4OWFiY2RlZi00IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTUiLCJ0b2stdjEtMDEyMzQ1Njc4OWFi" +
            "Y2RlZjAxMjM0NTY3ODlhYmNkZWYtNiIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi03IiwidG9rLXYxLTAxMjM0" +
            "NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTgiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtOSIsInRvay12" +
            "MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xMCJdfSwic291cmNlR2F0ZSI6eyJkZWNpc2lvbiI6IlNVRkZJQ0lFTlQiLCJn" +
            "YXRlUmVzdWx0SWQiOiJnYXQtdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIsInJlYXNvbnMiOlsiU3ludGhldGljIHNv" +
            "dXJjZSBzdHJ1Y3R1cmUgd2FzIHVuYXZhaWxhYmxlLiJdfX0=",
            length = 1169,
            sha256 = "5D0AF182608BC288B4B16350A7EDBFC2965B453AE5316AB9425F0179343608CC",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "EXTRACTION",
            code = "EXTRACTION_ENGINE_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_COMPLETED",
            gatePresent = true, gateDecision = "SUFFICIENT",
        ),
        L03Vector(
            id = "L03-P07",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiRVhUUkFDVElPTl9FTkdJTkVfRkFJTFVSRSIsInJldHJ5YWJsZSI6dHJ1ZSwic3RhZ2UiOiJFWFRSQUNUSU9OIn0sInN0YXR1" +
            "cyI6IlBST0NFU1NJTkdfRkFJTEVEIn0sInJlY2VpcHQiOm51bGwsInJlcXVlc3RJZCI6InJlcXVlc3QtbDAzLXN5bnRoZXRpYyIsInNjaGVt" +
            "YU5hbWUiOiJyZWNlaXB0LXByZXNlbnRhdGlvbiIsInNjaGVtYVZlcnNpb24iOiIxIiwic291cmNlIjp7InByb3ZlbmFuY2UiOnsiY29udGVu" +
            "dFNoYTI1NiI6bnVsbCwic291cmNlUmVmZXJlbmNlIjoic3JjLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJzb3Vy" +
            "Y2VTeXN0ZW0iOiJJMkJfU1lOVEhFVElDX0ZBSUxVUkVfVjAifSwidHlwZSI6IlNZTlRIRVRJQ19GSVhUVVJFIn0sInNvdXJjZUNvbnRyYWN0" +
            "VmVyc2lvbiI6IjAiLCJzb3VyY2VFdmlkZW5jZSI6eyJzb3VyY2VQcm9jZXNzaW5nU3RhdHVzIjoiT0NSX1BBUlRJQUwiLCJ0b2tlbklkcyI6" +
            "WyJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFi" +
            "Y2RlZi0yIiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTMiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0" +
            "NTY3ODlhYmNkZWYtNCIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi01IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNk" +
            "ZWYwMTIzNDU2Nzg5YWJjZGVmLTYiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNyIsInRvay12MS0wMTIzNDU2" +
            "Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi04IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTkiLCJ0b2stdjEt" +
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMTAiXX0sInNvdXJjZUdhdGUiOnsiZGVjaXNpb24iOiJTVUZGSUNJRU5UIiwiZ2F0" +
            "ZVJlc3VsdElkIjoiZ2F0LXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJyZWFzb25zIjpbIlN5bnRoZXRpYyBzb3Vy" +
            "Y2Ugc3RydWN0dXJlIHdhcyB1bmF2YWlsYWJsZS4iXX19",
            length = 1167,
            sha256 = "4C9099923F3538E66067AE25E90F2CEFCB7EFE011439BC91170F0A17CCA70F54",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "EXTRACTION",
            code = "EXTRACTION_ENGINE_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_PARTIAL",
            gatePresent = true, gateDecision = "SUFFICIENT",
        ),
        L03Vector(
            id = "L03-P08",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiUFJFU0VOVEFUSU9OX1BST0pFQ1RJT05fRkFJTFVSRSIsInJldHJ5YWJsZSI6dHJ1ZSwic3RhZ2UiOiJQUkVTRU5UQVRJT05f" +
            "QURBUFRFUiJ9LCJzdGF0dXMiOiJQUk9DRVNTSU5HX0ZBSUxFRCJ9LCJyZWNlaXB0IjpudWxsLCJyZXF1ZXN0SWQiOiJyZXF1ZXN0LWwwMy1z" +
            "eW50aGV0aWMiLCJzY2hlbWFOYW1lIjoicmVjZWlwdC1wcmVzZW50YXRpb24iLCJzY2hlbWFWZXJzaW9uIjoiMSIsInNvdXJjZSI6eyJwcm92" +
            "ZW5hbmNlIjp7ImNvbnRlbnRTaGEyNTYiOm51bGwsInNvdXJjZVJlZmVyZW5jZSI6InNyYy12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4" +
            "OWFiY2RlZi0xIiwic291cmNlU3lzdGVtIjoiSTJCX1NZTlRIRVRJQ19GQUlMVVJFX1YwIn0sInR5cGUiOiJTWU5USEVUSUNfRklYVFVSRSJ9" +
            "LCJzb3VyY2VDb250cmFjdFZlcnNpb24iOiIwIiwic291cmNlRXZpZGVuY2UiOnsic291cmNlUHJvY2Vzc2luZ1N0YXR1cyI6Ik9DUl9DT01Q" +
            "TEVURUQiLCJ0b2tlbklkcyI6WyJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMSIsInRvay12MS0wMTIzNDU2Nzg5" +
            "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0yIiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTMiLCJ0b2stdjEtMDEy" +
            "MzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNCIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi01IiwidG9r" +
            "LXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTYiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYt" +
            "NyIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi04IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5" +
            "YWJjZGVmLTkiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtMTAiXX0sInNvdXJjZUdhdGUiOnsiZGVjaXNpb24i" +
            "OiJTVUZGSUNJRU5UIiwiZ2F0ZVJlc3VsdElkIjoiZ2F0LXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJyZWFzb25z" +
            "IjpbIlN5bnRoZXRpYyBzb3VyY2Ugc3RydWN0dXJlIHdhcyB1bmF2YWlsYWJsZS4iXX19",
            length = 1185,
            sha256 = "815C6DC36A756A834B9F882E879FA16D792BB28A399C5B8C71348792D2B55562",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "PRESENTATION_ADAPTER",
            code = "PRESENTATION_PROJECTION_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_COMPLETED",
            gatePresent = true, gateDecision = "SUFFICIENT",
        ),
        L03Vector(
            id = "L03-P09",
            base64 = "eyJhdXRvbWF0aWNFeHRyYWN0aW9uIjpudWxsLCJpbWFnZUlkIjoiaW1hZ2UtbDAzLXN5bnRoZXRpYyIsIm91dGNvbWUiOnsiZmFpbHVyZSI6" +
            "eyJjb2RlIjoiUFJFU0VOVEFUSU9OX1BST0pFQ1RJT05fRkFJTFVSRSIsInJldHJ5YWJsZSI6dHJ1ZSwic3RhZ2UiOiJQUkVTRU5UQVRJT05f" +
            "QURBUFRFUiJ9LCJzdGF0dXMiOiJQUk9DRVNTSU5HX0ZBSUxFRCJ9LCJyZWNlaXB0IjpudWxsLCJyZXF1ZXN0SWQiOiJyZXF1ZXN0LWwwMy1z" +
            "eW50aGV0aWMiLCJzY2hlbWFOYW1lIjoicmVjZWlwdC1wcmVzZW50YXRpb24iLCJzY2hlbWFWZXJzaW9uIjoiMSIsInNvdXJjZSI6eyJwcm92" +
            "ZW5hbmNlIjp7ImNvbnRlbnRTaGEyNTYiOm51bGwsInNvdXJjZVJlZmVyZW5jZSI6InNyYy12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4" +
            "OWFiY2RlZi0xIiwic291cmNlU3lzdGVtIjoiSTJCX1NZTlRIRVRJQ19GQUlMVVJFX1YwIn0sInR5cGUiOiJTWU5USEVUSUNfRklYVFVSRSJ9" +
            "LCJzb3VyY2VDb250cmFjdFZlcnNpb24iOiIwIiwic291cmNlRXZpZGVuY2UiOnsic291cmNlUHJvY2Vzc2luZ1N0YXR1cyI6Ik9DUl9QQVJU" +
            "SUFMIiwidG9rZW5JZHMiOlsidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEiLCJ0b2stdjEtMDEyMzQ1Njc4OWFi" +
            "Y2RlZjAxMjM0NTY3ODlhYmNkZWYtMiIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0zIiwidG9rLXYxLTAxMjM0" +
            "NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTQiLCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtNSIsInRvay12" +
            "MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi02IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTci" +
            "LCJ0b2stdjEtMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYtOCIsInRvay12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFi" +
            "Y2RlZi05IiwidG9rLXYxLTAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmLTEwIl19LCJzb3VyY2VHYXRlIjp7ImRlY2lzaW9uIjoi" +
            "U1VGRklDSUVOVCIsImdhdGVSZXN1bHRJZCI6ImdhdC12MS0wMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZi0xIiwicmVhc29ucyI6" +
            "WyJTeW50aGV0aWMgc291cmNlIHN0cnVjdHVyZSB3YXMgdW5hdmFpbGFibGUuIl19fQ==",
            length = 1183,
            sha256 = "E5264850DE80AB73A453406A896F90DEC44D3D85BBD1B469F4E566B369BEF21E",
            requestId = "request-l03-synthetic", imageId = "image-l03-synthetic",
            status = "PROCESSING_FAILED", stage = "PRESENTATION_ADAPTER",
            code = "PRESENTATION_PROJECTION_FAILURE", retryable = true,
            evidencePresent = true, evidenceStatus = "OCR_PARTIAL",
            gatePresent = true, gateDecision = "SUFFICIENT",
        )
        )
    }
}
