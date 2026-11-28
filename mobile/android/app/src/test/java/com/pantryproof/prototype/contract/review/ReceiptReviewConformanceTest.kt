package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Validator
import com.pantryproof.prototype.data.sha256
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import org.junit.Assert.*
import org.junit.Test

class ReceiptReviewConformanceTest {
    @Test fun allSeventeenCanonicalCases() {
        val manifest = manifest()
        var accepted = 0
        var rejected = 0
        for (entry in manifest["fixtures"].array()) {
            val path = entry["path"].string()
            val raw = Files.readAllBytes(root.resolve(path))
            assertEquals(path, entry["byteLength"].integer(), raw.size)
            assertEquals(path, entry["sha256"].string(), sha256(raw))
            val fixture = readReviewFixture(raw)
            assertEquals(path, entry["expectedResult"].string(), fixture.expectedResult)
            assertEquals(path, entry["expectedPath"].textOrNull(), fixture.expectedPath)
            val rawV1 = slice(fixture.body, rootObject(fixture.body)["presentation"])
            val base = rootObject(rawV1)
            val embeddedContext = fixture.context.presentation.copy(
                expectedRequestId = base["requestId"].string(),
                expectedImageId = base["imageId"].string(),
            )
            assertTrue(path, ReceiptPresentationV1Validator.decodeAndValidate(rawV1, embeddedContext) is ReceiptPresentationResult.Accepted)
            verify(path, fixture.body, fixture.context, fixture.expectedResult, fixture.expectedPath)
            if (fixture.expectedResult == "ACCEPT") accepted++ else rejected++
        }
        assertEquals(10, accepted)
        assertEquals(7, rejected)
    }

    @Test fun sourceReferencesUseOpaqueIdentifiersWithoutRelaxingReasonValidation() {
        val fixture = loadReviewFixture("fixtures/01-policy-verified-correction.json")
        val body = fixture.body.decodeToString()
        val canonical = "\"reference\":\"ref-milk\""
        val path = "$.review.fields[3].alternativeCandidates[0].sourceReferences[0].reference"
        assertTrue(body.contains(canonical))
        fun withReference(jsonValue: String): ByteArray =
            body.replaceFirst(canonical, "\"reference\":$jsonValue").encodeToByteArray()

        val scoped = "retailer:Snapshot_1:milk-7"
        val reviewed = ReceiptReviewV1Decoder.decode(withReference("\"$scoped\""), fixture.context)
            as ReceiptPresentationResult.Accepted
        val reference = requireNotNull(reviewed.value.review).fields[3].alternatives[0].references[0]
        assertEquals(scoped, reference.id)
        assertEquals(listOf("tok-4"), reference.tokenIds)

        for (value in listOf("\"store::milk\"", "\"milk entry\"", "\"https://example.org/entry\"",
            "\"file:private-entry\"", "\"catalog/entry\"", "\"store:held-out-07\"", "\"store:participant-07\"",
            "\"\\u200Bentry\"")
        ) {
            verify("invalid opaque reference $value", withReference(value), fixture.context,
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE, path)
        }
        verify("numeric reference", withReference("7"), fixture.context, ReceiptPresentationIssueCodes.INVALID_JSON, path)
    }

    @Test fun allFiveCanonicalByteLimits() {
        val cases = manifest()["byteLimitCases"].array()
        assertEquals(5, cases.size)
        for (case in cases) {
            val fixture = loadReviewFixture(case["baseFixture"].string())
            val span = rootObject(fixture.body)["presentation"].objectNode()
            val index = when (case["location"].string()) {
                "insidePresentation" -> span.byteStart + 1
                "beforePresentation" -> span.byteStart
                "insideWrapper" -> 1
                else -> error("unknown generated case")
            }
            val spaces = case["spaceCount"].integer()
            val body = fixture.body.copyOfRange(0, index) + ByteArray(spaces) { 0x20 } +
                fixture.body.copyOfRange(index, fixture.body.size)
            val id = case["id"].string()
            assertEquals(id, case["bodyByteLength"].integer(), body.size)
            assertEquals(id, case["bodySha256"].string(), sha256(body))
            assertEquals(id, case["presentationByteLength"].integer(), slice(body, rootObject(body)["presentation"]).size)
            verify(id, body, fixture.context, case["expectedResult"].string(), case["expectedPath"].textOrNull())
        }
    }

    @Test fun strictLexicalRulesPrecedeVersionAndSpans() {
        val fixture = loadReviewFixture("fixtures/13-exact-weighted-quantity.json")
        val body = fixture.body.decodeToString()
        val invalid = listOf(
            byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + fixture.body,
            byteArrayOf(0xC3.toByte(), 0x28),
            body.replace("\"schemaVersion\":\"1\"}", "\"schemaVersion\":\"999\"}{}").encodeToByteArray(),
            body.replace("\"Kopi Édisi\"", "\"\\uD800\"").encodeToByteArray(),
            body.replace("\"schemaVersion\":\"1\"}", "\"schemaVersion\":\"1\",}").encodeToByteArray(),
            body.replaceFirst("\"rawConfidence\":0.91", "\"rawConfidence\":NaN").encodeToByteArray(),
        )
        invalid.forEach {
            val result = ReceiptReviewV1Decoder.decode(it, fixture.context) as ReceiptPresentationResult.Rejected
            assertEquals(ReceiptPresentationIssueCodes.INVALID_JSON, result.issue.code)
        }
        val dupe = "{\"x\":0,\"\\u0078\":1,".encodeToByteArray() + fixture.body.copyOfRange(1, fixture.body.size)
        verify("escaped duplicate", dupe, fixture.context, ReceiptPresentationIssueCodes.DUPLICATE_JSON_KEY, "$")
        val escaped = body.replaceFirst("\"presentation\":", "\"pre\\u0073entation\":").encodeToByteArray()
        verify("escaped presentation", escaped, fixture.context, "ACCEPT", null)
        val bare = slice(fixture.body, rootObject(fixture.body)["presentation"])
        verify("unexpected bare", bare, fixture.context, ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION, "$.schemaVersion")
        val exact = bare + ByteArray(ReceiptPresentationV1Decoder.MAX_BYTES - bare.size) { 0x20 }
        assertTrue(ReceiptPresentationV1Validator.decodeAndValidate(exact, fixture.context.presentation) is ReceiptPresentationResult.Accepted)
        val tooLarge = ReceiptPresentationV1Decoder.decode(exact + byteArrayOf(0x20)) as ReceiptPresentationResult.Rejected
        assertEquals(ReceiptPresentationIssueCodes.RESPONSE_TOO_LARGE, tooLarge.issue.code)
        assertEquals("$", tooLarge.issue.path)
    }

    private fun verify(label: String, bytes: ByteArray, context: ReviewContext, code: String, path: String?) {
        val result = ReceiptReviewV1Decoder.decode(bytes, context)
        val actual = (result as? ReceiptPresentationResult.Rejected)?.issue
        println("$label\t${actual?.code ?: "ACCEPT"}\t${actual?.path.orEmpty()}")
        assertEquals("$label: $actual", code, actual?.code ?: "ACCEPT")
        assertEquals(label, path, actual?.path)
    }

    private fun manifest(): ReviewJson {
        val bytes = Files.readAllBytes(root.resolve("manifest.json"))
        assertEquals("0361091ee0d9fadef3af9a337700220a0013e0e891764747e548aa45981657ff", sha256(bytes))
        return rootObject(bytes)
    }
}

private val root: Path by lazy {
    generateSequence(Paths.get(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
        .map { it.resolve("tests/fixtures/receipt_presentation_v1/review_v1") }
        .first { Files.isRegularFile(it.resolve("manifest.json")) }
}

internal data class ReviewFixture(val body: ByteArray, val context: ReviewContext, val expectedResult: String, val expectedPath: String?)

internal fun loadReviewFixture(path: String): ReviewFixture = readReviewFixture(Files.readAllBytes(root.resolve(path)))

private fun readReviewFixture(bytes: ByteArray): ReviewFixture {
    val j = rootObject(bytes)
    val context = j["consumerContext"]
    fun optional(name: String): Int? = context.objectNode().members[name]?.let { ReviewJson(it, name).integer() }
    return ReviewFixture(slice(bytes, j["envelope"]),
        ReviewContext(PresentationConsumerContext(context["expectedRequestId"].string(), context["expectedImageId"].string(),
            PresentationConsumerMode.valueOf(context["consumerMode"].string())),
            optional("expectedImageWidth"), optional("expectedImageHeight")), j["expectedResult"].string(), j["expectedPath"].textOrNull())
}

private fun rootObject(bytes: ByteArray): ReviewJson = when (val result = ReceiptPresentationV1Decoder.strictObject(bytes)) {
    is ReceiptPresentationResult.Accepted -> ReviewJson(result.value, "$")
    is ReceiptPresentationResult.Rejected -> error(result.issue.toString())
}

private fun slice(bytes: ByteArray, value: ReviewJson): ByteArray =
    value.objectNode().let { bytes.copyOfRange(it.byteStart, it.byteEnd) }
